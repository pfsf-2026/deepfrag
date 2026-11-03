package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"

	"deepfrag/live/match"
	"deepfrag/live/source"
)

// watch follows every demo mvdsv is recording in dir: a .mvd that grew in the last few
// seconds gets its own tail, its state is served until a while after it stops.
//
//	GET /live                      the matches being followed
//	GET /live/{id}/state           one match, JSON
//	GET /live/{id}/events          one match, server-sent events
//	GET /live/port/{port}/events   the current match on a game port (what the app uses)
type watcher struct {
	dir     string
	idle    time.Duration
	keep    time.Duration
	mu      sync.Mutex
	matches map[string]*followed // by demo file name
}

type followed struct {
	id      string
	file    string
	hub     *hub
	started time.Time
	ended   time.Time
}

var portInName = regexp.MustCompile(`:(\d{4,5})\b`)

func (f *followed) port() string {
	f.hub.mu.Lock()
	defer f.hub.mu.Unlock()
	if m := portInName.FindStringSubmatch(f.hub.last.Hostname); m != nil {
		return m[1]
	}
	return ""
}

func runWatch(ctx context.Context, dir, listen string, idle time.Duration) {
	w := &watcher{dir: dir, idle: idle, keep: 2 * time.Minute, matches: map[string]*followed{}}
	go w.serve(listen)
	for ctx.Err() == nil {
		w.scan(ctx)
		select {
		case <-ctx.Done():
		case <-time.After(2 * time.Second):
		}
	}
}

func (w *watcher) scan(ctx context.Context) {
	entries, err := os.ReadDir(w.dir)
	if err != nil {
		log.Printf("watch: %v", err)
		return
	}
	now := time.Now()
	for _, e := range entries {
		name := e.Name()
		if e.IsDir() || !strings.HasSuffix(name, ".mvd") {
			continue
		}
		info, err := e.Info()
		if err != nil || now.Sub(info.ModTime()) > 10*time.Second {
			continue
		}
		w.mu.Lock()
		_, known := w.matches[name]
		if !known {
			f := &followed{id: fmt.Sprintf("%x", now.UnixNano())[:12], file: name, hub: newHub(), started: now}
			w.matches[name] = f
			go w.follow(ctx, f)
		}
		w.mu.Unlock()
	}
	w.mu.Lock()
	for name, f := range w.matches {
		if !f.ended.IsZero() && now.Sub(f.ended) > w.keep {
			delete(w.matches, name)
		}
	}
	w.mu.Unlock()
}

func (w *watcher) follow(ctx context.Context, f *followed) {
	log.Printf("following %s", f.file)
	t, err := source.OpenTail(ctx, filepath.Join(w.dir, f.file), w.idle)
	if err == nil {
		err = run(ctx, t, nil, f.hub, 0)
		t.Close()
	}
	if err != nil {
		log.Printf("%s: %v", f.file, err)
	}
	f.hub.publish(match.Ended, true)
	w.mu.Lock()
	f.ended = time.Now()
	w.mu.Unlock()
	log.Printf("done with %s", f.file)
}

type listing struct {
	ID        string   `json:"id"`
	Port      string   `json:"port"`
	Map       string   `json:"map"`
	Mode      string   `json:"mode"`
	Status    string   `json:"status"`
	ClockMs   int32    `json:"clockMs"`
	Players   []string `json:"players"`
	Following bool     `json:"following"`
}

func (w *watcher) list() []listing {
	w.mu.Lock()
	defer w.mu.Unlock()
	out := []listing{}
	for _, f := range w.matches {
		port := f.port()
		f.hub.mu.Lock()
		s := f.hub.last
		f.hub.mu.Unlock()
		l := listing{ID: f.id, Port: port, Map: s.Map, Mode: s.Mode, Status: string(s.Status), ClockMs: s.ClockMs, Following: f.ended.IsZero()}
		for _, p := range s.Players {
			l.Players = append(l.Players, p.Name)
		}
		out = append(out, l)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Port < out[j].Port })
	return out
}

// the newest match on a port, or by id
func (w *watcher) find(id, port string) *followed {
	w.mu.Lock()
	all := make([]*followed, 0, len(w.matches))
	for _, f := range w.matches {
		all = append(all, f)
	}
	w.mu.Unlock()
	var best *followed
	for _, f := range all {
		if id != "" && f.id == id {
			return f
		}
		if port != "" && f.port() == port && (best == nil || f.started.After(best.started)) {
			best = f
		}
	}
	return best
}

func (w *watcher) serve(addr string) {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /live", func(rw http.ResponseWriter, r *http.Request) {
		rw.Header().Set("Content-Type", "application/json")
		rw.Header().Set("Access-Control-Allow-Origin", "*")
		json.NewEncoder(rw).Encode(w.list())
	})
	for _, route := range []string{"/live/{id}/", "/live/port/{port}/"} {
		mux.HandleFunc("GET "+route+"{what}", func(rw http.ResponseWriter, r *http.Request) {
			f := w.find(r.PathValue("id"), r.PathValue("port"))
			if f == nil {
				http.Error(rw, "no live match", http.StatusNotFound)
				return
			}
			switch r.PathValue("what") {
			case "state":
				f.hub.serveState(rw, r)
			case "events":
				f.hub.serveEvents(rw, r)
			default:
				http.NotFound(rw, r)
			}
		})
	}
	log.Printf("watching %s, serving /live on %s", w.dir, addr)
	log.Fatal(http.ListenAndServe(addr, mux))
}
