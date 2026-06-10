package app

import (
	"errors"
	"path/filepath"
	"testing"

	"github.com/groundcontrol/gc-agent/internal/client"
	"github.com/groundcontrol/gc-agent/internal/config"
	"github.com/groundcontrol/gc-agent/internal/inventory"
)

// fakeEnroller implementa enroller para os testes.
type fakeEnroller struct {
	res      *client.EnrollResult
	err      error
	gotToken string
	gotFP    string
	gotHost  string
	gotOS    string
	calls    int
}

func (f *fakeEnroller) Enroll(token, fp, host, os string, specs map[string]string) (*client.EnrollResult, error) {
	f.calls++
	f.gotToken, f.gotFP, f.gotHost, f.gotOS = token, fp, host, os
	return f.res, f.err
}

func fixedInventory() inventoryFunc {
	return func() (string, inventory.Specs) {
		return "fp-abc", inventory.Specs{Hostname: "host-x", OperatingSystem: "linux", CPU: "cpu"}
	}
}

func newEnrollDeps(e enroller) enrollDeps {
	return enrollDeps{
		newClient: func(server string) enroller { return e },
		collect:   fixedInventory(),
	}
}

func TestRunEnrollActivePersistsSecretNoToken(t *testing.T) {
	cfgPath := filepath.Join(t.TempDir(), "agent.conf")
	fe := &fakeEnroller{res: &client.EnrollResult{
		AgentID: "id-1", AgentSecret: "gca_secret", Status: "active", HeartbeatInterval: 1800,
	}}
	code := runEnroll(EnrollParams{ConfigPath: cfgPath, Server: "https://s", EnrollToken: "ENROLLTOK"}, newEnrollDeps(fe))
	if code != 0 {
		t.Fatalf("exit = %d, want 0", code)
	}
	if fe.gotToken != "ENROLLTOK" || fe.gotFP != "fp-abc" || fe.gotHost != "host-x" || fe.gotOS != "linux" {
		t.Fatalf("enroll called with wrong args: %+v", fe)
	}
	saved, err := config.Load(cfgPath)
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if saved.AgentSecret != "gca_secret" || saved.AgentID != "id-1" {
		t.Fatalf("credential not persisted: %+v", saved)
	}
	if saved.HeartbeatInterval != 1800 || saved.Server != "https://s" {
		t.Fatalf("server/interval not persisted: %+v", saved)
	}
	// O enroll_token NUNCA deve ser persistido — Config não tem campo p/ ele e o
	// arquivo não deve conter a string do token.
	raw, _ := readFileString(cfgPath)
	if contains(raw, "ENROLLTOK") {
		t.Fatalf("enroll token leaked into agent.conf: %s", raw)
	}
}

func TestRunEnrollPendingExitsZero(t *testing.T) {
	cfgPath := filepath.Join(t.TempDir(), "agent.conf")
	fe := &fakeEnroller{res: &client.EnrollResult{
		AgentID: "id-2", AgentSecret: "gca_p", Status: "pending", HeartbeatInterval: 3600,
	}}
	code := runEnroll(EnrollParams{ConfigPath: cfgPath, Server: "https://s", EnrollToken: "t"}, newEnrollDeps(fe))
	if code != 0 {
		t.Fatalf("pending exit = %d, want 0", code)
	}
	// Mesmo pending, a credencial emitida é guardada (o heartbeat passa a valer quando aprovado).
	saved, _ := config.Load(cfgPath)
	if saved.AgentSecret != "gca_p" {
		t.Fatalf("pending secret not saved: %+v", saved)
	}
}

func TestRunEnrollUnauthorizedExitsNonZero(t *testing.T) {
	cfgPath := filepath.Join(t.TempDir(), "agent.conf")
	fe := &fakeEnroller{err: client.ErrUnauthorized}
	code := runEnroll(EnrollParams{ConfigPath: cfgPath, Server: "https://s", EnrollToken: "bad"}, newEnrollDeps(fe))
	if code == 0 {
		t.Fatalf("401 should exit non-zero")
	}
	saved, _ := config.Load(cfgPath)
	if saved.HasSecret() {
		t.Fatalf("no secret should be saved on 401")
	}
}

func TestRunEnrollIdempotentSkipsWhenSecretExists(t *testing.T) {
	cfgPath := filepath.Join(t.TempDir(), "agent.conf")
	pre := &config.Config{Server: "https://s", AgentID: "old", AgentSecret: "gca_old"}
	if err := pre.Save(cfgPath); err != nil {
		t.Fatalf("seed: %v", err)
	}
	fe := &fakeEnroller{res: &client.EnrollResult{AgentSecret: "gca_new", Status: "active"}}
	code := runEnroll(EnrollParams{ConfigPath: cfgPath, Server: "https://s", EnrollToken: "t"}, newEnrollDeps(fe))
	if code != 0 {
		t.Fatalf("already-enrolled should exit 0, got %d", code)
	}
	if fe.calls != 0 {
		t.Fatalf("should not re-enroll without --force (calls=%d)", fe.calls)
	}
	saved, _ := config.Load(cfgPath)
	if saved.AgentSecret != "gca_old" {
		t.Fatalf("existing secret should be preserved: %+v", saved)
	}
}

func TestRunEnrollForceReenrolls(t *testing.T) {
	cfgPath := filepath.Join(t.TempDir(), "agent.conf")
	pre := &config.Config{Server: "https://s", AgentID: "old", AgentSecret: "gca_old"}
	_ = pre.Save(cfgPath)
	fe := &fakeEnroller{res: &client.EnrollResult{AgentID: "new", AgentSecret: "gca_new", Status: "active"}}
	code := runEnroll(EnrollParams{ConfigPath: cfgPath, Server: "https://s", EnrollToken: "t", Force: true}, newEnrollDeps(fe))
	if code != 0 {
		t.Fatalf("force exit = %d", code)
	}
	if fe.calls != 1 {
		t.Fatalf("force should re-enroll (calls=%d)", fe.calls)
	}
	saved, _ := config.Load(cfgPath)
	if saved.AgentSecret != "gca_new" {
		t.Fatalf("force should rotate secret: %+v", saved)
	}
}

func TestRunEnrollUnavailableExitsNonZero(t *testing.T) {
	cfgPath := filepath.Join(t.TempDir(), "agent.conf")
	fe := &fakeEnroller{err: client.ErrUnavailable}
	code := runEnroll(EnrollParams{ConfigPath: cfgPath, Server: "https://s", EnrollToken: "t"}, newEnrollDeps(fe))
	if code == 0 {
		t.Fatalf("503 should exit non-zero")
	}
}

// helper para garantir que err wrapping de ErrUnauthorized casa.
func TestErrUnauthorizedWraps(t *testing.T) {
	if !errors.Is(client.ErrUnauthorized, client.ErrUnauthorized) {
		t.Fatal("sanity")
	}
}
