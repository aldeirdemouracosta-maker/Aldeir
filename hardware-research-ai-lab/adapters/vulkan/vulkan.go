// Package vulkan é o adaptador Vulkan (Fase 0: somente detecção e metadados).
package vulkan

import (
	"context"

	"hrail/internal/tools"
)

// Adapter implementa tools.Adapter.
type Adapter struct{}

func (Adapter) ID() string { return "vulkan" }

func (Adapter) Metadata() tools.AdapterMetadata {
	return tools.AdapterMetadata{
		ID:                 "vulkan",
		Description:        "Detecção de vulkaninfo para coleta de capacidades Vulkan.",
		ToolIDs:            []string{"vulkaninfo"},
		SourceIDs:          []string{"vulkan-samples"},
		SupportedArch:      []string{"independente de fornecedor"},
		EquivalenceClaims:  []string{}, // nenhuma: sem evidência não se declara equivalência
		ExecutesWorkloads:  false,
		Phase0Capabilities: []string{"detecção", "metadados"},
	}
}

// Detect devolve o estado da ferramenta principal sem executar cargas de trabalho.
func (Adapter) Detect(ctx context.Context, r *tools.Registry) tools.Check {
	return r.DetectByID(ctx, "vulkaninfo")
}
