package discovery

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
	"time"

	"hrail/internal/security"
)

func fixtureInv(t *testing.T) Inventory {
	t.Helper()
	root := t.TempDir()
	if err := WriteFixture(root); err != nil {
		t.Fatal(err)
	}
	c := &Collector{Root: root, Runner: security.NewRunner(time.Second), Fixture: true}
	return c.Collect(context.Background())
}

func TestHardwareFicticio(t *testing.T) {
	inv := fixtureInv(t)
	if inv.Origin != OrigemFixture {
		t.Fatalf("origem=%s", inv.Origin)
	}
	if inv.CPU.Logical != 2 || inv.CPU.Features["avx2"] || !inv.CPU.Features["avx"] {
		t.Errorf("CPU/flags: %+v", inv.CPU)
	}
	if inv.Memory.TotalKiB != 16384000 {
		t.Errorf("RAM: %+v", inv.Memory)
	}
	if len(inv.Storage) != 1 || inv.Storage[0].SizeBytes != 1953525168*512 {
		t.Errorf("storage: %+v", inv.Storage)
	}
	if len(inv.GPUs) != 1 {
		t.Fatalf("GPUs: %+v", inv.GPUs)
	}
	g := inv.GPUs[0]
	if g.DeviceID != "0x6fdf" || g.Revision != "0xef" || g.KernelDriver != "amdgpu" || g.KernelDriverVersion != "1.0.0-fixture" {
		t.Errorf("perfil: %+v", g)
	}
	if g.VRAMTotalBytes == nil || *g.VRAMTotalBytes != 8<<30 {
		t.Errorf("VRAM: %v", g.VRAMTotalBytes)
	}
	if g.KnownVariant == nil || g.KnownVariant.Level != "requer_verificacao" {
		t.Errorf("a RX 580 2048SP deve exigir verificação: %+v", g.KnownVariant)
	}
	if g.ArchFamilySource != "inferido_pci_id" {
		t.Errorf("arquitetura deve ser marcada como inferida: %+v", g)
	}
}

func TestVulkanAssociadoEPriorizaNomeReal(t *testing.T) {
	g := fixtureInv(t).GPUs[0]
	if g.Vulkan == nil {
		t.Fatal("Vulkan não associado")
	}
	if g.NameSource != "vulkan" || !strings.Contains(g.Name, "RX 580 2048SP") {
		t.Errorf("nome deveria vir do Vulkan: %q (%s)", g.Name, g.NameSource)
	}
	v := g.Vulkan
	if v.DriverName != "radv" || v.MesaVersion != "24.2.8" || v.APIVersion != "1.3.255" {
		t.Errorf("driver: %+v", v)
	}
	if v.ComputeLimits["maxComputeWorkGroupInvocations"] != "1024" || v.ComputeLimits["maxComputeSharedMemorySize"] != "32768" {
		t.Errorf("limites: %v", v.ComputeLimits)
	}
	if len(v.QueueFamilies) != 2 || v.QueueFamilies[1].Count != "4" || !strings.Contains(v.QueueFamilies[0].Flags, "GRAPHICS") {
		t.Errorf("filas: %+v", v.QueueFamilies)
	}
	if len(v.Extensions) != 2 {
		t.Errorf("extensões: %v", v.Extensions)
	}
}

func TestSuporteNumericoNaoInventaCampos(t *testing.T) {
	v := fixtureInv(t).GPUs[0].Vulkan.NumericSupport
	if v["shaderFloat16"] != false || v["shaderInt64"] != true {
		t.Errorf("valores: %v", v)
	}
	if _, ok := v["cooperativeMatrix"]; ok {
		t.Error("chave ausente na saída não pode aparecer (desconhecido ≠ falso)")
	}
	if !v["ext:VK_KHR_16bit_storage"] {
		t.Error("extensão presente deveria ser registrada")
	}
}

func TestExportacaoJSON(t *testing.T) {
	inv := fixtureInv(t)
	b, err := json.MarshalIndent(inv, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	var back Inventory
	if err := json.Unmarshal(b, &back); err != nil {
		t.Fatal(err)
	}
	if back.GPUs[0].DeviceID != "0x6fdf" || back.Origin != "fixture" {
		t.Errorf("ida e volta falhou: %+v", back.GPUs)
	}
	if strings.Contains(string(b), "serial") {
		t.Error("não deve exportar números de série")
	}
}

func TestSistemaVazioNaoQuebra(t *testing.T) {
	c := &Collector{Root: t.TempDir(), Runner: security.NewRunner(time.Second), Fixture: true}
	inv := c.Collect(context.Background())
	if len(inv.GPUs) != 0 || len(inv.Unavailable) < 3 {
		t.Errorf("deveria registrar indisponibilidades: %+v", inv.Unavailable)
	}
	if _, ok := inv.CPU.Features["avx2"]; ok {
		t.Error("sem /proc/cpuinfo, AVX2 deve ser desconhecido, não falso")
	}
}

func TestParseVulkanLixo(t *testing.T) {
	if ParseVulkanInfo("lixo\nsem dispositivos\n") != nil {
		t.Fatal("saída sem GPU deve devolver nil")
	}
}

func TestVulkanAusenteGeraAviso(t *testing.T) {
	root := t.TempDir()
	WriteFixture(root)
	t.Setenv("PATH", t.TempDir())
	c := &Collector{Root: root, Runner: security.NewRunner(time.Second, "vulkaninfo")}
	inv := c.Collect(context.Background()) // modo real, vulkaninfo ausente
	found := false
	for _, u := range inv.Unavailable {
		found = found || strings.Contains(u, "vulkaninfo ausente")
	}
	if !found || inv.GPUs[0].Vulkan != nil {
		t.Errorf("esperava aviso de vulkaninfo ausente: %v", inv.Unavailable)
	}
}

// Saída REAL de `vulkaninfo --summary` (Windows, driver AMD proprietário, RX 580 2048SP), 2026-10-22.
// Valida o parser contra formato real; note que NÃO há Mesa nem RADV neste ambiente.
const vulkanSummaryReal = "VULKANINFO\r\n==========\r\n\r\nVulkan Instance Version: 1.4.363\r\n\r\n\r\nInstance Extensions: count = 13\r\n-------------------------------\r\nVK_EXT_debug_report                    : extension revision 10\r\n\r\nDevices:\r\n========\r\nGPU0:\r\n\tapiVersion         = 1.3.260\r\n\tdriverVersion      = 2.0.279\r\n\tvendorID           = 0x1002\r\n\tdeviceID           = 0x6fdf\r\n\tdeviceType         = PHYSICAL_DEVICE_TYPE_DISCRETE_GPU\r\n\tdeviceName         = AMD Radeon RX 580 2048SP\r\n\tdriverID           = DRIVER_ID_AMD_PROPRIETARY\r\n\tdriverName         = AMD proprietary driver\r\n\tdriverInfo         = 26.5.2 (AMD proprietary shader compiler)\r\n\tconformanceVersion = 1.3.3.1\r\n"

func TestParserComSaidaRealDoWindows(t *testing.T) {
	v := ParseVulkanInfo(vulkanSummaryReal)
	if v == nil || len(v.Devices) != 1 || v.InstanceVersion != "1.4.363" {
		t.Fatalf("%+v", v)
	}
	d := v.Devices[0]
	if d.Name != "AMD Radeon RX 580 2048SP" || d.VendorID != "0x1002" || d.DeviceID != "0x6fdf" || d.APIVersion != "1.3.260" {
		t.Errorf("%+v", d)
	}
	if d.DriverName != "AMD proprietary driver" || d.MesaVersion != "" {
		t.Errorf("driver proprietário: Mesa não pode ser inventado: %+v", d)
	}
	if len(d.ComputeLimits) != 0 || len(d.QueueFamilies) != 0 {
		t.Errorf("o resumo não traz limites/filas: não preencher: %+v", d)
	}
}
