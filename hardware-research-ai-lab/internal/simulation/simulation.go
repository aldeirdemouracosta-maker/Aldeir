// Package simulation implementa o simulation-engine (Fase 0: detecção e metadados).
// Nenhuma simulação é executada.
package simulation

import (
	"context"
	"errors"
	"fmt"

	"hrail/adapters/gem5"
	"hrail/adapters/mgpusim"
	"hrail/internal/tools"
)

// Simulator é a interface para futuros simuladores.
type Simulator interface {
	tools.Adapter
}

// Engine mantém os adaptadores registrados.
type Engine struct {
	Adapters []Simulator
	Registry *tools.Registry
}

// New cria o engine com os adaptadores iniciais: MGPUSim e gem5.
func New(reg *tools.Registry) *Engine {
	return &Engine{Adapters: []Simulator{mgpusim.Adapter{}, gem5.Adapter{}}, Registry: reg}
}

// Info é o relatório de um adaptador.
type Info struct {
	Metadata tools.AdapterMetadata `json:"metadata"`
	Check    tools.Check           `json:"check"`
	Notice   string                `json:"notice"`
}

// Describe detecta cada simulador e devolve metadados. Não executa simulações.
func (e *Engine) Describe(ctx context.Context) []Info {
	var out []Info
	for _, a := range e.Adapters {
		out = append(out, Info{
			Metadata: a.Metadata(), Check: a.Detect(ctx, e.Registry),
			Notice: "Fase 0: somente detecção. Nenhuma equivalência entre GCN3, Polaris e gfx9 foi estabelecida.",
		})
	}
	return out
}

// ErrSemEvidencia é devolvido ao tentar declarar equivalência arquitetural sem evidência.
var ErrSemEvidencia = errors.New("equivalência arquitetural não pode ser declarada sem evidência")

// EquivalenceClaim é uma alegação registrada (não uma verdade).
type EquivalenceClaim struct {
	A        string   `json:"a"`
	B        string   `json:"b"`
	Evidence []string `json:"evidence"`
	Status   string   `json:"status"`
}

// ClaimEquivalence recusa alegações sem evidência (ex.: GCN3 == Polaris == gfx9).
// Mesmo com evidência, o status é apenas "alegada_nao_validada" até calibração medida.
func ClaimEquivalence(a, b string, evidence []string) (EquivalenceClaim, error) {
	if len(evidence) == 0 {
		return EquivalenceClaim{}, fmt.Errorf("%w: %s ≡ %s", ErrSemEvidencia, a, b)
	}
	return EquivalenceClaim{A: a, B: b, Evidence: evidence, Status: "alegada_nao_validada"}, nil
}
