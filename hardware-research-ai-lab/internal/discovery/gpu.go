package discovery

import (
	"strconv"
	"strings"
)

// GPUProfile é o perfil automático de uma GPU. Nada é inventado: o que não pôde
// ser lido/consultado fica ausente e aparece em NotDetermined.
type GPUProfile struct {
	PCIAddress      string `json:"pci_address"`
	VendorID        string `json:"vendor_id"`
	DeviceID        string `json:"device_id"`
	Revision        string `json:"revision,omitempty"`
	SubsystemVendor string `json:"subsystem_vendor_id,omitempty"`
	SubsystemDevice string `json:"subsystem_device_id,omitempty"`

	Name       string `json:"name,omitempty"`
	NameSource string `json:"name_source,omitempty"` // vulkan | tabela_pci_id (inferido)

	ArchFamily       string `json:"arch_family,omitempty"`
	ArchFamilySource string `json:"arch_family_source,omitempty"` // inferido_pci_id | vulkan
	GFXID            string `json:"gfx_id,omitempty"`
	GFXIDSource      string `json:"gfx_id_source,omitempty"`

	KernelDriver        string  `json:"kernel_driver,omitempty"`
	KernelDriverVersion string  `json:"kernel_driver_version,omitempty"`
	VRAMTotalBytes      *uint64 `json:"vram_total_bytes,omitempty"`
	VRAMVisibleBytes    *uint64 `json:"vram_cpu_visible_bytes,omitempty"`

	Vulkan *VulkanDevice `json:"vulkan,omitempty"`

	KnownVariant  *VariantNote `json:"known_variant,omitempty"`
	NotDetermined []string     `json:"not_determined,omitempty"`
}

// VariantNote registra variantes que exigem verificação técnica.
type VariantNote struct {
	Name  string `json:"name"`
	Note  string `json:"note"`
	Level string `json:"verification_level"` // "requer_verificacao"
}

type knownGPU struct {
	name, arch, gfx string
	variant         *VariantNote
}

// Tabela mínima e CONSERVADORA: serve apenas de dica quando o Vulkan não está disponível.
// Tudo que vem daqui é marcado como inferido.
var knownGPUs = map[string]knownGPU{
	"0x1002:0x6fdf": {
		name: "AMD Radeon RX 580 2048SP (inferido pelo PCI ID)", arch: "GCN 4 / Polaris 20 (inferido)", gfx: "gfx803 (inferido; confirmar via driver/Vulkan)",
		variant: &VariantNote{
			Name:  "Radeon RX 580 2048SP",
			Level: "requer_verificacao",
			Note:  "Variante distinta da RX 580 convencional (o sufixo indica 2048 stream processors, a confirmar). Não presumir especificações, clocks, limites ou compatibilidade da RX 580 padrão; verificar contagem de CUs, memória, limites Vulkan e extensões na máquina real.",
		},
	},
	"0x1002:0x67df": {
		name: "AMD Radeon Polaris 10/20 (RX 470/480/570/580/590 – ambíguo; inferido pelo PCI ID)", arch: "GCN 4 / Polaris (inferido)", gfx: "gfx803 (inferido; confirmar via driver/Vulkan)",
		variant: &VariantNote{Name: "Polaris 0x67DF", Level: "requer_verificacao",
			Note: "O mesmo PCI ID cobre vários produtos; usar revisão PCI e nome do driver Vulkan para distinguir."},
	},
}

func (c *Collector) gpus(devs []PCIDevice) []GPUProfile {
	var out []GPUProfile
	for _, d := range devs {
		if !d.IsDisplayLike {
			continue
		}
		g := GPUProfile{
			PCIAddress: d.Address, VendorID: d.VendorID, DeviceID: d.DeviceID, Revision: d.Revision,
			SubsystemVendor: d.SubVendorID, SubsystemDevice: d.SubDeviceID, KernelDriver: d.Driver,
		}
		if k, ok := knownGPUs[strings.ToLower(d.VendorID)+":"+strings.ToLower(d.DeviceID)]; ok {
			g.Name, g.NameSource = k.name, "tabela_pci_id (inferido)"
			g.ArchFamily, g.ArchFamilySource = k.arch, "inferido_pci_id"
			g.GFXID, g.GFXIDSource = k.gfx, "inferido_pci_id"
			g.KnownVariant = k.variant
		}
		if g.KernelDriver == "amdgpu" || g.KernelDriver == "radeon" {
			g.KernelDriverVersion, _ = c.read("sys", "module", g.KernelDriver, "version")
		}
		if g.KernelDriverVersion == "" && g.KernelDriver != "" {
			g.NotDetermined = append(g.NotDetermined, "kernel_driver_version (módulo sem /sys/module/<drv>/version; ver versão do kernel)")
		}
		g.VRAMTotalBytes = c.drmU64(d.Address, "mem_info_vram_total")
		g.VRAMVisibleBytes = c.drmU64(d.Address, "mem_info_vis_vram_total")
		if g.VRAMTotalBytes == nil {
			g.NotDetermined = append(g.NotDetermined, "vram_total_bytes (sem mem_info_vram_total no sysfs)")
		}
		out = append(out, g)
	}
	return out
}

func (c *Collector) drmU64(addr, file string) *uint64 {
	s, ok := c.read("sys", "bus", "pci", "devices", addr, file)
	if !ok {
		return nil
	}
	n, err := strconv.ParseUint(s, 10, 64)
	if err != nil {
		return nil
	}
	return &n
}
