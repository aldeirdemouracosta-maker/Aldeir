package discovery

import (
	"strings"
	"time"
	"unicode/utf16"
)

// DecodeText converte texto UTF-16 (LE/BE, como gerado pelo PowerShell do Windows) ou UTF-8 em string UTF-8.
func DecodeText(b []byte) string {
	if len(b) >= 2 && ((b[0] == 0xFF && b[1] == 0xFE) || (b[0] == 0xFE && b[1] == 0xFF)) {
		le := b[0] == 0xFF
		u := make([]uint16, 0, len(b)/2)
		for i := 2; i+1 < len(b); i += 2 {
			if le {
				u = append(u, uint16(b[i])|uint16(b[i+1])<<8)
			} else {
				u = append(u, uint16(b[i])<<8|uint16(b[i+1]))
			}
		}
		return string(utf16.Decode(u))
	}
	return strings.TrimPrefix(string(b), "\xef\xbb\xbf")
}

// FromVulkan monta um inventário PARCIAL a partir de uma saída do vulkaninfo importada.
// Sem sysfs: não há revisão PCI, driver do kernel, CPU nem RAM; isso é declarado em Unavailable.
func FromVulkan(v *VulkanInfo, source string) Inventory {
	inv := Inventory{
		CollectedAt: time.Now().UTC().Format(time.RFC3339), Origin: OrigemMedido, Source: source, Vulkan: v,
		Unavailable: []string{"importado apenas de vulkaninfo: sem revisão PCI, driver do kernel, CPU, RAM e armazenamento"},
	}
	for i := range v.Devices {
		d := &v.Devices[i]
		g := GPUProfile{VendorID: d.VendorID, DeviceID: d.DeviceID, Name: d.Name, NameSource: "vulkan", Vulkan: d}
		if k, ok := knownGPUs[strings.ToLower(d.VendorID)+":"+strings.ToLower(d.DeviceID)]; ok {
			g.ArchFamily, g.ArchFamilySource = k.arch, "inferido_pci_id"
			g.GFXID, g.GFXIDSource = k.gfx, "inferido_pci_id"
			g.KnownVariant = k.variant
		}
		if t, vis, ok := d.VRAMFromHeaps(); ok {
			g.VRAMTotalBytes, g.VRAMVisibleBytes = &t, &vis
			g.VRAMSource = "vulkan: soma dos heaps device-local (derivado do que o driver reporta)"
		}
		g.NotDetermined = append(g.NotDetermined, "revisão PCI e driver do kernel (sem sysfs)")
		inv.GPUs = append(inv.GPUs, g)
	}
	return inv
}
