// Package gem5 é o adaptador gem5 (Fase 0: somente detecção e metadados).
package gem5

import (
	"context"

	"hrail/internal/tools"
)

// Adapter implementa tools.Adapter.
type Adapter struct{}

func (Adapter) ID() string { return "gem5" }

func (Adapter) Metadata() tools.AdapterMetadata {
	return tools.AdapterMetadata{
		ID:                 "gem5",
		Description:        "Simulador de arquiteturas; Fase 0 apenas detecta binários gem5.*.",
		ToolIDs:            []string{"gem5", "python3", "gcc"},
		SourceIDs:          []string{"gem5-repo", "gem5-site"},
		SupportedArch:      []string{"x86 (não verificado)"},
		EquivalenceClaims:  []string{}, // nenhuma: sem evidência não se declara equivalência
		ExecutesWorkloads:  false,
		Phase0Capabilities: []string{"detecção", "metadados"},
	}
}

// Detect devolve o estado da ferramenta principal sem executar cargas de trabalho.
func (Adapter) Detect(ctx context.Context, r *tools.Registry) tools.Check {
	return r.DetectByID(ctx, "gem5")
}
