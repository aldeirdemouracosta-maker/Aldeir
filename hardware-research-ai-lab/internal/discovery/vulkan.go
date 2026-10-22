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
	HeapSizes      []string          `json:"memory_heaps,omitempty"`
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
	reHeap     = regexp.MustCompile(`^\s*size\s*=\s*(\d+)`)
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
	"shaderIntegerDotProduct": true, "cooperativeMatrix": true,
}

// ParseVulkanInfo interpreta a saída textual do vulkaninfo de forma tolerante.
// Formatos variam entre versões; o que não for reconhecido simplesmente não é preenchido.
func ParseVulkanInfo(out string) *VulkanInfo {
	info := &VulkanInfo{}
	if m := reInst.FindStringSubmatch(out); m != nil {
		info.InstanceVersion = m[1]
	}
	var cur *VulkanDevice
	var inQueues, inHeaps bool
	var qIdx = -1
	flush := func() {
		if cur != nil {
			info.Devices = append(info.Devices, *cur)
		}
	}
	for _, ln := range strings.Split(out, "\n") {
		if m := reGPU.FindStringSubmatch(strings.TrimRight(ln, " \t\r")); m != nil && !strings.HasPrefix(ln, " ") && !strings.HasPrefix(ln, "\t") {
			flush()
			cur = &VulkanDevice{ComputeLimits: map[string]string{}, NumericSupport: map[string]bool{}}
			inQueues, inHeaps = false, false
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
			inQueues, inHeaps = true, false
		case strings.HasPrefix(trim, "VkPhysicalDeviceMemoryProperties") || strings.HasPrefix(trim, "Memory Heaps"):
			inQueues, inHeaps = false, true
		case strings.HasPrefix(trim, "Vk") && strings.HasSuffix(trim, ":") && !strings.Contains(trim, "QueueFamily"):
			inQueues, inHeaps = false, false
		}
		if m := reQueueHdr.FindStringSubmatch(trim); m != nil {
			for _, g := range m[1:] {
				if g != "" {
					fmt.Sscan(g, &qIdx)
					cur.QueueFamilies = append(cur.QueueFamilies, QueueFamily{Index: qIdx})
				}
			}
			continue
		}
		if inHeaps {
			if m := reHeap.FindStringSubmatch(ln); m != nil {
				cur.HeapSizes = append(cur.HeapSizes, m[1])
			}
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
				cur.APIVersion = v
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
			case "VK_KHR_cooperative_matrix", "VK_NV_cooperative_matrix":
				d.NumericSupport["ext:"+e] = true
			case "VK_KHR_shader_integer_dot_product", "VK_KHR_16bit_storage", "VK_KHR_8bit_storage", "VK_KHR_shader_float16_int8":
				d.NumericSupport["ext:"+e] = true
			}
		}
	}
	if len(info.Devices) == 0 {
		return nil
	}
	return info
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
