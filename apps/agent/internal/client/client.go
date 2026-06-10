// Package client fala com os endpoints do agente no sidecar (#1R-a):
//
//	POST /v1/agent/enroll     — Bearer <enroll_token>  → troca por agent_secret
//	POST /v1/agent/heartbeat  — Bearer <agent_secret>  → mantém last_seen + specs
//
// Transporte HTTPS com verificação de certificado padrão do servidor (NÃO desabilita
// TLS). Erros são tipados para o caller decidir (401 enroll → falha; 401 heartbeat →
// revogado/para; 503/rede → backoff).
package client

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"
)

// Erros tipados retornados pelo cliente.
var (
	// ErrUnauthorized: enroll token inválido/desabilitado/expirado (401 no enroll).
	ErrUnauthorized = errors.New("unauthorized")
	// ErrRevoked: agent_secret inválido/revogado (401 no heartbeat) → o agente para.
	ErrRevoked = errors.New("revoked")
	// ErrUnavailable: servidor/GI indisponível (503) ou erro de rede → backoff.
	ErrUnavailable = errors.New("unavailable")
)

// Client é o cliente HTTP do agente. Reutilizável entre chamadas.
type Client struct {
	server string
	http   *http.Client
}

// New cria um cliente para a base URL do sidecar (barra final é removida).
func New(server string) *Client {
	return &Client{
		server: strings.TrimRight(server, "/"),
		http: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

// EnrollResult é a resposta do /v1/agent/enroll (contrato #1R-a).
type EnrollResult struct {
	AgentID           string `json:"agent_id"`
	AgentSecret       string `json:"agent_secret"`
	Status            string `json:"status"`
	HeartbeatInterval int    `json:"heartbeat_interval_seconds"`
}

// HeartbeatResult é a resposta do /v1/agent/heartbeat (contrato #1R-a).
type HeartbeatResult struct {
	OK                bool   `json:"ok"`
	Status            string `json:"status"`
	HeartbeatInterval int    `json:"heartbeat_interval_seconds"`
}

type enrollBody struct {
	Fingerprint string            `json:"fingerprint"`
	Hostname    string            `json:"hostname"`
	OS          string            `json:"os"`
	Specs       map[string]string `json:"specs"`
}

type heartbeatBody struct {
	Specs         map[string]string `json:"specs"`
	UptimeSeconds int               `json:"uptime_seconds"`
}

// Enroll troca o enroll token por uma credencial de longo prazo.
// 201/202 → resultado (status active|pending); 401 → ErrUnauthorized; 503/rede → ErrUnavailable.
func (c *Client) Enroll(enrollToken, fingerprint, hostname, os string, specs map[string]string) (*EnrollResult, error) {
	body := enrollBody{
		Fingerprint: fingerprint,
		Hostname:    hostname,
		OS:          os,
		Specs:       specs,
	}
	var out EnrollResult
	status, err := c.postJSON("/v1/agent/enroll", enrollToken, body, &out)
	if err != nil {
		return nil, err
	}
	switch status {
	case http.StatusCreated, http.StatusAccepted: // 201 active / 202 pending
		return &out, nil
	case http.StatusUnauthorized:
		return nil, ErrUnauthorized
	case http.StatusServiceUnavailable:
		return nil, ErrUnavailable
	default:
		return nil, fmt.Errorf("enroll: unexpected status %d", status)
	}
}

// Heartbeat reporta presença + specs atuais.
// 200 → resultado; 401 → ErrRevoked; 503/rede → ErrUnavailable.
func (c *Client) Heartbeat(agentSecret string, specs map[string]string, uptimeSeconds int) (*HeartbeatResult, error) {
	body := heartbeatBody{Specs: specs, UptimeSeconds: uptimeSeconds}
	var out HeartbeatResult
	status, err := c.postJSON("/v1/agent/heartbeat", agentSecret, body, &out)
	if err != nil {
		return nil, err
	}
	switch status {
	case http.StatusOK:
		return &out, nil
	case http.StatusUnauthorized:
		return nil, ErrRevoked
	case http.StatusServiceUnavailable:
		return nil, ErrUnavailable
	default:
		return nil, fmt.Errorf("heartbeat: unexpected status %d", status)
	}
}

// postJSON faz um POST JSON com Bearer e desserializa o corpo em out (se status o
// permitir). Retorna o status code. Erros de rede viram ErrUnavailable (o caller
// faz backoff). Só desserializa quando há corpo de sucesso.
func (c *Client) postJSON(path, bearer string, body any, out any) (int, error) {
	buf, err := json.Marshal(body)
	if err != nil {
		return 0, err
	}
	req, err := http.NewRequest(http.MethodPost, c.server+path, bytes.NewReader(buf))
	if err != nil {
		return 0, err
	}
	req.Header.Set("Authorization", "Bearer "+bearer)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")

	resp, err := c.http.Do(req)
	if err != nil {
		// Falha de rede/DNS/TLS → tratável como indisponível (backoff).
		return 0, fmt.Errorf("%w: %v", ErrUnavailable, err)
	}
	defer resp.Body.Close()

	data, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	if out != nil && len(data) > 0 &&
		(resp.StatusCode == http.StatusOK ||
			resp.StatusCode == http.StatusCreated ||
			resp.StatusCode == http.StatusAccepted) {
		// Ignora erro de parse de corpos não-JSON em respostas de sucesso inesperadas.
		_ = json.Unmarshal(data, out)
	}
	return resp.StatusCode, nil
}
