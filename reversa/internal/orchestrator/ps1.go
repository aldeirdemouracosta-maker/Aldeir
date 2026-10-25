package orchestrator

import (
	"context"
	"fmt"
	"strings"

	"reversa/internal/evidence"
	"reversa/internal/llm"
	"reversa/internal/ps1"
)

// PS1 é o pipeline em três estágios:
//  1. triagem determinística em Go (sem modelo): cabeçalho, funções candidatas, desmontagem;
//  2. operários: um modelo pequeno resume cada função, em paralelo;
//  3. sintetizador: um modelo maior junta tudo, citando evidências.
//
// Fatos (saída das ferramentas) e hipóteses (texto do modelo) ficam em registros separados.
type PS1 struct {
	Worker      llm.Chatter // modelo pequeno e rápido
	Synthesizer llm.Chatter // modelo maior, uma única chamada
	Evidence    *evidence.Log
	Workers     int
	TopN        int // quantas funções analisar
	MaxInsns    int // instruções por função enviadas ao modelo
}

const workerPrompt = `Código MIPS R3000 (PlayStation 1) de uma função. Em no máximo 3 linhas em português, diga o que ela
provavelmente faz. Se não der para saber, diga "indeterminado". Não invente nomes de símbolos.

%s`

func (p *PS1) Run(ctx context.Context, exe *ps1.Exe) (string, error) {
	// Estágio 1: fatos.
	header := fmt.Sprintf("entrada=0x%08x carga=0x%08x gp=0x%08x sp=0x%08x região=%q tamanho=%d bytes",
		exe.PC, exe.Load, exe.GP, exe.SP, exe.Region, len(exe.Text))
	hdr := p.Evidence.Add("ps1_header", "", header, "Lido do cabeçalho PS-X EXE; o conteúdo não é validado.")

	funcs := exe.FindFunctions()
	if p.TopN > 0 && len(funcs) > p.TopN {
		funcs = funcs[:p.TopN]
	}
	type job struct {
		fn  ps1.Func
		dis string
		ev  int
	}
	jobs := make([]job, len(funcs))
	for i, f := range funcs {
		dis := exe.DisasmRange(f.Addr, p.MaxInsns)
		rec := p.Evidence.Add("ps1_disasm", fmt.Sprintf("0x%08x (chamada %dx)", f.Addr, f.Calls), dis,
			"Desmontagem linear; chamadas indiretas (jalr) e dados no meio do código não são resolvidos.")
		jobs[i] = job{f, dis, rec.ID}
	}

	// Estágio 2: hipóteses em paralelo.
	res := Map(ctx, jobs, p.Workers, func(ctx context.Context, j job) (string, error) {
		m, err := p.Worker.Chat(ctx, []llm.Message{{Role: "user", Content: fmt.Sprintf(workerPrompt, j.dis)}}, nil)
		if err != nil {
			return "", err
		}
		return strings.TrimSpace(m.Content), nil
	})

	var sum strings.Builder
	fmt.Fprintf(&sum, "Fatos [E%d]: %s\n\nFunções:\n", hdr.ID, header)
	for i, r := range res {
		j := jobs[i]
		if r.Err != nil {
			fmt.Fprintf(&sum, "- 0x%08x [E%d]: (falhou: %v)\n", j.fn.Addr, j.ev, r.Err)
			continue
		}
		hyp := p.Evidence.Add("llm_hipotese", fmt.Sprintf("0x%08x", j.fn.Addr), r.Val, "Hipótese do modelo; não verificada.")
		fmt.Fprintf(&sum, "- 0x%08x, chamada %dx, desmontagem [E%d], hipótese [E%d]: %s\n", j.fn.Addr, j.fn.Calls, j.ev, hyp.ID, r.Val)
	}

	// Estágio 3: síntese.
	m, err := p.Synthesizer.Chat(ctx, []llm.Message{
		{Role: "system", Content: "Você é analista de engenharia reversa de PS1. Escreva um relatório em português. Cite [E#] em cada afirmação e separe fatos de hipóteses."},
		{Role: "user", Content: sum.String()},
	}, nil)
	if err != nil {
		return "", err
	}
	return m.Content, nil
}
