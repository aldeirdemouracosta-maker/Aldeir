// Package report gera relatórios em Markdown e JSON.
package report

import (
	"fmt"
	"strings"

	"hrail/internal/benchmark"
	"hrail/internal/discovery"
	"hrail/internal/experiments"
	"hrail/internal/research"
	"hrail/internal/security"
	"hrail/internal/tools"
)

// Data é o conteúdo estruturado do relatório (também exportado como JSON).
type Data struct {
	GeneratedAt string                   `json:"generated_at"`
	Version     string                   `json:"hrail_version"`
	Phase       string                   `json:"phase"`
	Hardware    discovery.Inventory      `json:"hardware"`
	Tools       []tools.Check            `json:"tools"`
	Sources     []research.Source        `json:"sources"`
	Experiments []experiments.Experiment `json:"experiments"`
	Results     []benchmark.Stored       `json:"results"`
	Commands    []security.CommandRecord `json:"commands"`
	Limitations []string                 `json:"limitations"`
}

// Limitations padrão da Fase 0.
var Limitations = []string{
	"Fase 0: nenhum código de GPU, driver, kernel ou firmware é executado ou alterado.",
	"Fontes externas NÃO foram verificadas online; 'último commit consultado' permanece vazio até verificação.",
	"Campos 'inferido' (arquitetura, gfx) vêm de tabela por PCI ID e exigem confirmação via driver/Vulkan.",
	"Ausência de evidência não é evidência de incompatibilidade.",
	"Nenhuma equivalência entre GCN3, Polaris e gfx9 foi estabelecida.",
	"O autoteste de CPU valida a infraestrutura; não mede hardware de forma comparável.",
}

func orDash(s string) string {
	if s == "" {
		return "—"
	}
	return s
}

// Markdown renderiza o relatório.
func Markdown(d Data) string {
	var b strings.Builder
	w := func(f string, a ...any) { fmt.Fprintf(&b, f, a...) }
	w("# Relatório HRAIL\n\n")
	w("- Gerado em: %s\n- Versão: %s\n- Fase: %s\n- Origem do inventário: **%s**\n\n", d.GeneratedAt, d.Version, d.Phase, d.Hardware.Origin)

	w("## Hardware\n\n")
	h := d.Hardware
	w("- Kernel: %s\n- CPU: %s (%d CPUs lógicas)\n", orDash(h.Kernel), orDash(h.CPU.Model), h.CPU.Logical)
	if len(h.CPU.Features) > 0 {
		var fs []string
		for _, k := range []string{"sse4_2", "avx", "avx2", "fma", "avx512f"} {
			if v, ok := h.CPU.Features[k]; ok {
				fs = append(fs, fmt.Sprintf("%s=%v", k, v))
			}
		}
		w("- Extensões de CPU (conforme /proc/cpuinfo): %s\n", strings.Join(fs, ", "))
	}
	w("- RAM total: %d MiB\n\n", h.Memory.TotalKiB/1024)
	if len(h.GPUs) == 0 {
		w("**Nenhuma GPU detectada.**\n\n")
	}
	for _, g := range h.GPUs {
		w("### GPU %s\n\n", g.PCIAddress)
		w("- PCI: %s:%s rev %s\n- Nome: %s (fonte: %s)\n", g.VendorID, g.DeviceID, orDash(g.Revision), orDash(g.Name), orDash(g.NameSource))
		w("- Arquitetura: %s (fonte: %s); GFX: %s\n", orDash(g.ArchFamily), orDash(g.ArchFamilySource), orDash(g.GFXID))
		w("- Driver do kernel: %s %s\n", orDash(g.KernelDriver), g.KernelDriverVersion)
		if g.VRAMTotalBytes != nil {
			w("- VRAM: %d MiB\n", *g.VRAMTotalBytes>>20)
		}
		if g.KnownVariant != nil {
			w("- ⚠ Variante: **%s** — %s\n", g.KnownVariant.Name, g.KnownVariant.Note)
		}
		if g.Vulkan != nil {
			w("- Vulkan: API %s, driver %s (%s), Mesa %s\n", orDash(g.Vulkan.APIVersion), orDash(g.Vulkan.DriverName), orDash(g.Vulkan.DriverInfo), orDash(g.Vulkan.MesaVersion))
		}
		for _, n := range g.NotDetermined {
			w("- não determinado: %s\n", n)
		}
		w("\n")
	}
	if len(h.Unavailable) > 0 {
		w("Informações indisponíveis:\n\n")
		for _, u := range h.Unavailable {
			w("- %s\n", u)
		}
		w("\n")
	}

	w("## Ferramentas\n\n| Id | Categoria | Estado | Versão | Detalhe |\n|---|---|---|---|---|\n")
	for _, t := range d.Tools {
		w("| %s | %s | %s | %s | %s |\n", t.Def.ID, t.Def.Category, t.Status, orDash(t.Version), orDash(t.Detail))
	}

	w("\n## Fontes de pesquisa\n\n| Id | Tipo | Licença (verificada?) | Verificação | Último commit |\n|---|---|---|---|---|\n")
	for _, s := range d.Sources {
		lc := "—"
		if s.LastCommitConsulted != nil {
			lc = *s.LastCommitConsulted
		}
		w("| [%s](%s) | %s | %s (%v) | %s | %s |\n", s.ID, s.URL, s.Kind, s.License, s.LicenseVerified, s.Verification.Status, lc)
	}

	w("\n## Experimentos\n\n")
	if len(d.Experiments) == 0 {
		w("Nenhum experimento registrado.\n")
	}
	for _, e := range d.Experiments {
		tag := ""
		if e.InfrastructureTest {
			tag = " — **TESTE DE INFRAESTRUTURA**"
		}
		w("- `%s` nível %s, origem %s, evidência: %s%s\n", e.ID, e.Level, e.Origin, e.State(), tag)
	}

	w("\n## Resultados (separados por origem)\n\n")
	for _, o := range []string{"measured", "simulated", "estimated", "fixture"} {
		var rs []benchmark.Stored
		for _, r := range d.Results {
			if r.Origin == o {
				rs = append(rs, r)
			}
		}
		if len(rs) == 0 {
			continue
		}
		w("### %s\n\n", o)
		for _, r := range rs {
			w("- %s: %s = %.2f %s (%s)\n", r.ExperimentID, r.Metric, r.Value, r.Unit, r.RecordedAt)
		}
		w("\n")
	}

	w("## Comandos externos executados\n\n")
	if len(d.Commands) == 0 {
		w("Nenhum.\n")
	}
	for _, c := range d.Commands {
		w("- `%s %s` → código %d (%s)%s\n", c.Command, strings.Join(c.Args, " "), c.ExitCode, c.Duration, map[bool]string{true: " **timeout**", false: ""}[c.TimedOut])
	}

	w("\n## Limitações\n\n")
	for _, l := range d.Limitations {
		w("- %s\n", l)
	}
	return b.String()
}
