package discovery

import (
	"os"
	"path/filepath"
)

// FixtureVulkanInfo é uma saída FICTÍCIA no formato do vulkaninfo, para testes de infraestrutura.
const FixtureVulkanInfo = `Vulkan Instance Version: 1.3.275

GPU0:
VkPhysicalDeviceProperties:
	apiVersion     = 1.3.255
	driverVersion  = 24.2.8
	vendorID       = 0x1002
	deviceID       = 0x6fdf
	deviceType     = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU
	deviceName     = AMD Radeon RX 580 2048SP (RADV POLARIS10)
VkPhysicalDeviceLimits:
	maxComputeSharedMemorySize     = 32768
	maxComputeWorkGroupCount       = (65535, 65535, 65535)
	maxComputeWorkGroupInvocations = 1024
	maxComputeWorkGroupSize        = (1024, 1024, 1024)
VkPhysicalDeviceDriverProperties:
	driverID   = DRIVER_ID_MESA_RADV
	driverName = radv
	driverInfo = Mesa 24.2.8
VkPhysicalDeviceFeatures:
	shaderInt16   = true
	shaderInt64   = true
	shaderFloat64 = true
VkPhysicalDeviceVulkan12Features:
	shaderFloat16 = false
	shaderInt8    = false
VkQueueFamilyProperties:
	queueProperties[0]:
		queueCount = 1
		queueFlags = QUEUE_GRAPHICS_BIT | QUEUE_COMPUTE_BIT | QUEUE_TRANSFER_BIT
	queueProperties[1]:
		queueCount = 4
		queueFlags = QUEUE_COMPUTE_BIT | QUEUE_TRANSFER_BIT
Device Extensions:
	VK_KHR_16bit_storage                  : extension revision 1
	VK_KHR_swapchain                      : extension revision 70
`

// WriteFixture cria sob root uma árvore sysfs/proc FICTÍCIA de uma máquina com uma
// GPU 1002:6fdf. Todos os valores são inventados para testes de infraestrutura.
func WriteFixture(root string) error {
	files := map[string]string{
		"proc/cpuinfo":                                             "processor\t: 0\nvendor_id\t: GenuineIntel\nmodel name\t: FIXTURE CPU sem AVX2\nflags\t\t: fpu sse2 sse4_1 sse4_2 avx popcnt\n\nprocessor\t: 1\nmodel name\t: FIXTURE CPU sem AVX2\nflags\t\t: fpu sse2 sse4_1 sse4_2 avx popcnt\n",
		"proc/meminfo":                                             "MemTotal:       16384000 kB\nMemAvailable:    8192000 kB\n",
		"proc/sys/kernel/osrelease":                                "0.0.0-fixture\n",
		"sys/block/sda/size":                                       "1953525168\n",
		"sys/block/sda/queue/rotational":                           "0\n",
		"sys/block/sda/removable":                                  "0\n",
		"sys/block/sda/device/model":                               "FIXTURE SSD\n",
		"sys/bus/pci/devices/0000:01:00.0/vendor":                  "0x1002\n",
		"sys/bus/pci/devices/0000:01:00.0/device":                  "0x6fdf\n",
		"sys/bus/pci/devices/0000:01:00.0/subsystem_vendor":        "0x1002\n",
		"sys/bus/pci/devices/0000:01:00.0/subsystem_device":        "0x0b01\n",
		"sys/bus/pci/devices/0000:01:00.0/class":                   "0x030000\n",
		"sys/bus/pci/devices/0000:01:00.0/revision":                "0xef\n",
		"sys/bus/pci/devices/0000:01:00.0/mem_info_vram_total":     "8589934592\n",
		"sys/bus/pci/devices/0000:01:00.0/mem_info_vis_vram_total": "268435456\n",
		"sys/bus/pci/devices/0000:01:00.0/current_link_speed":      "8.0 GT/s PCIe\n",
		"sys/bus/pci/devices/0000:01:00.0/current_link_width":      "16\n",
		"sys/module/amdgpu/version":                                "1.0.0-fixture\n",
		"sys/class/hwmon/hwmon0/temp1_input":                       "47000\n",
		"fixture/vulkaninfo.txt":                                   FixtureVulkanInfo,
	}
	for rel, body := range files {
		p := filepath.Join(root, rel)
		if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
			return err
		}
		if err := os.WriteFile(p, []byte(body), 0o644); err != nil {
			return err
		}
	}
	drv := filepath.Join(root, "sys/module/amdgpu")
	return os.Symlink(drv, filepath.Join(root, "sys/bus/pci/devices/0000:01:00.0/driver"))
}
