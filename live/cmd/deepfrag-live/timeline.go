package main

import (
	"bytes"
	"compress/gzip"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"regexp"
	"strings"
	"sync"
	"time"

	"deepfrag/live/match"

	"errors"
	mvdsource "github.com/mvd-analyzer/mvd-reader/source/mvd"
)

// A timeline is the match state once a second for a finished demo, so a player can show
// the panels for wherever playback is (seeking included). The feed is sent once, whole;
// a client shows the entries up to the current clock.
type timeline struct {
	Map         string          `json:"map"`
	Mode        string          `json:"mode"`
	Hostname    string          `json:"hostname"`
	TimelimitMs int32           `json:"timelimitMs"`
	Feed        []match.Kill    `json:"feed"`
	Frames      []timelineFrame `json:"frames"`
}

type timelineFrame struct {
	ClockMs int32           `json:"clockMs"`
	Status  match.Status    `json:"status"`
	Players []*match.Player `json:"players"`
	Items   []*match.Item   `json:"items"`
}

func buildTimeline(r io.Reader) (*timeline, error) {
	src, err := mvdsource.NewFromReader(r)
	if err != nil {
		return nil, err
	}
	defer src.Close()
	st := match.New()
	tl := &timeline{}
	var lastClock int32 = -1 << 30
	for {
		ev, err := src.Next()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return nil, err
		}
		st.Apply(ev)
		if _, ok := ev.(interface{ EventTimeMs() int32 }); !ok {
			continue
		}
		snap := st.Snapshot()
		if snap.Status == match.Warmup || snap.ClockMs-lastClock < 1000 {
			continue
		}
		lastClock = snap.ClockMs - snap.ClockMs%1000
		tl.Frames = append(tl.Frames, timelineFrame{ClockMs: lastClock, Status: snap.Status, Players: snap.Players, Items: snap.Items})
	}
	final := st.Snapshot()
	tl.Map, tl.Mode, tl.Hostname, tl.TimelimitMs, tl.Feed = final.Map, final.Mode, final.Hostname, final.TimelimitMs, final.Feed
	tl.Frames = append(tl.Frames, timelineFrame{ClockMs: final.ClockMs, Status: final.Status, Players: final.Players, Items: final.Items})
	return tl, nil
}

var sha256Pattern = regexp.MustCompile(`^[0-9a-f]{64}$`)

// serve: GET /timeline/{sha256} for hub demos, gzipped JSON, cached in memory
func runServe(ctx context.Context, listen string) {
	var mu sync.Mutex
	cache := map[string][]byte{}
	order := []string{}
	client := &http.Client{Timeout: 60 * time.Second}

	mux := http.NewServeMux()
	mux.HandleFunc("GET /timeline/{sha}", func(w http.ResponseWriter, r *http.Request) {
		sha := strings.ToLower(r.PathValue("sha"))
		if !sha256Pattern.MatchString(sha) {
			http.Error(w, "bad demo id", http.StatusBadRequest)
			return
		}
		mu.Lock()
		body, ok := cache[sha]
		mu.Unlock()
		if !ok {
			req, _ := http.NewRequestWithContext(r.Context(), "GET", fmt.Sprintf("https://d.quake.world/%s/%s.mvd.gz", sha[:3], sha), nil)
			req.Header.Set("User-Agent", "DeepFrag-live/0.1")
			resp, err := client.Do(req)
			if err != nil || resp.StatusCode != 200 {
				if resp != nil {
					resp.Body.Close()
				}
				http.Error(w, "demo not found", http.StatusNotFound)
				return
			}
			tl, err := buildTimeline(resp.Body)
			resp.Body.Close()
			if err != nil {
				http.Error(w, "demo did not parse: "+err.Error(), http.StatusUnprocessableEntity)
				return
			}
			var buf bytes.Buffer
			gz := gzip.NewWriter(&buf)
			json.NewEncoder(gz).Encode(tl)
			gz.Close()
			body = buf.Bytes()
			mu.Lock()
			cache[sha] = body
			order = append(order, sha)
			if len(order) > 200 {
				delete(cache, order[0])
				order = order[1:]
			}
			mu.Unlock()
		}
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Content-Encoding", "gzip")
		w.Header().Set("Cache-Control", "public, max-age=86400")
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Write(body)
	})
	newQTVStreams().register(mux)
	srv := &http.Server{Addr: listen, Handler: mux}
	go func() {
		<-ctx.Done()
		srv.Close()
	}()
	log.Printf("serving /timeline/{sha256} and /qtv/{stream}/events on %s", listen)
	if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Fatal(err)
	}
}
