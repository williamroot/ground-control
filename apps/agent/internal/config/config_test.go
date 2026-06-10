package config

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func TestSaveCreatesDirAndFileWith0600(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "sub", "agent.conf")

	c := &Config{
		Server:            "https://api.example.com",
		AgentID:           "id-123",
		AgentSecret:       "gca_secret",
		HeartbeatInterval: 3600,
	}
	if err := c.Save(path); err != nil {
		t.Fatalf("Save: %v", err)
	}

	info, err := os.Stat(path)
	if err != nil {
		t.Fatalf("stat: %v", err)
	}
	if runtime.GOOS != "windows" {
		if perm := info.Mode().Perm(); perm != 0o600 {
			t.Fatalf("perm = %o, want 0600", perm)
		}
	}
}

func TestLoadRoundTrip(t *testing.T) {
	path := filepath.Join(t.TempDir(), "agent.conf")
	want := &Config{
		Server:            "https://api.example.com",
		AgentID:           "id-123",
		AgentSecret:       "gca_secret",
		HeartbeatInterval: 1800,
	}
	if err := want.Save(path); err != nil {
		t.Fatalf("Save: %v", err)
	}
	got, err := Load(path)
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if got.Server != want.Server || got.AgentID != want.AgentID ||
		got.AgentSecret != want.AgentSecret || got.HeartbeatInterval != want.HeartbeatInterval {
		t.Fatalf("round trip mismatch: got %+v want %+v", got, want)
	}
}

func TestLoadMissingReturnsEmptyConfig(t *testing.T) {
	path := filepath.Join(t.TempDir(), "does-not-exist.conf")
	got, err := Load(path)
	if err != nil {
		t.Fatalf("Load missing should not error, got %v", err)
	}
	if got == nil {
		t.Fatalf("Load missing returned nil config")
	}
	if got.AgentSecret != "" {
		t.Fatalf("expected empty secret, got %q", got.AgentSecret)
	}
}

func TestHasSecret(t *testing.T) {
	if (&Config{}).HasSecret() {
		t.Fatalf("empty config should not have secret")
	}
	if !(&Config{AgentSecret: "gca_x"}).HasSecret() {
		t.Fatalf("config with secret should report HasSecret")
	}
}

func TestHeartbeatIntervalDefault(t *testing.T) {
	c := &Config{}
	if d := c.HeartbeatIntervalOrDefault(); d != DefaultHeartbeatInterval {
		t.Fatalf("default interval = %d, want %d", d, DefaultHeartbeatInterval)
	}
	c.HeartbeatInterval = 42
	if d := c.HeartbeatIntervalOrDefault(); d != 42 {
		t.Fatalf("interval = %d, want 42", d)
	}
}
