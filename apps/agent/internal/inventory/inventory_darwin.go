//go:build darwin

package inventory

import (
	"os/exec"
	"strconv"
	"strings"
)

func defaultOSName() string { return "macos" }

// osSources: no macOS o identificador estável é o IOPlatformUUID, lido via ioreg.
func osSources() []source {
	return []source{
		{name: "io-platform-uuid", read: readIOPlatformUUID},
		{name: "hardware-uuid", read: func() (string, bool) {
			v := profilerValue("Hardware UUID")
			return v, v != ""
		}},
	}
}

func readIOPlatformUUID() (string, bool) {
	out, err := exec.Command("ioreg", "-rd1", "-c", "IOPlatformExpertDevice").Output()
	if err != nil {
		return "", false
	}
	for _, line := range strings.Split(string(out), "\n") {
		if strings.Contains(line, "IOPlatformUUID") {
			// Linha: `    "IOPlatformUUID" = "XXXX-...."`
			if i := strings.Index(line, "="); i >= 0 {
				v := strings.TrimSpace(line[i+1:])
				v = strings.Trim(v, `"`)
				return v, v != ""
			}
		}
	}
	return "", false
}

func collectSpecs() Specs {
	s := Specs{}
	s.OperatingSystem = macOSVersion()
	s.CPU = macCPU()
	s.Memory = macMemory()
	s.Disk = macDisk()
	s.Serial = profilerValue("Serial Number (system)")
	s.Vendor = "Apple"
	s.Model = sysctl("hw.model")
	return s
}

func macOSVersion() string {
	name, _ := exec.Command("sw_vers", "-productName").Output()
	ver, _ := exec.Command("sw_vers", "-productVersion").Output()
	n := strings.TrimSpace(string(name))
	v := strings.TrimSpace(string(ver))
	out := strings.TrimSpace(n + " " + v)
	if out == "" {
		return "macos"
	}
	return out
}

func sysctl(key string) string {
	out, err := exec.Command("sysctl", "-n", key).Output()
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(out))
}

func macCPU() string {
	brand := sysctl("machdep.cpu.brand_string")
	cores := sysctl("hw.logicalcpu")
	if brand == "" {
		return ""
	}
	if cores != "" {
		return brand + " (" + cores + " cores)"
	}
	return brand
}

func macMemory() string {
	v := sysctl("hw.memsize")
	bytes, err := strconv.ParseInt(v, 10, 64)
	if err != nil || bytes == 0 {
		return ""
	}
	gib := float64(bytes) / (1024.0 * 1024.0 * 1024.0)
	return strconv.FormatFloat(gib, 'f', 1, 64) + " GiB"
}

func macDisk() string {
	// Capacidade total do volume raiz via df (-k → blocos de 1KiB).
	out, err := exec.Command("df", "-k", "/").Output()
	if err != nil {
		return ""
	}
	lines := strings.Split(strings.TrimSpace(string(out)), "\n")
	if len(lines) < 2 {
		return ""
	}
	fields := strings.Fields(lines[1])
	if len(fields) < 2 {
		return ""
	}
	kb, err := strconv.ParseInt(fields[1], 10, 64)
	if err != nil {
		return ""
	}
	gib := float64(kb) / (1024.0 * 1024.0)
	return strconv.FormatFloat(gib, 'f', 1, 64) + " GiB"
}

// profilerValue extrai um campo "Label: value" da saída de system_profiler.
func profilerValue(label string) string {
	out, err := exec.Command("system_profiler", "SPHardwareDataType").Output()
	if err != nil {
		return ""
	}
	for _, line := range strings.Split(string(out), "\n") {
		line = strings.TrimSpace(line)
		if strings.HasPrefix(line, label+":") {
			return strings.TrimSpace(strings.TrimPrefix(line, label+":"))
		}
	}
	return ""
}
