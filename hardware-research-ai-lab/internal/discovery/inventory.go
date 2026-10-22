// Package discovery implementa o hardware-discovery: coleta SOMENTE LEITURA
// de CPU, RAM, armazenamento, PCIe, drivers e Vulkan.
package discovery

import (
	"bufio"
	"context"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"time"

	"hrail/internal/security"
)

// Origens possíveis de um dado (usadas também pelo benchmark-engine).
const (
	OrigemMedido  = "measured"
	OrigemFixture = "fixture" // dados fictícios de teste de infraestrutura
)

// Inventory é o inventário técnico exportável em JSON.
// Campos desconhecidos ficam ausentes (ponteiros/omitempty) e são listados em Unavailable.
type Inventory struct {
	CollectedAt string       `json:"collected_at"`
	Origin      string       `json:"origin"`
	Kernel      string       `json:"kernel,omitempty"`
	CPU         CPUInfo      `json:"cpu"`
	Memory      MemoryInfo   `json:"memory"`
	Storage     []StorageDev `json:"storage"`
	PCI         []PCIDevice  `json:"pci"`
	GPUs        []GPUProfile `json:"gpus"`
	Vulkan      *VulkanInfo  `json:"vulkan,omitempty"`
	Unavailable []string     `json:"unavailable,omitempty"`
}

type CPUInfo struct {
	Model    string          `json:"model,omitempty"`
	Vendor   string          `json:"vendor,omitempty"`
	Logical  int             `json:"logical_cpus"`
	Features map[string]bool `json:"features"` // verificado contra a lista de flags do kernel
}

type MemoryInfo struct {
	TotalKiB     uint64 `json:"total_kib,omitempty"`
	AvailableKiB uint64 `json:"available_kib,omitempty"`
}

type StorageDev struct {
	Name       string `json:"name"`
	Model      string `json:"model,omitempty"`
	SizeBytes  uint64 `json:"size_bytes"`
	Rotational *bool  `json:"rotational,omitempty"`
	Removable  *bool  `json:"removable,omitempty"`
}

type PCIDevice struct {
	Address       string `json:"address"`
	VendorID      string `json:"vendor_id"`
	DeviceID      string `json:"device_id"`
	SubVendorID   string `json:"subsystem_vendor_id,omitempty"`
	SubDeviceID   string `json:"subsystem_device_id,omitempty"`
	Class         string `json:"class"`
	Revision      string `json:"revision,omitempty"`
	Driver        string `json:"kernel_driver,omitempty"`
	VendorName    string `json:"vendor_name,omitempty"`
	CurLinkSpeed  string `json:"current_link_speed,omitempty"`
	CurLinkWidth  string `json:"current_link_width,omitempty"`
	MaxLinkSpeed  string `json:"max_link_speed,omitempty"`
	MaxLinkWidth  string `json:"max_link_width,omitempty"`
	IsDisplayLike bool   `json:"display_class"`
}

// Collector lê o sistema a partir de Root ("/" em produção; diretório fictício em testes).
type Collector struct {
	Root   string
	Runner *security.Runner
	// Fixture marca o inventário como dados fictícios.
	Fixture bool
}

// NewCollector cria um coletor para o sistema real.
func NewCollector(r *security.Runner) *Collector { return &Collector{Root: "/", Runner: r} }

func (c *Collector) p(parts ...string) string {
	return filepath.Join(append([]string{c.Root}, parts...)...)
}

func (c *Collector) read(parts ...string) (string, bool) {
	b, err := os.ReadFile(c.p(parts...))
	if err != nil {
		return "", false
	}
	return strings.TrimSpace(string(b)), true
}

// Collect gera o inventário. Nunca altera o sistema; falhas parciais são registradas.
func (c *Collector) Collect(ctx context.Context) Inventory {
	inv := Inventory{CollectedAt: time.Now().UTC().Format(time.RFC3339), Origin: OrigemMedido}
	if c.Fixture {
		inv.Origin = OrigemFixture
	}
	miss := func(s string) { inv.Unavailable = append(inv.Unavailable, s) }

	if k, ok := c.read("proc", "sys", "kernel", "osrelease"); ok {
		inv.Kernel = k
	} else {
		miss("kernel")
	}
	inv.CPU = c.cpu(miss)
	inv.Memory = c.memory(miss)
	inv.Storage = c.storage()
	inv.PCI = c.pci()
	if len(inv.PCI) == 0 {
		miss("pci (nenhum dispositivo legível em /sys/bus/pci/devices)")
	}
	inv.GPUs = c.gpus(inv.PCI)
	if len(inv.GPUs) == 0 {
		miss("gpu (nenhuma GPU PCI de classe display detectada)")
	}
	if c.Fixture {
		if b, ok := c.read("fixture", "vulkaninfo.txt"); ok {
			if v := ParseVulkanInfo(b); v != nil {
				inv.Vulkan = v
				attachVulkan(inv.GPUs, v)
			}
		}
	} else if c.Runner != nil {
		if v, why := c.vulkan(ctx); v != nil {
			inv.Vulkan = v
			attachVulkan(inv.GPUs, v)
		} else {
			miss("vulkan: " + why)
		}
	}
	return inv
}

var watchedFlags = []string{"sse2", "sse4_1", "sse4_2", "avx", "avx2", "fma", "f16c", "bmi2", "avx512f", "popcnt"}

func (c *Collector) cpu(miss func(string)) CPUInfo {
	out := CPUInfo{Features: map[string]bool{}}
	f, err := os.Open(c.p("proc", "cpuinfo"))
	if err != nil {
		miss("cpu (/proc/cpuinfo)")
		return out
	}
	defer f.Close()
	var flags map[string]bool
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	for sc.Scan() {
		k, v, ok := strings.Cut(sc.Text(), ":")
		if !ok {
			continue
		}
		k, v = strings.TrimSpace(k), strings.TrimSpace(v)
		switch k {
		case "processor":
			out.Logical++
		case "model name":
			if out.Model == "" {
				out.Model = v
			}
		case "vendor_id":
			if out.Vendor == "" {
				out.Vendor = v
			}
		case "flags":
			if flags == nil {
				flags = map[string]bool{}
				for _, fl := range strings.Fields(v) {
					flags[fl] = true
				}
			}
		}
	}
	if flags == nil {
		miss("cpu.features (sem linha 'flags'; presença de AVX2 desconhecida)")
		return out
	}
	for _, fl := range watchedFlags {
		out.Features[fl] = flags[fl]
	}
	return out
}

func (c *Collector) memory(miss func(string)) MemoryInfo {
	var m MemoryInfo
	s, ok := c.read("proc", "meminfo")
	if !ok {
		miss("memory (/proc/meminfo)")
		return m
	}
	for _, ln := range strings.Split(s, "\n") {
		k, v, ok := strings.Cut(ln, ":")
		if !ok {
			continue
		}
		n, _ := strconv.ParseUint(strings.Fields(v + " ")[0], 10, 64)
		switch k {
		case "MemTotal":
			m.TotalKiB = n
		case "MemAvailable":
			m.AvailableKiB = n
		}
	}
	return m
}

func (c *Collector) storage() []StorageDev {
	var out []StorageDev
	ents, _ := os.ReadDir(c.p("sys", "block"))
	for _, e := range ents {
		n := e.Name()
		if strings.HasPrefix(n, "loop") || strings.HasPrefix(n, "ram") || strings.HasPrefix(n, "dm-") || strings.HasPrefix(n, "zram") {
			continue
		}
		d := StorageDev{Name: n}
		if s, ok := c.read("sys", "block", n, "size"); ok {
			sec, _ := strconv.ParseUint(s, 10, 64)
			d.SizeBytes = sec * 512
		}
		d.Model, _ = c.read("sys", "block", n, "device", "model") // sem número de série
		if s, ok := c.read("sys", "block", n, "queue", "rotational"); ok {
			b := s == "1"
			d.Rotational = &b
		}
		if s, ok := c.read("sys", "block", n, "removable"); ok {
			b := s == "1"
			d.Removable = &b
		}
		out = append(out, d)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Name < out[j].Name })
	return out
}

var vendorNames = map[string]string{"0x1002": "AMD/ATI", "0x10de": "NVIDIA", "0x8086": "Intel", "0x1af4": "Red Hat/virtio"}

func (c *Collector) pci() []PCIDevice {
	var out []PCIDevice
	base := c.p("sys", "bus", "pci", "devices")
	ents, _ := os.ReadDir(base)
	for _, e := range ents {
		a := e.Name()
		rd := func(f string) string { s, _ := c.read("sys", "bus", "pci", "devices", a, f); return s }
		d := PCIDevice{
			Address: a, VendorID: rd("vendor"), DeviceID: rd("device"),
			SubVendorID: rd("subsystem_vendor"), SubDeviceID: rd("subsystem_device"),
			Class: rd("class"), Revision: rd("revision"),
			CurLinkSpeed: rd("current_link_speed"), CurLinkWidth: rd("current_link_width"),
			MaxLinkSpeed: rd("max_link_speed"), MaxLinkWidth: rd("max_link_width"),
		}
		if t, err := os.Readlink(filepath.Join(base, a, "driver")); err == nil {
			d.Driver = filepath.Base(t)
		}
		d.VendorName = vendorNames[strings.ToLower(d.VendorID)]
		d.IsDisplayLike = strings.HasPrefix(strings.ToLower(d.Class), "0x03")
		out = append(out, d)
	}
	return out
}
