package inventory

import (
	"strings"
	"testing"
)

func TestCollectReturnsHostnameAndOS(t *testing.T) {
	s := Collect()
	if s.Hostname == "" {
		t.Fatalf("hostname should not be empty")
	}
	if s.OperatingSystem == "" {
		t.Fatalf("operating_system should not be empty")
	}
}

func TestFingerprintStableAcrossCalls(t *testing.T) {
	a := Fingerprint()
	b := Fingerprint()
	if a == "" {
		t.Fatalf("fingerprint should not be empty")
	}
	if a != b {
		t.Fatalf("fingerprint not deterministic: %q != %q", a, b)
	}
}

func TestFingerprintIsHashedNotRaw(t *testing.T) {
	// A fonte crua não deve vazar: o fingerprint é um sha256 hex (64 chars).
	fp := fingerprintFrom([]source{
		{name: "machine-id", read: func() (string, bool) { return "abc-raw-machine-id", true }},
	})
	if fp == "abc-raw-machine-id" {
		t.Fatalf("fingerprint leaked the raw source")
	}
	if len(fp) != 64 {
		t.Fatalf("fingerprint should be sha256 hex (64 chars), got %d: %q", len(fp), fp)
	}
	for _, c := range fp {
		if !strings.ContainsRune("0123456789abcdef", c) {
			t.Fatalf("fingerprint not lowercase hex: %q", fp)
		}
	}
}

func TestFingerprintPrefersFirstAvailableSource(t *testing.T) {
	srcs := []source{
		{name: "empty", read: func() (string, bool) { return "", false }},
		{name: "first", read: func() (string, bool) { return "FIRST", true }},
		{name: "second", read: func() (string, bool) { return "SECOND", true }},
	}
	got := fingerprintFrom(srcs)
	want := fingerprintFrom([]source{{name: "x", read: func() (string, bool) { return "FIRST", true }}})
	if got != want {
		t.Fatalf("did not prefer first available source: %q != %q", got, want)
	}
}

func TestFingerprintNormalizesWhitespaceAndCase(t *testing.T) {
	a := fingerprintFrom([]source{{read: func() (string, bool) { return "  ABCdef\n", true }}})
	b := fingerprintFrom([]source{{read: func() (string, bool) { return "abcdef", true }}})
	if a != b {
		t.Fatalf("expected normalization to make these equal: %q != %q", a, b)
	}
}

func TestFingerprintFallbackWhenNoSource(t *testing.T) {
	// Sem nenhuma fonte disponível, cai no fallback (hostname+MACs); ainda assim
	// retorna um hash não-vazio determinístico.
	fp := fingerprintFrom(nil)
	if len(fp) != 64 {
		t.Fatalf("fallback fingerprint should be sha256 hex, got %q", fp)
	}
	fp2 := fingerprintFrom(nil)
	if fp != fp2 {
		t.Fatalf("fallback fingerprint not deterministic")
	}
}

func TestSpecsAsMapHasContractFields(t *testing.T) {
	s := Specs{
		CPU: "x", Memory: "y", Disk: "z", Serial: "sn",
		Vendor: "v", Model: "m", OperatingSystem: "os",
	}
	m := s.AsMap()
	for _, k := range []string{"cpu", "memory", "disk", "serial", "vendor", "model", "operating_system"} {
		if _, ok := m[k]; !ok {
			t.Fatalf("AsMap missing key %q", k)
		}
	}
}
