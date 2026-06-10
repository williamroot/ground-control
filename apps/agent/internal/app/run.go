package app

import (
	"errors"
	"log"
	"time"

	"github.com/groundcontrol/gc-agent/internal/client"
	"github.com/groundcontrol/gc-agent/internal/config"
	"github.com/groundcontrol/gc-agent/internal/inventory"
)

// Limites do backoff exponencial usado quando o servidor está indisponível (503/rede).
const (
	initialBackoff = 5 * time.Second
	maxBackoff     = 5 * time.Minute
)

// heartbeater é o subconjunto do client.Client usado no loop (seam de teste).
type heartbeater interface {
	Heartbeat(secret string, specs map[string]string, uptime int) (*client.HeartbeatResult, error)
}

// loopDeps agrega as dependências injetáveis do loop de heartbeat.
type loopDeps struct {
	beater  heartbeater
	collect inventoryFunc
	sleep   func(time.Duration)
	uptime  func() int
}

// loopState é o estado mutável do loop.
type loopState struct {
	secret   string
	interval time.Duration
}

// RunDaemon é o ponto de entrada do subcomando `run` (deps reais).
func RunDaemon(p DaemonParams) int {
	cfg, err := config.Load(p.ConfigPath)
	if err != nil {
		log.Printf("run: erro lendo config %s: %v", p.ConfigPath, err)
		return 1
	}
	if !cfg.HasSecret() {
		log.Printf("run: agente não enrollado (sem agent_secret em %s); rode `gc-agent enroll` primeiro", p.ConfigPath)
		return 1
	}
	server := cfg.Server
	if p.ServerOverride != "" {
		server = p.ServerOverride
	}
	if server == "" {
		log.Printf("run: server não configurado")
		return 1
	}

	start := time.Now()
	deps := loopDeps{
		beater:  client.New(server),
		collect: func() (string, inventory.Specs) { return inventory.Fingerprint(), inventory.Collect() },
		sleep:   time.Sleep,
		uptime:  func() int { return int(time.Since(start).Seconds()) },
	}
	log.Printf("run: iniciando loop de heartbeat (server=%s, intervalo=%ds)", server, cfg.HeartbeatIntervalOrDefault())
	return runLoop(loopState{
		secret:   cfg.AgentSecret,
		interval: time.Duration(cfg.HeartbeatIntervalOrDefault()) * time.Second,
	}, deps)
}

// runLoop bate heartbeat periodicamente. Re-coleta specs a cada ciclo. Em
// ErrUnavailable (503/rede) faz backoff exponencial limitado e continua; em
// ErrRevoked (401) para e loga; o intervalo é atualizado pelo que o servidor manda.
//
// Retorna 0 num encerramento limpo (revogação). É um loop infinito por design
// (serviço); nos testes o fakeBeater encerra via ErrRevoked.
func runLoop(st loopState, deps loopDeps) int {
	backoff := initialBackoff
	for {
		_, specs := deps.collect()
		res, err := deps.beater.Heartbeat(st.secret, specs.AsMap(), deps.uptime())

		switch {
		case err == nil:
			// Sucesso: atualiza o intervalo se o servidor mandou um novo, zera o backoff.
			if res != nil && res.HeartbeatInterval > 0 {
				st.interval = time.Duration(res.HeartbeatInterval) * time.Second
			}
			backoff = initialBackoff
			if res != nil && res.Status != "active" {
				log.Printf("heartbeat: ok (status=%s)", res.Status)
			}
			deps.sleep(st.interval)

		case errors.Is(err, client.ErrRevoked):
			// Credencial revogada no console → encerra o serviço.
			log.Printf("heartbeat: credencial REVOGADA pelo servidor (401); encerrando o agente.")
			return 0

		case errors.Is(err, client.ErrUnavailable):
			// Servidor/GI fora → backoff exponencial limitado, depois tenta de novo.
			log.Printf("heartbeat: servidor indisponível; novo retry em %v", backoff)
			deps.sleep(backoff)
			backoff *= 2
			if backoff > maxBackoff {
				backoff = maxBackoff
			}

		default:
			// Erro inesperado: trata como transitório (backoff) e segue — não derruba o serviço.
			log.Printf("heartbeat: erro inesperado (%v); retry em %v", err, backoff)
			deps.sleep(backoff)
			backoff *= 2
			if backoff > maxBackoff {
				backoff = maxBackoff
			}
		}
	}
}
