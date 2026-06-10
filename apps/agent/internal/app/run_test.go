package app

import (
	"sync"
	"testing"
	"time"

	"github.com/groundcontrol/gc-agent/internal/client"
	"github.com/groundcontrol/gc-agent/internal/inventory"
)

// fakeBeater implementa heartbeater; cada chamada consome um passo do roteiro.
type fakeBeater struct {
	mu      sync.Mutex
	results []hbStep
	calls   int
	secrets []string
}

type hbStep struct {
	res *client.HeartbeatResult
	err error
}

func (f *fakeBeater) Heartbeat(secret string, specs map[string]string, uptime int) (*client.HeartbeatResult, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	i := f.calls
	f.calls++
	f.secrets = append(f.secrets, secret)
	if i >= len(f.results) {
		// Sem mais passos: devolve revogado p/ encerrar o loop e não rodar infinito.
		return nil, client.ErrRevoked
	}
	s := f.results[i]
	return s.res, s.err
}

func okStep() hbStep {
	return hbStep{res: &client.HeartbeatResult{OK: true, Status: "active", HeartbeatInterval: 10}}
}

func newLoopDeps(b heartbeater, sleeps *[]time.Duration) loopDeps {
	var mu sync.Mutex
	return loopDeps{
		beater: b,
		collect: func() (string, inventory.Specs) {
			return "fp", inventory.Specs{Hostname: "h", OperatingSystem: "linux"}
		},
		sleep: func(d time.Duration) {
			mu.Lock()
			*sleeps = append(*sleeps, d)
			mu.Unlock()
		},
		uptime: func() int { return 1 },
	}
}

func TestRunLoopStopsOnRevoked(t *testing.T) {
	b := &fakeBeater{results: []hbStep{okStep(), okStep(), {err: client.ErrRevoked}}}
	var sleeps []time.Duration
	code := runLoop(loopState{secret: "gca_x", interval: 10 * time.Second}, newLoopDeps(b, &sleeps))
	if code != 0 {
		t.Fatalf("revoked should exit 0 (clean stop), got %d", code)
	}
	if b.calls != 3 {
		t.Fatalf("expected 3 heartbeats before revoked, got %d", b.calls)
	}
}

func TestRunLoopBacksOffOnUnavailableThenContinues(t *testing.T) {
	// 1º OK (sleep=interval), depois 2 indisponíveis (sleeps de backoff crescente),
	// depois OK (sleep volta ao interval), depois revogado para.
	b := &fakeBeater{results: []hbStep{
		okStep(),
		{err: client.ErrUnavailable},
		{err: client.ErrUnavailable},
		okStep(),
		{err: client.ErrRevoked},
	}}
	var sleeps []time.Duration
	runLoop(loopState{secret: "s", interval: 10 * time.Second}, newLoopDeps(b, &sleeps))

	if len(sleeps) < 4 {
		t.Fatalf("expected at least 4 sleeps, got %d: %v", len(sleeps), sleeps)
	}
	// sleeps[0] após OK = intervalo normal.
	if sleeps[0] != 10*time.Second {
		t.Fatalf("first sleep should be interval (10s), got %v", sleeps[0])
	}
	// sleeps[1] e sleeps[2] são backoff e devem crescer (exponencial).
	if !(sleeps[1] < sleeps[2]) {
		t.Fatalf("backoff should grow: %v then %v", sleeps[1], sleeps[2])
	}
	// backoff não deve ser o intervalo normal (deve começar menor e crescer, limitado).
	if sleeps[1] >= 10*time.Second {
		t.Fatalf("first backoff should be below interval, got %v", sleeps[1])
	}
}

func TestRunLoopUpdatesIntervalFromServer(t *testing.T) {
	// Servidor responde com novo intervalo (10s); o próximo sleep usa 10s.
	b := &fakeBeater{results: []hbStep{
		{res: &client.HeartbeatResult{OK: true, Status: "active", HeartbeatInterval: 10}},
		{err: client.ErrRevoked},
	}}
	var sleeps []time.Duration
	runLoop(loopState{secret: "s", interval: 99 * time.Second}, newLoopDeps(b, &sleeps))
	if len(sleeps) < 1 || sleeps[0] != 10*time.Second {
		t.Fatalf("expected server-provided interval 10s as first sleep, got %v", sleeps)
	}
}

func TestRunLoopBackoffCapped(t *testing.T) {
	steps := []hbStep{}
	for i := 0; i < 20; i++ {
		steps = append(steps, hbStep{err: client.ErrUnavailable})
	}
	steps = append(steps, hbStep{err: client.ErrRevoked})
	b := &fakeBeater{results: steps}
	var sleeps []time.Duration
	runLoop(loopState{secret: "s", interval: 10 * time.Second}, newLoopDeps(b, &sleeps))
	for _, d := range sleeps {
		if d > maxBackoff {
			t.Fatalf("backoff exceeded cap %v: %v", maxBackoff, d)
		}
	}
}
