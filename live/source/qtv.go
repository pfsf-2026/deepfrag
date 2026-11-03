package source

import (
	"bufio"
	"context"
	"fmt"
	"io"
	"net"
	"strings"
	"time"
)

// QTV connects to a QTV proxy and returns its stream: the raw MVD of the match it relays.
// stream is a qtv_stream url as api.quake.world lists it, "7@dm6.uk:28000" (stream 7 on that
// proxy). The proxy answers "QTVSV 1" then BEGIN (or PERROR/TERROR) and a blank line, then
// sends MVD exactly as a demo file has it, continuing across map changes.
func QTV(ctx context.Context, stream string) (io.ReadCloser, error) {
	source, addr, ok := strings.Cut(stream, "@")
	if !ok {
		source, addr = "", stream
	}
	dialer := net.Dialer{Timeout: 10 * time.Second}
	conn, err := dialer.DialContext(ctx, "tcp", addr)
	if err != nil {
		return nil, err
	}
	request := "QTV\nVERSION: 1.0\nRAW: 1\n"
	if source != "" {
		request += "SOURCE: " + source + "\n"
	}
	if _, err := io.WriteString(conn, request+"\n"); err != nil {
		conn.Close()
		return nil, err
	}
	conn.SetReadDeadline(time.Now().Add(15 * time.Second))
	r := bufio.NewReader(conn)
	first := true
	for {
		line, err := r.ReadString('\n')
		if err != nil {
			conn.Close()
			return nil, fmt.Errorf("qtv handshake: %w", err)
		}
		line = strings.TrimRight(line, "\r\n")
		if first {
			if !strings.HasPrefix(line, "QTVSV") {
				conn.Close()
				return nil, fmt.Errorf("not a qtv proxy: %q", line)
			}
			first = false
			continue
		}
		if line == "" {
			break
		}
		if key, value, _ := strings.Cut(line, ":"); key == "PERROR" || key == "TERROR" {
			conn.Close()
			return nil, fmt.Errorf("qtv: %s", strings.TrimSpace(value))
		}
	}
	conn.SetReadDeadline(time.Time{})
	return &qtvConn{Reader: r, conn: conn, ctx: ctx}, nil
}

type qtvConn struct {
	*bufio.Reader
	conn net.Conn
	ctx  context.Context
}

func (q *qtvConn) Read(p []byte) (int, error) {
	if q.ctx.Err() != nil {
		return 0, io.EOF
	}
	// a relay that goes quiet for a minute has dropped us
	q.conn.SetReadDeadline(time.Now().Add(60 * time.Second))
	return q.Reader.Read(p)
}

func (q *qtvConn) Close() error { return q.conn.Close() }
