// Package inventory coleta o fingerprint estável da máquina e os specs de hardware/SO.
//
// Fingerprint estável (núcleo do auto-registro seguro): preferimos um identificador
// imutável da máquina por SO — Linux /etc/machine-id ou SMBIOS UUID; Windows
// MachineGuid / SMBIOS UUID; macOS IOPlatformUUID. A fonte crua é SEMPRE hasheada
// (sha256) para não expor o identificador bruto no payload. Se nenhuma fonte estiver
// disponível, cai num fallback determinístico (hash de hostname+MACs) e loga.
package inventory

import (
	"crypto/sha256"
	"encoding/hex"
	"log"
	"net"
	"os"
	"sort"
	"strings"
)

// Specs são os atributos de hardware/SO reportados ao servidor. Os nomes batem o
// contrato do sidecar #1R-a (campo specs do enroll/heartbeat).
type Specs struct {
	Hostname        string
	OperatingSystem string
	CPU             string
	Memory          string
	Disk            string
	Serial          string
	Vendor          string
	Model           string
}

// AsMap serializa os specs no shape exato do contrato (chaves snake_case).
// O sidecar espera specs:{cpu,memory,disk,serial,vendor,model,operating_system}.
func (s Specs) AsMap() map[string]string {
	return map[string]string{
		"cpu":              s.CPU,
		"memory":           s.Memory,
		"disk":             s.Disk,
		"serial":           s.Serial,
		"vendor":           s.Vendor,
		"model":            s.Model,
		"operating_system": s.OperatingSystem,
	}
}

// source é uma fonte candidata de fingerprint. read retorna (valor, ok); ok=false
// quando a fonte não está disponível nesta máquina.
type source struct {
	name string
	read func() (string, bool)
}

// Collect coleta hostname, SO e specs de hardware. Nunca falha: campos que não
// puderam ser lidos ficam vazios (o servidor os trata como desconhecidos).
func Collect() Specs {
	host, _ := os.Hostname()
	s := collectSpecs() // por-SO (build tag)
	if s.Hostname == "" {
		s.Hostname = host
	}
	if s.OperatingSystem == "" {
		s.OperatingSystem = defaultOSName()
	}
	return s
}

// Fingerprint retorna o identificador estável da máquina (sha256 hex). Determinístico:
// duas chamadas na mesma máquina retornam o mesmo valor.
func Fingerprint() string {
	return fingerprintFrom(osSources())
}

// fingerprintFrom escolhe a primeira fonte disponível, normaliza (trim + lowercase)
// e devolve sha256 hex. Se nenhuma fonte estiver disponível, usa o fallback
// (hostname+MACs) e loga que recorreu a ele.
func fingerprintFrom(sources []source) string {
	for _, src := range sources {
		if src.read == nil {
			continue
		}
		raw, ok := src.read()
		raw = normalize(raw)
		if ok && raw != "" {
			return hashHex(raw)
		}
	}
	fb := fallbackIdentity()
	log.Printf("inventory: nenhuma fonte de fingerprint estável disponível; usando fallback (hostname+MACs)")
	return hashHex(fb)
}

func normalize(s string) string {
	return strings.ToLower(strings.TrimSpace(s))
}

func hashHex(s string) string {
	sum := sha256.Sum256([]byte(s))
	return hex.EncodeToString(sum[:])
}

// fallbackIdentity monta uma identidade determinística a partir do hostname + MACs
// das interfaces físicas (ordenados). Estável entre reinicializações na ausência de
// um UUID de máquina.
func fallbackIdentity() string {
	host, _ := os.Hostname()
	macs := physicalMACs()
	sort.Strings(macs)
	return "fallback:" + normalize(host) + "|" + strings.Join(macs, ",")
}

func physicalMACs() []string {
	out := []string{}
	ifaces, err := net.Interfaces()
	if err != nil {
		return out
	}
	for _, ifc := range ifaces {
		// Pula loopback e interfaces sem MAC (virtuais/ponto-a-ponto).
		if ifc.Flags&net.FlagLoopback != 0 {
			continue
		}
		mac := ifc.HardwareAddr.String()
		if mac == "" {
			continue
		}
		out = append(out, strings.ToLower(mac))
	}
	return out
}
