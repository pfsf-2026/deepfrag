// Package source feeds MVD bytes to the parser: a demo file that is still being written
// (mvdsv records the match to ktx/demos/ as it is played), or a finished file.
package source

import (
	"context"
	"errors"
	"io"
	"os"
	"time"
)

// Tail reads a file that another process is still appending to. At the end of the data it
// waits for more instead of returning io.EOF, until the file has not grown for idle (the
// recording has stopped) or ctx ends.
type Tail struct {
	ctx   context.Context
	file  *os.File
	idle  time.Duration
	poll  time.Duration
	lastN time.Time
}

func OpenTail(ctx context.Context, path string, idle time.Duration) (*Tail, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	return &Tail{ctx: ctx, file: f, idle: idle, poll: 200 * time.Millisecond, lastN: time.Now()}, nil
}

func (t *Tail) Read(p []byte) (int, error) {
	for {
		n, err := t.file.Read(p)
		if n > 0 {
			t.lastN = time.Now()
			return n, nil
		}
		if err != nil && !errors.Is(err, io.EOF) {
			return 0, err
		}
		if time.Since(t.lastN) > t.idle {
			return 0, io.EOF
		}
		select {
		case <-t.ctx.Done():
			return 0, io.EOF
		case <-time.After(t.poll):
		}
	}
}

func (t *Tail) Close() error { return t.file.Close() }
