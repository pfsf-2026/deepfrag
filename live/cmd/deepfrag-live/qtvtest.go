package main

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"deepfrag/live/match"
	"deepfrag/live/source"
)

// qtvprobe: follow a qtv stream for a while and print the state every 5 s
func runQTVProbe(ctx context.Context, stream string, d time.Duration) error {
	ctx, cancel := context.WithTimeout(ctx, d)
	defer cancel()
	r, err := source.QTV(ctx, stream)
	if err != nil {
		return err
	}
	defer r.Close()
	h := newHub()
	go func() {
		for ctx.Err() == nil {
			time.Sleep(5 * time.Second)
			h.mu.Lock()
			s := h.last
			h.mu.Unlock()
			out, _ := json.Marshal(struct {
				Map, Mode, Status string
				Clock             int32
				Players           []string
				Items             int
				Feed              int
			}{s.Map, s.Mode, string(s.Status), s.ClockMs / 1000, names(s), len(s.Items), len(s.Feed)})
			fmt.Println(string(out))
		}
	}()
	return run(ctx, r, nil, h, 0)
}

func names(s match.Snapshot) []string {
	var out []string
	for _, p := range s.Players {
		out = append(out, fmt.Sprintf("%s %d %d/%d%s", p.Name, p.Frags, p.Health, p.Armor, p.ArmorType))
	}
	return out
}
