// Package mgpusim é o adaptador MGPUSim (Fase 0: somente detecção e metadados).
package mgpusim

import (
	"context"

	"hrail/internal/tools"
)

// Adapter implementa tools.Adapter.
type Adapter struct{}

func (Adapter) ID() string { return "mgpusim" }

func (Adapter) Metadata() tools.AdapterMetadata {
	return tools.AdapterMetadata{
		ID:                 "mgpusim",
		Description:        "Simulador de GPU em Go (modelo GCN3). Sem equivalência declarada com Polaris/gfx803 ou gfx9.",
		ToolIDs:            []string{"mgpusim", "go"},
		SourceIDs:          []string{"mgpusim"},
		SupportedArch:      []string{"GCN3 (documentado pelo projeto; não verificado)"},
		EquivalenceClaims:  []string{}, // nenhuma: sem evidência não se declara equivalência
		ExecutesWorkloads:  true,       // Fase 2: somente amostras do catálogo, após aprovação humana, em sandbox
		RequiresApproval:   true,
		Phase0Capabilities: []string{"detecção", "metadados", "preparo/revisão/compilação/execução controladas (Fase 2)"},
	}
}

// Detect devolve o estado da ferramenta principal sem executar cargas de trabalho.
func (Adapter) Detect(ctx context.Context, r *tools.Registry) tools.Check {
	return r.DetectByID(ctx, "mgpusim")
}
