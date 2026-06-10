//go:build windows

package inventory

import (
	"os/exec"
	"strconv"
	"strings"
)

func defaultOSName() string { return "windows" }

// osSources lista as fontes de fingerprint preferidas no Windows, em ordem:
//  1. MachineGuid do registro (HKLM\SOFTWARE\Microsoft\Cryptography); estável por instalação.
//  2. SMBIOS UUID (Win32_ComputerSystemProduct.UUID via wmic/PowerShell).
func osSources() []source {
	return []source{
		{name: "machine-guid", read: readMachineGUID},
		{name: "smbios-uuid", read: readSMBIOSUUID},
	}
}

// readMachineGUID lê HKLM\SOFTWARE\Microsoft\Cryptography\MachineGuid via `reg query`
// (evita dependência de golang.org/x/sys/windows/registry — stdlib + exec).
func readMachineGUID() (string, bool) {
	out, err := exec.Command("reg", "query",
		`HKLM\SOFTWARE\Microsoft\Cryptography`, "/v", "MachineGuid").Output()
	if err != nil {
		return "", false
	}
	// Saída: "    MachineGuid    REG_SZ    <guid>"
	for _, line := range strings.Split(string(out), "\n") {
		if strings.Contains(line, "MachineGuid") {
			fields := strings.Fields(line)
			if len(fields) >= 3 {
				return fields[len(fields)-1], true
			}
		}
	}
	return "", false
}

func readSMBIOSUUID() (string, bool) {
	v := psQuery(`(Get-CimInstance Win32_ComputerSystemProduct).UUID`)
	return v, v != ""
}

// psQuery roda um one-liner PowerShell e retorna a saída trimada.
func psQuery(expr string) string {
	out, err := exec.Command("powershell", "-NoProfile", "-NonInteractive",
		"-Command", expr).Output()
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(out))
}

func collectSpecs() Specs {
	s := Specs{OperatingSystem: psQuery(`(Get-CimInstance Win32_OperatingSystem).Caption`)}
	s.CPU = winCPU()
	s.Memory = winMemory()
	s.Disk = winDisk()
	s.Serial = psQuery(`(Get-CimInstance Win32_BIOS).SerialNumber`)
	s.Vendor = psQuery(`(Get-CimInstance Win32_ComputerSystem).Manufacturer`)
	s.Model = psQuery(`(Get-CimInstance Win32_ComputerSystem).Model`)
	return s
}

func winCPU() string {
	name := psQuery(`(Get-CimInstance Win32_Processor | Select-Object -First 1).Name`)
	cores := psQuery(`(Get-CimInstance Win32_Processor | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum`)
	name = strings.TrimSpace(name)
	if name == "" {
		return ""
	}
	if cores != "" {
		return name + " (" + cores + " cores)"
	}
	return name
}

func winMemory() string {
	v := psQuery(`(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory`)
	bytes, err := strconv.ParseInt(strings.TrimSpace(v), 10, 64)
	if err != nil || bytes == 0 {
		return ""
	}
	gib := float64(bytes) / (1024.0 * 1024.0 * 1024.0)
	return strconv.FormatFloat(gib, 'f', 1, 64) + " GiB"
}

func winDisk() string {
	v := psQuery(`(Get-CimInstance Win32_DiskDrive | Measure-Object -Property Size -Sum).Sum`)
	bytes, err := strconv.ParseInt(strings.TrimSpace(v), 10, 64)
	if err != nil || bytes == 0 {
		return ""
	}
	gib := float64(bytes) / (1024.0 * 1024.0 * 1024.0)
	return strconv.FormatFloat(gib, 'f', 1, 64) + " GiB"
}
