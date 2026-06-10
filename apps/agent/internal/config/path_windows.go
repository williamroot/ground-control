//go:build windows

package config

import (
	"os"
	"path/filepath"
)

func defaultPath() string {
	base := os.Getenv("ProgramData")
	if base == "" {
		base = "."
	}
	return filepath.Join(base, "gc-agent", "agent.conf")
}
