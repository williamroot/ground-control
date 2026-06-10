package client

import (
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func specs() map[string]string {
	return map[string]string{
		"cpu": "x", "memory": "y", "disk": "z", "serial": "sn",
		"vendor": "v", "model": "m", "operating_system": "os",
	}
}

func TestEnrollActive201(t *testing.T) {
	var gotBody map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/agent/enroll" {
			t.Errorf("path = %s", r.URL.Path)
		}
		if r.Header.Get("Authorization") != "Bearer enroll-tok" {
			t.Errorf("authz = %q", r.Header.Get("Authorization"))
		}
		b, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(b, &gotBody)
		w.WriteHeader(201)
		_, _ = w.Write([]byte(`{"agent_id":"uuid-1","agent_secret":"gca_abc","status":"active","heartbeat_interval_seconds":1800}`))
	}))
	defer srv.Close()

	c := New(srv.URL)
	res, err := c.Enroll("enroll-tok", "fp-123", "host-a", "linux", specs())
	if err != nil {
		t.Fatalf("Enroll: %v", err)
	}
	if res.AgentID != "uuid-1" || res.AgentSecret != "gca_abc" || res.Status != "active" {
		t.Fatalf("unexpected result: %+v", res)
	}
	if res.HeartbeatInterval != 1800 {
		t.Fatalf("hb interval = %d", res.HeartbeatInterval)
	}
	// Confere o shape do body enviado (contrato #1R-a).
	if gotBody["fingerprint"] != "fp-123" || gotBody["hostname"] != "host-a" || gotBody["os"] != "linux" {
		t.Fatalf("body fields wrong: %+v", gotBody)
	}
	sp, ok := gotBody["specs"].(map[string]any)
	if !ok || sp["cpu"] != "x" {
		t.Fatalf("specs not nested correctly: %+v", gotBody["specs"])
	}
}

func TestEnrollPending202(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(202)
		_, _ = w.Write([]byte(`{"agent_id":"uuid-2","agent_secret":"gca_xyz","status":"pending","heartbeat_interval_seconds":3600}`))
	}))
	defer srv.Close()

	res, err := New(srv.URL).Enroll("t", "fp", "h", "linux", specs())
	if err != nil {
		t.Fatalf("Enroll pending should not error: %v", err)
	}
	if res.Status != "pending" {
		t.Fatalf("status = %q, want pending", res.Status)
	}
}

func TestEnroll401Unauthorized(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(401)
		_, _ = w.Write([]byte(`{"detail":"invalid_enroll_token"}`))
	}))
	defer srv.Close()

	_, err := New(srv.URL).Enroll("bad", "fp", "h", "linux", specs())
	if !errors.Is(err, ErrUnauthorized) {
		t.Fatalf("err = %v, want ErrUnauthorized", err)
	}
}

func TestHeartbeatOK200(t *testing.T) {
	var gotBody map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/agent/heartbeat" {
			t.Errorf("path = %s", r.URL.Path)
		}
		if r.Header.Get("Authorization") != "Bearer gca_abc" {
			t.Errorf("authz = %q", r.Header.Get("Authorization"))
		}
		b, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(b, &gotBody)
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"ok":true,"status":"active","heartbeat_interval_seconds":900}`))
	}))
	defer srv.Close()

	res, err := New(srv.URL).Heartbeat("gca_abc", specs(), 42)
	if err != nil {
		t.Fatalf("Heartbeat: %v", err)
	}
	if !res.OK || res.Status != "active" || res.HeartbeatInterval != 900 {
		t.Fatalf("unexpected: %+v", res)
	}
	if gotBody["uptime_seconds"].(float64) != 42 {
		t.Fatalf("uptime not sent: %+v", gotBody)
	}
	sp, ok := gotBody["specs"].(map[string]any)
	if !ok || sp["cpu"] != "x" {
		t.Fatalf("specs not nested: %+v", gotBody)
	}
}

func TestHeartbeat401Revoked(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(401)
	}))
	defer srv.Close()

	_, err := New(srv.URL).Heartbeat("revoked", specs(), 0)
	if !errors.Is(err, ErrRevoked) {
		t.Fatalf("err = %v, want ErrRevoked", err)
	}
}

func TestHeartbeat503Unavailable(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(503)
	}))
	defer srv.Close()

	_, err := New(srv.URL).Heartbeat("s", specs(), 0)
	if !errors.Is(err, ErrUnavailable) {
		t.Fatalf("err = %v, want ErrUnavailable", err)
	}
}

func TestServerURLTrailingSlashTrimmed(t *testing.T) {
	c := New("https://api.example.com/")
	if strings.HasSuffix(c.server, "/") {
		t.Fatalf("trailing slash not trimmed: %q", c.server)
	}
}
