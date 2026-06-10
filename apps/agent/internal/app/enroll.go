package app

import (
	"errors"
	"log"

	"github.com/groundcontrol/gc-agent/internal/client"
	"github.com/groundcontrol/gc-agent/internal/config"
	"github.com/groundcontrol/gc-agent/internal/inventory"
)

// enroller é o subconjunto do client.Client usado no enroll (seam de teste).
type enroller interface {
	Enroll(token, fingerprint, hostname, os string, specs map[string]string) (*client.EnrollResult, error)
}

// inventoryFunc coleta (fingerprint, specs) — injetável nos testes.
type inventoryFunc func() (string, inventory.Specs)

// enrollDeps agrega as dependências injetáveis do enroll.
type enrollDeps struct {
	newClient func(server string) enroller
	collect   inventoryFunc
}

// defaultEnrollDeps usa o cliente HTTP real e a coleta real de inventário.
func defaultEnrollDeps() enrollDeps {
	return enrollDeps{
		newClient: func(server string) enroller { return client.New(server) },
		collect: func() (string, inventory.Specs) {
			return inventory.Fingerprint(), inventory.Collect()
		},
	}
}

// RunEnroll é o ponto de entrada do subcomando `enroll` (usa deps reais).
func RunEnroll(p EnrollParams) int {
	return runEnroll(p, defaultEnrollDeps())
}

// runEnroll é a versão testável: coleta specs+fingerprint, troca o enroll token por
// uma credencial própria, grava agent_id+agent_secret (0600) e NÃO persiste o token.
//
// Exit codes: 0 = sucesso (active ou pending) ou já-enrollado (idempotente);
// !=0 = 401 (token inválido), indisponível, ou falha ao gravar.
func runEnroll(p EnrollParams, deps enrollDeps) int {
	cfg, err := config.Load(p.ConfigPath)
	if err != nil {
		log.Printf("enroll: erro lendo config %s: %v", p.ConfigPath, err)
		return 1
	}

	// Idempotência: se já há credencial e não é --force, não re-enrolla.
	if cfg.HasSecret() && !p.Force {
		log.Printf("enroll: já existe credencial em %s; use --force para re-enrollar", p.ConfigPath)
		return 0
	}

	fingerprint, specs := deps.collect()
	cl := deps.newClient(p.Server)

	res, err := cl.Enroll(p.EnrollToken, fingerprint, specs.Hostname, specs.OperatingSystem, specs.AsMap())
	if err != nil {
		switch {
		case errors.Is(err, client.ErrUnauthorized):
			log.Printf("enroll: token de enrollment inválido/desabilitado (401)")
		case errors.Is(err, client.ErrUnavailable):
			log.Printf("enroll: servidor indisponível (503/rede); tente novamente mais tarde")
		default:
			log.Printf("enroll: falha: %v", err)
		}
		return 1
	}

	// Grava a credencial de longo prazo. O enroll_token é DESCARTADO (nunca vai pro disco).
	cfg.Server = p.Server
	cfg.AgentID = res.AgentID
	cfg.AgentSecret = res.AgentSecret
	if res.HeartbeatInterval > 0 {
		cfg.HeartbeatInterval = res.HeartbeatInterval
	}
	if err := cfg.Save(p.ConfigPath); err != nil {
		log.Printf("enroll: falha ao gravar %s: %v", p.ConfigPath, err)
		return 1
	}

	switch res.Status {
	case "pending":
		log.Printf("enroll: registrado como PENDING — aguardando aprovação do operador no console. " +
			"O agente só entrará no inventário após a aprovação; o heartbeat passará a valer então.")
	default:
		log.Printf("enroll: OK (status=%s, agent_id=%s, heartbeat=%ds). Credencial gravada em %s.",
			res.Status, res.AgentID, cfg.HeartbeatIntervalOrDefault(), p.ConfigPath)
	}
	return 0
}
