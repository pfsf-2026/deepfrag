package main

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"sync"
	"time"

	"deepfrag/live/source"
)

// live qtv streams for the app: GET /qtv/{stream}/events (and /state), stream as
// api.quake.world lists it ("7@dm6.uk:28000"). One relay connection per stream however many
// watch; it closes a minute after the last viewer leaves. Only streams in the hub's server
// list are followed, so this is not an open proxy to any host.
type qtvStreams struct {
	mu      sync.Mutex
	streams map[string]*qtvStream
	known   map[string]bool
	knownAt time.Time
}

type qtvStream struct {
	hub      *hub
	cancel   context.CancelFunc
	lastSeen time.Time
}

func newQTVStreams() *qtvStreams {
	q := &qtvStreams{streams: map[string]*qtvStream{}}
	go q.reap()
	return q
}

func (q *qtvStreams) listed(stream string) bool {
	q.mu.Lock()
	fresh := time.Since(q.knownAt) < 30*time.Second
	q.mu.Unlock()
	if !fresh {
		req, _ := http.NewRequest("GET", "https://api.quake.world/v1/servers?server_type=game", nil)
		req.Header.Set("User-Agent", "DeepFrag-live/0.1")
		resp, err := http.DefaultClient.Do(req)
		if err == nil {
			var servers []struct {
				QtvStream *struct {
					URL string `json:"url"`
				} `json:"qtv_stream"`
			}
			if json.NewDecoder(resp.Body).Decode(&servers) == nil {
				known := map[string]bool{}
				for _, s := range servers {
					if s.QtvStream != nil {
						known[s.QtvStream.URL] = true
					}
				}
				q.mu.Lock()
				q.known, q.knownAt = known, time.Now()
				q.mu.Unlock()
			}
			resp.Body.Close()
		}
	}
	q.mu.Lock()
	defer q.mu.Unlock()
	return q.known[stream]
}

func (q *qtvStreams) get(stream string) *qtvStream {
	q.mu.Lock()
	defer q.mu.Unlock()
	if s := q.streams[stream]; s != nil {
		s.lastSeen = time.Now()
		return s
	}
	ctx, cancel := context.WithCancel(context.Background())
	s := &qtvStream{hub: newHub(), cancel: cancel, lastSeen: time.Now()}
	q.streams[stream] = s
	go func() {
		defer func() {
			q.mu.Lock()
			if q.streams[stream] == s {
				delete(q.streams, stream)
			}
			q.mu.Unlock()
			s.hub.publish("", true)
		}()
		log.Printf("qtv %s: connecting", stream)
		r, err := source.QTV(ctx, stream)
		if err != nil {
			log.Printf("qtv %s: %v", stream, err)
			return
		}
		defer r.Close()
		if err := run(ctx, r, nil, s.hub, 0); err != nil {
			log.Printf("qtv %s: %v", stream, err)
		}
		log.Printf("qtv %s: closed", stream)
	}()
	return s
}

// close streams nobody has watched for a minute
func (q *qtvStreams) reap() {
	for range time.Tick(10 * time.Second) {
		q.mu.Lock()
		for name, s := range q.streams {
			s.hub.mu.Lock()
			watched := len(s.hub.subs) > 0
			s.hub.mu.Unlock()
			if watched {
				s.lastSeen = time.Now()
			} else if time.Since(s.lastSeen) > time.Minute {
				s.cancel()
				delete(q.streams, name)
			}
		}
		q.mu.Unlock()
	}
}

func (q *qtvStreams) register(mux *http.ServeMux) {
	mux.HandleFunc("GET /qtv/{stream}/{what}", func(w http.ResponseWriter, r *http.Request) {
		stream := r.PathValue("stream")
		if !q.listed(stream) {
			http.Error(w, "not a qtv stream on the hub", http.StatusNotFound)
			return
		}
		s := q.get(stream)
		switch r.PathValue("what") {
		case "state":
			s.hub.serveState(w, r)
		case "events":
			s.hub.serveEvents(w, r)
		default:
			http.NotFound(w, r)
		}
	})
}
