// Package compiler implementa o compiler-lab: inventário de Mesa/RADV/NIR/ACO e
// ferramentas de shader. Fase 0: inventário e prontidão para análise offline.
package compiler

import (
	"context"

	"hrail/internal/tools"
)

// Inventory agrupa ferramentas do laboratório de compilação.
type Inventory struct {
	Mesa    []tools.Check `json:"mesa"`
	Shader  []tools.Check `json:"shader"`
	Offline []Capability  `json:"offline_capabilities"`
}

// Capability descreve se uma análise offline é possível com as ferramentas atuais.
type Capability struct {
	Name     string `json:"name"`
	Possible bool   `json:"possible"`
	Reason   string `json:"reason"`
}

// Collect verifica as ferramentas de categoria mesa e shader.
func Collect(ctx context.Context, reg *tools.Registry) Inventory {
	var inv Inventory
	st := map[string]tools.Status{}
	for _, d := range reg.Defs {
		if d.Category != "mesa" && d.Category != "shader" {
			continue
		}
		c := reg.CheckOne(ctx, d)
		st[d.ID] = c.Status
		if d.Category == "mesa" {
			inv.Mesa = append(inv.Mesa, c)
		} else {
			inv.Shader = append(inv.Shader, c)
		}
	}
	ok := func(id string) bool { return st[id] == tools.Disponivel }
	cap := func(name string, possible bool, why string) {
		inv.Offline = append(inv.Offline, Capability{name, possible, why})
	}
	if ok("glslangValidator") || ok("glslc") {
		cap("GLSL → SPIR-V", true, "compilador de shader disponível")
	} else {
		cap("GLSL → SPIR-V", false, "nem glslangValidator nem glslc encontrados")
	}
	if ok("spirv-val") {
		cap("validação SPIR-V", true, "spirv-val disponível")
	} else {
		cap("validação SPIR-V", false, "spirv-val ausente")
	}
	cap("análise NIR/ACO", false, "requer código-fonte do Mesa (planejado para a Fase 3); nada é baixado automaticamente")
	return inv
}
