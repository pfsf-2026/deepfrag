// deepfrag-live: the running state of a QuakeWorld match for the live panels.
//
//	deepfrag-live dump   <demo.mvd[.gz]>             whole demo, print the final state
//	deepfrag-live replay [-speed 1] <demo.mvd[.gz]>   a finished demo at match speed (testing)
//	deepfrag-live tail   <demo.mvd>                   a demo mvdsv is still recording
//	deepfrag-live watch  <ktx/demos dir>              every demo being recorded there (see watch.go)
//
// replay and tail serve GET /state (JSON) and GET /events (server-sent events, one
// snapshot a second) on -listen.
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"os/signal"
	"sync"
	"time"

	"deepfrag/live/match"
	"deepfrag/live/source"

	"github.com/mvd-analyzer/mvd-reader/events"
	mvdsource "github.com/mvd-analyzer/mvd-reader/source/mvd"
)

func main() {
	log.SetFlags(log.Ltime)
	if len(os.Args) < 2 {
		usage()
	}
	cmd, args := os.Args[1], os.Args[2:]
	fs := flag.NewFlagSet(cmd, flag.ExitOnError)
	listen := fs.String("listen", ":8090", "http address for /state and /events")
	speed := fs.Float64("speed", 1, "replay: match seconds per real second")
	idle := fs.Duration("idle", 90*time.Second, "tail: stop when the file has not grown for this long")
	fs.Parse(args)
	if fs.NArg() != 1 {
		usage()
	}
	path := fs.Arg(0)

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()

	switch cmd {
	case "dump":
		f, err := os.Open(path)
		check(err)
		defer f.Close()
		st := match.New()
		check(run(ctx, f, st, nil, 0))
		out, _ := json.MarshalIndent(st.Snapshot(), "", "  ")
		fmt.Println(string(out))
	case "watch":
		runWatch(ctx, path, *listen, *idle)
	case "replay", "tail":
		var r io.Reader
		if cmd == "replay" {
			f, err := os.Open(path)
			check(err)
			defer f.Close()
			r = f
		} else {
			t, err := source.OpenTail(ctx, path, *idle)
			check(err)
			defer t.Close()
			r = t
		}
		hub := newHub()
		go serve(*listen, hub)
		pace := 0.0
		if cmd == "replay" {
			pace = *speed
		}
		err := run(ctx, r, nil, hub, pace)
		check(err)
		log.Printf("stream ended")
		hub.publish(hub.last.Status, true)
	default:
		usage()
	}
}

func usage() {
	fmt.Fprintln(os.Stderr, "usage: deepfrag-live dump|replay|tail|watch [-listen :8090] [-speed 1] [-idle 90s] <demo.mvd[.gz] | demos dir>")
	os.Exit(2)
}

func check(err error) {
	if err != nil {
		log.Fatal(err)
	}
}

// run feeds the stream through the parser into a match state. With a hub it publishes a
// snapshot every second of match time; pace > 0 sleeps so match time runs at that speed.
func run(ctx context.Context, r io.Reader, st *match.State, hub *hub, pace float64) error {
	src, err := mvdsource.NewFromReader(r)
	if err != nil {
		return err
	}
	defer src.Close()
	if st == nil {
		st = match.New()
	}
	began := time.Now()
	var firstMs, lastPublishMs int32 = -1, -1
	for ctx.Err() == nil {
		ev, err := src.Next()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return err
		}
		st.Apply(ev)
		t, ok := ev.(interface{ EventTimeMs() int32 })
		if !ok {
			continue
		}
		ms := t.EventTimeMs()
		if firstMs < 0 {
			firstMs = ms
		}
		if pace > 0 {
			due := began.Add(time.Duration(float64(ms-firstMs)/pace) * time.Millisecond)
			if wait := time.Until(due); wait > 0 {
				select {
				case <-ctx.Done():
				case <-time.After(wait):
				}
			}
		}
		if hub != nil && ms-lastPublishMs >= 1000 {
			lastPublishMs = ms
			hub.set(st.Snapshot())
		}
	}
	if hub != nil {
		hub.set(st.Snapshot())
	}
	return nil
}

// hub holds the latest snapshot and fans it out to /events subscribers.
type hub struct {
	mu   sync.Mutex
	last match.Snapshot
	subs map[chan []byte]bool
}

func newHub() *hub { return &hub{subs: map[chan []byte]bool{}} }

func (h *hub) set(s match.Snapshot) {
	h.mu.Lock()
	h.last = s
	h.mu.Unlock()
	h.publish(s.Status, false)
}

func (h *hub) publish(_ match.Status, final bool) {
	h.mu.Lock()
	defer h.mu.Unlock()
	data, _ := json.Marshal(h.last)
	for c := range h.subs {
		select {
		case c <- data:
		default: // a slow client misses a frame, the next one has everything
		}
		if final {
			close(c)
			delete(h.subs, c)
		}
	}
}

func serve(addr string, h *hub) {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /state", h.serveState)
	mux.HandleFunc("GET /events", h.serveEvents)
	log.Printf("serving /state and /events on %s", addr)
	log.Fatal(http.ListenAndServe(addr, mux))
}

func (h *hub) serveState(w http.ResponseWriter, r *http.Request) {
	{
		h.mu.Lock()
		data, _ := json.Marshal(h.last)
		h.mu.Unlock()
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Access-Control-Allow-Origin", "*")
		w.Write(data)
	}
}

func (h *hub) serveEvents(w http.ResponseWriter, r *http.Request) {
	{
		flusher, ok := w.(http.Flusher)
		if !ok {
			http.Error(w, "streaming unsupported", http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "text/event-stream")
		w.Header().Set("Cache-Control", "no-cache")
		w.Header().Set("Access-Control-Allow-Origin", "*")
		c := make(chan []byte, 4)
		h.mu.Lock()
		h.subs[c] = true
		first, _ := json.Marshal(h.last)
		h.mu.Unlock()
		fmt.Fprintf(w, "data: %s\n\n", first)
		flusher.Flush()
		defer func() {
			h.mu.Lock()
			if h.subs[c] {
				delete(h.subs, c)
			}
			h.mu.Unlock()
		}()
		for {
			select {
			case <-r.Context().Done():
				return
			case data, ok := <-c:
				if !ok {
					return
				}
				fmt.Fprintf(w, "data: %s\n\n", data)
				flusher.Flush()
			}
		}
	}
}

var _ events.Source = (*mvdsource.Source)(nil)
