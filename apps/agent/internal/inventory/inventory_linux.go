//go:build linux

package inventory

import (
	"bufio"
	"os"
	"strconv"
	"strings"
)

func defaultOSName() string { return "linux" }

// osSources lista as fontes de fingerprint preferidas no Linux, em ordem:
//  1. /etc/machine-id (systemd; estável por instalação)
//  2. /var/lib/dbus/machine-id (compat)
//  3. SMBIOS product_uuid (/sys/class/dmi/id/product_uuid; requer root, mais estável)
func osSources() []source {
	return []source{
		{name: "machine-id", read: fileSource("/etc/machine-id")},
		{name: "dbus-machine-id", read: fileSource("/var/lib/dbus/machine-id")},
		{name: "smbios-product-uuid", read: fileSource("/sys/class/dmi/id/product_uuid")},
	}
}

func fileSource(path string) func() (string, bool) {
	return func() (string, bool) {
		b, err := os.ReadFile(path)
		if err != nil {
			return "", false
		}
		v := strings.TrimSpace(string(b))
		return v, v != ""
	}
}

func collectSpecs() Specs {
	s := Specs{OperatingSystem: linuxOSPretty()}
	s.CPU = linuxCPU()
	s.Memory = linuxMemory()
	s.Disk = linuxDisk()
	s.Serial = readDMI("product_serial")
	s.Vendor = readDMI("sys_vendor")
	s.Model = readDMI("product_name")
	return s
}

func readDMI(name string) string {
	b, err := os.ReadFile("/sys/class/dmi/id/" + name)
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(b))
}

// linuxOSPretty lê PRETTY_NAME de /etc/os-release (ex.: "Debian GNU/Linux 12").
func linuxOSPretty() string {
	f, err := os.Open("/etc/os-release")
	if err != nil {
		return "linux"
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := sc.Text()
		if strings.HasPrefix(line, "PRETTY_NAME=") {
			v := strings.TrimPrefix(line, "PRETTY_NAME=")
			return strings.Trim(v, `"`)
		}
	}
	return "linux"
}

// linuxCPU conta os cores e pega o model name de /proc/cpuinfo.
func linuxCPU() string {
	f, err := os.Open("/proc/cpuinfo")
	if err != nil {
		return ""
	}
	defer f.Close()
	model := ""
	cores := 0
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := sc.Text()
		if strings.HasPrefix(line, "processor") {
			cores++
		} else if model == "" && strings.HasPrefix(line, "model name") {
			if i := strings.Index(line, ":"); i >= 0 {
				model = strings.TrimSpace(line[i+1:])
			}
		}
	}
	if model == "" {
		return ""
	}
	if cores > 0 {
		return model + " (" + strconv.Itoa(cores) + " cores)"
	}
	return model
}

// linuxMemory lê MemTotal de /proc/meminfo e formata em GiB.
func linuxMemory() string {
	f, err := os.Open("/proc/meminfo")
	if err != nil {
		return ""
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := sc.Text()
		if strings.HasPrefix(line, "MemTotal:") {
			fields := strings.Fields(line)
			if len(fields) >= 2 {
				kb, err := strconv.ParseInt(fields[1], 10, 64)
				if err == nil {
					return humanGiBFromKB(kb)
				}
			}
		}
	}
	return ""
}

func humanGiBFromKB(kb int64) string {
	gib := float64(kb) / (1024.0 * 1024.0)
	return strconv.FormatFloat(gib, 'f', 1, 64) + " GiB"
}

// linuxDisk soma a capacidade dos discos de bloco físicos em /sys/block (setores
// de 512 bytes), ignorando loop/ram/zram.
func linuxDisk() string {
	entries, err := os.ReadDir("/sys/block")
	if err != nil {
		return ""
	}
	var totalBytes int64
	for _, e := range entries {
		name := e.Name()
		if strings.HasPrefix(name, "loop") || strings.HasPrefix(name, "ram") || strings.HasPrefix(name, "zram") {
			continue
		}
		b, err := os.ReadFile("/sys/block/" + name + "/size")
		if err != nil {
			continue
		}
		sectors, err := strconv.ParseInt(strings.TrimSpace(string(b)), 10, 64)
		if err != nil {
			continue
		}
		totalBytes += sectors * 512
	}
	if totalBytes == 0 {
		return ""
	}
	gib := float64(totalBytes) / (1024.0 * 1024.0 * 1024.0)
	return strconv.FormatFloat(gib, 'f', 1, 64) + " GiB"
}
