package discovery

import (
	"context"
	"fmt"
	"regexp"
	"strings"
)

// VulkanInfo é o resultado da consulta ao vulkaninfo.
type VulkanInfo struct {
	InstanceVersion string         `json:"instance_version,omitempty"`
	Devices         []VulkanDevice `json:"devices"`
}

// VulkanDevice descreve um dispositivo físico Vulkan. Booleanos em NumericSupport só
// existem se a chave foi encontrada na saída; ausência = desconhecido (NÃO = falso).
type VulkanDevice struct {
	memMode        byte              // estado interno do parser
	Name           string            `json:"name,omitempty"`
	VendorID       string            `json:"vendor_id,omitempty"`
	DeviceID       string            `json:"device_id,omitempty"`
	DeviceType     string            `json:"device_type,omitempty"`
	APIVersion     string            `json:"api_version,omitempty"`
	DriverName     string            `json:"driver_name,omitempty"`
	DriverInfo     string            `json:"driver_info,omitempty"`
	MesaVersion    string            `json:"mesa_version,omitempty"`
	ComputeLimits  map[string]string `json:"compute_limits,omitempty"`
	QueueFamilies  []QueueFamily     `json:"queue_families,omitempty"`
	Extensions     []string          `json:"extensions,omitempty"`
	NumericSupport map[string]bool   `json:"numeric_support,omitempty"`
	MemoryHeaps    []MemoryHeap      `json:"memory_heaps,omitempty"`
	MemoryTypes    []MemoryType      `json:"memory_types,omitempty"`
}

// MemoryHeap é um heap de memória Vulkan.
type MemoryHeap struct {
	Index       int    `json:"index"`
	SizeBytes   uint64 `json:"size_bytes"`
	DeviceLocal bool   `json:"device_local"`
}

// MemoryType relaciona um tipo de memória ao heap e às propriedades relevantes.
type MemoryType struct {
	Index       int  `json:"index"`
	HeapIndex   int  `json:"heap_index"`
	DeviceLocal bool `json:"device_local"`
	HostVisible bool `json:"host_visible"`
}

type QueueFamily struct {
	Index int    `json:"index"`
	Count string `json:"queue_count,omitempty"`
	Flags string `json:"flags,omitempty"`
}

var (
	reGPU      = regexp.MustCompile(`^GPU\s*(?:id\s*:\s*)?(\d+)\b`)
	reKV       = regexp.MustCompile(`^\s*([A-Za-z0-9_\[\]\.]+)\s*(?:=|:)\s*(.*?)\s*$`)
	reExt      = regexp.MustCompile(`^\s*(VK_[A-Za-z0-9_]+)\s*:\s*extension revision`)
	reQueueHdr = regexp.MustCompile(`queueProperties\[(\d+)\]|VkQueueFamilyProperties\[(\d+)\]|queue family (\d+)`)
	reMesa     = regexp.MustCompile(`Mesa\s+([0-9][^\s]*)`)
	reInst     = regexp.MustCompile(`Vulkan Instance Version:\s*([0-9][0-9.]*)`)
	reHeapSize = regexp.MustCompile(`^\s*size\s*=\s*(\d+)`)
	reHeapHdr  = regexp.MustCompile(`^memoryHeaps\[(\d+)\]:`)
	reTypeHdr  = regexp.MustCompile(`^memoryTypes\[(\d+)\]:`)
	reArray    = regexp.MustCompile(`^\s*([A-Za-z0-9_]+):\s*count\s*=\s*(\d+)\s*$`)
)

var computeKeys = map[string]bool{
	"maxComputeSharedMemorySize": true, "maxComputeWorkGroupCount": true,
	"maxComputeWorkGroupInvocations": true, "maxComputeWorkGroupSize": true,
	"maxPushConstantsSize": true, "maxStorageBufferRange": true, "maxBoundDescriptorSets": true,
	"subgroupSize": true, "subgroupSupportedStages": true, "minSubgroupSize": true, "maxSubgroupSize": true,
}

var numericKeys = map[string]bool{
	"shaderFloat16": true, "shaderInt8": true, "shaderInt16": true, "shaderInt64": true, "shaderFloat64": true,
	"storageBuffer16BitAccess": true, "storageBuffer8BitAccess": true,
	"uniformAndStorageBuffer16BitAccess": true, "shaderBufferInt64Atomics": true,
	"shaderIntegerDotProduct": true, "cooperativeMatrix": true, "shaderSharedInt64Atomics": true,
	"shaderSubgroupExtendedTypes": true, "bufferDeviceAddress": true, "storagePushConstant16": true,
}

// ParseVulkanInfo interpreta a saída textual do vulkaninfo de forma tolerante.
// Formatos variam entre versões; o que não for reconhecido simplesmente não é preenchido.
func ParseVulkanInfo(out string) *VulkanInfo {
	info := &VulkanInfo{}
	if m := reInst.FindStringSubmatch(out); m != nil {
		info.InstanceVersion = m[1]
	}
	lines := strings.Split(out, "\n")
	var cur *VulkanDevice
	var inQueues, inMem bool
	flush := func() {
		if cur != nil && (cur.Name != "" || cur.DeviceID != "" || len(cur.Extensions) > 0) {
			info.Devices = append(info.Devices, *cur)
		}
	}
	for i := 0; i < len(lines); i++ {
		ln := strings.TrimRight(lines[i], "\r")
		// "GPU id : 0 (nome) [VK_KHR_win32_surface]:" é uma superfície de apresentação, NÃO um dispositivo.
		if m := reGPU.FindStringSubmatch(strings.TrimRight(ln, " \t")); m != nil && !strings.HasPrefix(ln, " ") && !strings.HasPrefix(ln, "\t") && !strings.Contains(ln, "[") {
			flush()
			cur = &VulkanDevice{ComputeLimits: map[string]string{}, NumericSupport: map[string]bool{}}
			inQueues, inMem = false, false
			continue
		}
		if cur == nil {
			continue
		}
		if m := reExt.FindStringSubmatch(ln); m != nil {
			cur.Extensions = append(cur.Extensions, m[1])
			continue
		}
		trim := strings.TrimSpace(ln)
		switch {
		case strings.HasPrefix(trim, "VkQueueFamilyProperties") || strings.HasPrefix(trim, "Queue Families"):
			inQueues, inMem = true, false
		case strings.HasPrefix(trim, "VkPhysicalDeviceMemoryProperties") || strings.HasPrefix(trim, "Memory Heaps"):
			inQueues, inMem = false, true
		case strings.HasPrefix(trim, "Vk") && strings.HasSuffix(trim, ":") && !strings.Contains(trim, "QueueFamily"):
			inQueues, inMem = false, false
		}
		if m := reQueueHdr.FindStringSubmatch(trim); m != nil {
			for _, g := range m[1:] {
				if g != "" {
					var q int
					fmt.Sscan(g, &q)
					cur.QueueFamilies = append(cur.QueueFamilies, QueueFamily{Index: q})
				}
			}
			continue
		}
		if inMem {
			cur.parseMemoryLine(trim)
		}
		// arrays em linhas separadas: "chave: count = N" seguido de N valores
		if m := reArray.FindStringSubmatch(ln); m != nil {
			var n int
			fmt.Sscan(m[2], &n)
			if computeKeys[m[1]] && n > 0 && n <= 8 && i+n < len(lines) {
				vals := make([]string, 0, n)
				for j := 1; j <= n; j++ {
					vals = append(vals, strings.TrimSpace(lines[i+j]))
				}
				if _, seen := cur.ComputeLimits[m[1]]; !seen {
					cur.ComputeLimits[m[1]] = strings.Join(vals, ",")
				}
				i += n
			}
			continue
		}
		m := reKV.FindStringSubmatch(ln)
		if m == nil {
			continue
		}
		k, v := m[1], m[2]
		if inQueues && len(cur.QueueFamilies) > 0 {
			q := &cur.QueueFamilies[len(cur.QueueFamilies)-1]
			switch k {
			case "queueCount":
				q.Count = v
			case "queueFlags":
				q.Flags = v
			}
			continue
		}
		if inMem {
			continue
		}
		switch k {
		case "deviceName":
			if cur.Name == "" {
				cur.Name = v
			}
		case "vendorID":
			if cur.VendorID == "" {
				cur.VendorID = strings.ToLower(v)
			}
		case "deviceID":
			if cur.DeviceID == "" {
				cur.DeviceID = strings.ToLower(v)
			}
		case "deviceType":
			if cur.DeviceType == "" {
				cur.DeviceType = v
			}
		case "apiVersion":
			if cur.APIVersion == "" {
				cur.APIVersion = stripParen(v)
			}
		case "driverName":
			if cur.DriverName == "" {
				cur.DriverName = v
			}
		case "driverInfo":
			if cur.DriverInfo == "" {
				cur.DriverInfo = v
				if mm := reMesa.FindStringSubmatch(v); mm != nil {
					cur.MesaVersion = mm[1]
				}
			}
		default:
			if computeKeys[k] {
				if _, seen := cur.ComputeLimits[k]; !seen {
					cur.ComputeLimits[k] = v
				}
			}
			if numericKeys[k] {
				if _, seen := cur.NumericSupport[k]; !seen {
					cur.NumericSupport[k] = strings.EqualFold(v, "true") || v == "1"
				}
			}
		}
	}
	flush()
	// Extensões que indicam suporte numérico/IA (presença é evidência; ausência não é lida como "falso" aqui).
	for i := range info.Devices {
		d := &info.Devices[i]
		for _, e := range d.Extensions {
			switch e {
			case "VK_KHR_cooperative_matrix", "VK_NV_cooperative_matrix",
				"VK_KHR_shader_integer_dot_product", "VK_KHR_16bit_storage", "VK_KHR_8bit_storage", "VK_KHR_shader_float16_int8",
				"VK_AMD_shader_core_properties", "VK_AMD_shader_core_properties2":
				d.NumericSupport["ext:"+e] = true
			}
		}
	}
	if len(info.Devices) == 0 {
		return nil
	}
	return info
}

func stripParen(v string) string {
	if i := strings.Index(v, " ("); i > 0 {
		return strings.TrimSpace(v[:i])
	}
	return v
}

// parseMemoryLine acumula heaps e tipos de memória (formato do vulkaninfo moderno).
func (d *VulkanDevice) parseMemoryLine(trim string) {
	if m := reHeapHdr.FindStringSubmatch(trim); m != nil {
		var n int
		fmt.Sscan(m[1], &n)
		d.MemoryHeaps = append(d.MemoryHeaps, MemoryHeap{Index: n})
		d.memMode = 'h'
		return
	}
	if m := reTypeHdr.FindStringSubmatch(trim); m != nil {
		var n int
		fmt.Sscan(m[1], &n)
		d.MemoryTypes = append(d.MemoryTypes, MemoryType{Index: n})
		d.memMode = 't'
		return
	}
	switch d.memMode {
	case 'h':
		h := &d.MemoryHeaps[len(d.MemoryHeaps)-1]
		if m := reHeapSize.FindStringSubmatch(trim); m != nil {
			fmt.Sscan(m[1], &h.SizeBytes)
		}
		if trim == "MEMORY_HEAP_DEVICE_LOCAL_BIT" {
			h.DeviceLocal = true
		}
	case 't':
		t := &d.MemoryTypes[len(d.MemoryTypes)-1]
		switch {
		case strings.HasPrefix(trim, "heapIndex"):
			if _, v, ok := strings.Cut(trim, "="); ok {
				fmt.Sscan(strings.TrimSpace(v), &t.HeapIndex)
			}
		case trim == "MEMORY_PROPERTY_DEVICE_LOCAL_BIT":
			t.DeviceLocal = true
		case trim == "MEMORY_PROPERTY_HOST_VISIBLE_BIT":
			t.HostVisible = true
		}
	}
}

// VRAMFromHeaps deriva a VRAM total (soma dos heaps device-local) e a parte visível à CPU
// (heaps device-local que têm um tipo DEVICE_LOCAL+HOST_VISIBLE). ok=false se não houver heaps.
// ATENÇÃO: é uma derivação a partir do que o driver reporta, não leitura direta de hardware.
func (d *VulkanDevice) VRAMFromHeaps() (total, visible uint64, ok bool) {
	vis := map[int]bool{}
	for _, t := range d.MemoryTypes {
		if t.DeviceLocal && t.HostVisible {
			vis[t.HeapIndex] = true
		}
	}
	for _, h := range d.MemoryHeaps {
		if h.DeviceLocal {
			total += h.SizeBytes
			ok = true
			if vis[h.Index] {
				visible += h.SizeBytes
			}
		}
	}
	return
}

func (c *Collector) vulkan(ctx context.Context) (*VulkanInfo, string) {
	if _, err := c.Runner.LookPath("vulkaninfo"); err != nil {
		return nil, "vulkaninfo ausente no PATH"
	}
	res, err := c.Runner.Run(ctx, "vulkaninfo")
	if err != nil {
		return nil, "falha ao executar vulkaninfo: " + err.Error()
	}
	if res.ExitCode != 0 {
		return nil, fmt.Sprintf("vulkaninfo retornou código %d (sem driver/ICD ou sem dispositivo?)", res.ExitCode)
	}
	v := ParseVulkanInfo(res.Stdout)
	if v == nil {
		return nil, "saída do vulkaninfo sem dispositivos reconhecíveis"
	}
	return v, ""
}

// attachVulkan associa dispositivos Vulkan às GPUs PCI por vendor:device.
func attachVulkan(gpus []GPUProfile, v *VulkanInfo) {
	for i := range gpus {
		g := &gpus[i]
		for j := range v.Devices {
			d := &v.Devices[j]
			if strings.EqualFold(d.VendorID, g.VendorID) && strings.EqualFold(d.DeviceID, g.DeviceID) {
				g.Vulkan = d
				if t, v, ok := d.VRAMFromHeaps(); ok && g.VRAMTotalBytes == nil {
					g.VRAMTotalBytes, g.VRAMVisibleBytes = &t, &v
					g.VRAMSource = "vulkan: soma dos heaps device-local (derivado do que o driver reporta)"
				}
				if d.Name != "" {
					g.Name, g.NameSource = d.Name, "vulkan"
				}
				break
			}
		}
		if g.Vulkan == nil {
			g.NotDetermined = append(g.NotDetermined, "vulkan (nenhum dispositivo Vulkan correspondente ao PCI ID)")
		}
	}
}
