// Package mesa é o adaptador Mesa/RADV/NIR/ACO (Fase 0: somente detecção e metadados).
package mesa

import (
	"context"

	"hrail/internal/tools"
)

// Adapter implementa tools.Adapter.
type Adapter struct{}

func (Adapter) ID() string { return "mesa" }

func (Adapter) Metadata() tools.AdapterMetadata {
	return tools.AdapterMetadata{
		ID:                 "mesa",
		Description:        "Inventário da pilha Mesa; NIR e ACO são internos ao código-fonte.",
		ToolIDs:            []string{"radv-icd", "nir", "aco"},
		SourceIDs:          []string{"mesa", "radv-docs"},
		SupportedArch:      []string{"AMD GCN/RDNA via RADV (não verificado)"},
		EquivalenceClaims:  []string{}, // nenhuma: sem evidência não se declara equivalência
		ExecutesWorkloads:  false,
		Phase0Capabilities: []string{"detecção", "metadados"},
	}
}

// Detect devolve o estado da ferramenta principal sem executar cargas de trabalho.
func (Adapter) Detect(ctx context.Context, r *tools.Registry) tools.Check {
	return r.DetectByID(ctx, "radv-icd")
}
