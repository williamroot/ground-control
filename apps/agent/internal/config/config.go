// Package config carrega/grava o estado persistente do agente (agent.conf).
//
// O arquivo guarda a credencial de longo prazo (agent_secret) emitida no enroll;
// o enroll_token NUNCA é persistido (chega só por flag no install e é descartado
// após a troca). Por isso o arquivo é gravado com permissão 0600.
package config

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
)

// DefaultHeartbeatInterval é o intervalo (segundos) usado quando o servidor ainda
// não informou um valor (default conservador de 1h, igual ao do sidecar #1R-a).
const DefaultHeartbeatInterval = 3600

// Config é o estado persistente do agente, serializado como JSON em agent.conf.
type Config struct {
	// Server é a base URL do sidecar (ex.: https://api-dev.was.dev.br). Sem barra final.
	Server string `json:"server"`
	// AgentID é o UUID do device retornado no enroll.
	AgentID string `json:"agent_id,omitempty"`
	// AgentSecret é a credencial Bearer de longo prazo (gca_...). Sensível → 0600.
	AgentSecret string `json:"agent_secret,omitempty"`
	// HeartbeatInterval é o intervalo (segundos) que o servidor pediu no último enroll/heartbeat.
	HeartbeatInterval int `json:"heartbeat_interval_seconds,omitempty"`
}

// HasSecret indica se o agente já tem uma credencial de longo prazo (já fez enroll).
func (c *Config) HasSecret() bool {
	return c != nil && c.AgentSecret != ""
}

// HeartbeatIntervalOrDefault retorna o intervalo configurado ou o default.
func (c *Config) HeartbeatIntervalOrDefault() int {
	if c == nil || c.HeartbeatInterval <= 0 {
		return DefaultHeartbeatInterval
	}
	return c.HeartbeatInterval
}

// Load lê agent.conf de path. Arquivo ausente NÃO é erro: retorna um Config vazio
// (estado "ainda não enrollado").
func Load(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return &Config{}, nil
		}
		return nil, err
	}
	c := &Config{}
	if len(data) == 0 {
		return c, nil
	}
	if err := json.Unmarshal(data, c); err != nil {
		return nil, err
	}
	return c, nil
}

// Save grava agent.conf em path, criando o diretório pai se preciso, com perm 0600
// (a credencial é sensível). A gravação é atômica (tmp + rename) para não corromper
// o arquivo se o processo morrer no meio.
func (c *Config) Save(path string) error {
	dir := filepath.Dir(path)
	if dir != "" && dir != "." {
		if err := os.MkdirAll(dir, 0o700); err != nil {
			return err
		}
	}
	data, err := json.MarshalIndent(c, "", "  ")
	if err != nil {
		return err
	}
	data = append(data, '\n')

	tmp, err := os.CreateTemp(dir, ".agent.conf.*")
	if err != nil {
		return err
	}
	tmpName := tmp.Name()
	defer os.Remove(tmpName) // no-op se o rename já consumiu o arquivo

	if err := tmp.Chmod(0o600); err != nil {
		tmp.Close()
		return err
	}
	if _, err := tmp.Write(data); err != nil {
		tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	if err := os.Rename(tmpName, path); err != nil {
		return err
	}
	// Garante a permissão final mesmo se um umask interferiu no destino.
	return os.Chmod(path, 0o600)
}

// DefaultPath retorna o caminho padrão do agent.conf por SO. Pode ser sobreposto
// pela flag --config. Em Linux/macOS: /etc/gc-agent/agent.conf; em Windows:
// %ProgramData%\gc-agent\agent.conf (com fallback para o diretório de trabalho).
func DefaultPath() string {
	return defaultPath()
}
