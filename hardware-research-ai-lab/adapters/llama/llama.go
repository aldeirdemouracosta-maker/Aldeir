// Package llama é o adaptador llama.cpp (Fase 0: somente detecção e metadados).
package llama

import (
	"context"

	"hrail/internal/tools"
)

// Adapter implementa tools.Adapter.
type Adapter struct{}

func (Adapter) ID() string { return "llama" }

func (Adapter) Metadata() tools.AdapterMetadata {
	return tools.AdapterMetadata{
		ID:                 "llama",
		Description:        "Detecção de llama.cpp como provedor local de IA.",
		ToolIDs:            []string{"llama-cli", "llama-server"},
		SourceIDs:          []string{"llama-cpp"},
		SupportedArch:      []string{"CPU x86-64; Vulkan (não verificado)"},
		EquivalenceClaims:  []string{}, // nenhuma: sem evidência não se declara equivalência
		ExecutesWorkloads:  false,
		Phase0Capabilities: []string{"detecção", "metadados"},
	}
}

// Detect devolve o estado da ferramenta principal sem executar cargas de trabalho.
func (Adapter) Detect(ctx context.Context, r *tools.Registry) tools.Check {
	return r.DetectByID(ctx, "llama-cli")
}
