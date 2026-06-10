// Package app orquestra os subcomandos do agente (enroll e run), conectando
// config + inventory + client. As implementações reais vivem em enroll.go e run.go.
package app

// EnrollParams agrega os parâmetros do subcomando `enroll`.
type EnrollParams struct {
	ConfigPath  string
	Server      string
	EnrollToken string
	Force       bool
}

// DaemonParams agrega os parâmetros do subcomando `run`.
type DaemonParams struct {
	ConfigPath     string
	ServerOverride string
}
