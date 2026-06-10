// Command gc-agent é o agente de inventário do Ground Control (Spec #1R-b).
//
// Subcomandos:
//
//	gc-agent enroll --server <url> --enroll-token <tok> [--config <path>] [--force]
//	    coleta specs+fingerprint, troca o enroll token por uma credencial própria
//	    (agent_secret) e a grava em agent.conf (0600). O enroll token NÃO é persistido.
//
//	gc-agent run [--config <path>] [--server <url>]
//	    loop de heartbeat periódico (rodado como serviço systemd / Windows service).
//
// Sem dependências de runtime na máquina do cliente: binário estático cross-platform.
package main

import (
	"flag"
	"fmt"
	"os"

	"github.com/groundcontrol/gc-agent/internal/app"
	"github.com/groundcontrol/gc-agent/internal/config"
)

func usage() {
	fmt.Fprintf(os.Stderr, `gc-agent — agente de inventário do Ground Control

uso:
  gc-agent enroll --server <url> --enroll-token <token> [--config <path>] [--force]
  gc-agent run [--config <path>] [--server <url>]

`)
}

func main() {
	os.Exit(run(os.Args[1:]))
}

// run é o ponto de entrada testável (sem os.Exit). Retorna o exit code.
func run(args []string) int {
	if len(args) < 1 {
		usage()
		return 2
	}

	switch args[0] {
	case "enroll":
		return cmdEnroll(args[1:])
	case "run":
		return cmdRun(args[1:])
	case "-h", "--help", "help":
		usage()
		return 0
	default:
		fmt.Fprintf(os.Stderr, "subcomando desconhecido: %q\n\n", args[0])
		usage()
		return 2
	}
}

func cmdEnroll(args []string) int {
	fs := flag.NewFlagSet("enroll", flag.ContinueOnError)
	server := fs.String("server", "", "base URL do sidecar (ex.: https://api-dev.was.dev.br)")
	enrollToken := fs.String("enroll-token", "", "token de enrollment (descartado após a troca)")
	cfgPath := fs.String("config", config.DefaultPath(), "caminho do agent.conf")
	force := fs.Bool("force", false, "re-enrolla mesmo se já houver credencial")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if *server == "" || *enrollToken == "" {
		fmt.Fprintln(os.Stderr, "enroll: --server e --enroll-token são obrigatórios")
		return 2
	}
	return app.RunEnroll(app.EnrollParams{
		ConfigPath:  *cfgPath,
		Server:      *server,
		EnrollToken: *enrollToken,
		Force:       *force,
	})
}

func cmdRun(args []string) int {
	fs := flag.NewFlagSet("run", flag.ContinueOnError)
	cfgPath := fs.String("config", config.DefaultPath(), "caminho do agent.conf")
	server := fs.String("server", "", "sobrepõe o server do agent.conf (opcional)")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	return app.RunDaemon(app.DaemonParams{
		ConfigPath:     *cfgPath,
		ServerOverride: *server,
	})
}
