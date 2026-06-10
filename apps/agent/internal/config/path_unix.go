//go:build !windows

package config

func defaultPath() string {
	return "/etc/gc-agent/agent.conf"
}
