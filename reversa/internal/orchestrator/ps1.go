package orchestrator

import (
	"context"
	"fmt"
	"strings"
	"sync/atomic"

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
	// Progress, se definido, recebe uma linha a cada marco (estágios e funções concluídas).
	Progress func(format string, args ...any)
}

func (p *PS1) logf(format string, args ...any) {
	if p.Progress != nil {
		p.Progress(format, args...)
	}
}

const workerPrompt = `Código MIPS R3000 (PlayStation 1) de uma função.%s
Responda em no máximo 3 linhas, em português, dizendo o propósito provável da função. Use os nomes de
registradores de hardware e os endereços como aparecem no código (após ';'); não recalcule nem converta números.
Não liste instruções. Não invente símbolos. Se não der para saber, diga "indeterminado".

%s`

func (p *PS1) Run(ctx context.Context, exe *ps1.Exe) (string, error) {
	// Estágio 1: fatos.
	header := fmt.Sprintf("entrada=0x%08x carga=0x%08x gp=0x%08x sp=0x%08x região=%q tamanho=%d bytes",
		exe.PC, exe.Load, exe.GP, exe.SP, exe.Region, len(exe.Text))
	hdr := p.Evidence.AddAs(evidence.Observed, "ps1_header", "", header, "Lido do cabeçalho PS-X EXE; o conteúdo não é validado.")

	funcs := exe.FindFunctions()
	if p.TopN > 0 && len(funcs) > p.TopN {
		funcs = funcs[:p.TopN]
	}
	type job struct {
		context string
		fn      ps1.Func
		dis     string
		ev      int
		unknown int // id da evidência de saltos indiretos, 0 se não houver
	}
	jobs := make([]job, len(funcs))
	for i, f := range funcs {
		dis := exe.DisasmRange(f.Addr, p.MaxInsns)
		rec := p.Evidence.AddAs(evidence.Derived, "ps1_disasm", fmt.Sprintf("0x%08x (%s)", f.Addr, role(exe, f)), dis,
			"Desmontagem linear; chamadas indiretas (jalr) e dados no meio do código não são resolvidos.")
		jobs[i] = job{fn: f, dis: dis, ev: rec.ID, context: funcContext(exe, f, p.MaxInsns)}
		if ind := exe.Indirects(f.Addr, p.MaxInsns); len(ind) > 0 {
			var list strings.Builder
			for _, pc := range ind {
				fmt.Fprintf(&list, "0x%08x ", pc)
			}
			u := p.Evidence.AddAs(evidence.Unknown, "ps1_indirect", fmt.Sprintf("0x%08x", f.Addr), strings.TrimSpace(list.String()),
				"Destino de jr/jalr não é estático; a análise não sabe para onde esses saltos vão.")
			jobs[i].unknown = u.ID
		}
	}

	// Estágio 2: hipóteses em paralelo.
	p.logf("estágio 1/3 concluído: %d funções; resumindo com o modelo pequeno (%d em paralelo)", len(jobs), max(p.Workers, 1))
	var done atomic.Int32
	res := Map(ctx, jobs, p.Workers, func(ctx context.Context, j job) (string, error) {
		m, err := p.Worker.Chat(ctx, []llm.Message{{Role: "user", Content: fmt.Sprintf(workerPrompt, j.context, j.dis)}}, nil)
		p.logf("estágio 2/3: %d/%d funções resumidas (0x%08x)", done.Add(1), len(jobs), j.fn.Addr)
		if err != nil {
			return "", err
		}
		return strings.TrimSpace(m.Content), nil
	})

	// Os fatos de cada função vêm do programa; o modelo só escreve o resumo geral. Assim as citações [E#] e os
	// registradores de hardware nunca dependem de o modelo copiar números corretamente.
	var body, forModel strings.Builder
	fmt.Fprintf(&body, "## Fatos\n\n- Cabeçalho [E%d] (observado): %s\n\n## Funções\n", hdr.ID, header)
	fmt.Fprintf(&forModel, "Cabeçalho: %s\n\nFunções analisadas:\n", header)
	for i, r := range res {
		j := jobs[i]
		fmt.Fprintf(&body, "\n### 0x%08x (%s)\n\n- Desmontagem: [E%d] (derivada)\n", j.fn.Addr, role(exe, j.fn), j.ev)
		if hw := groupHW(exe.HWAccesses(j.fn.Addr, p.MaxInsns)); hw != "" {
			fmt.Fprintf(&body, "- Hardware tocado (derivado): %s\n", hw)
		}
		if cs := exe.Callees(j.fn.Addr, p.MaxInsns); len(cs) > 0 {
			fmt.Fprintf(&body, "- Chama: %s\n", hexList(cs))
		}
		if j.unknown != 0 {
			fmt.Fprintf(&body, "- Saltos indiretos sem destino conhecido: %s [E%d] (desconhecido)\n", hexList(exe.Indirects(j.fn.Addr, p.MaxInsns)), j.unknown)
		}
		if r.Err != nil {
			fmt.Fprintf(&body, "- Hipótese do modelo: falhou (%v)\n", r.Err)
			continue
		}
		hyp := p.Evidence.AddAs(evidence.Inferred, "llm_hipotese", fmt.Sprintf("0x%08x", j.fn.Addr), r.Val, "Hipótese do modelo; não verificada.")
		fmt.Fprintf(&body, "- Hipótese do modelo [E%d] (inferida, não verificada): %s\n", hyp.ID, oneLine(r.Val))
		fmt.Fprintf(&forModel, "- 0x%08x (%s): %s\n", j.fn.Addr, role(exe, j.fn), oneLine(r.Val))
		if j.unknown != 0 {
			fmt.Fprintf(&forModel, "  Atenção: há saltos indiretos não resolvidos; não afirme para onde vão.\n")
		}
	}

	// Estágio 3: resumo geral.
	p.logf("estágio 3/3: escrevendo o resumo geral com o modelo grande (a primeira resposta pode demorar)")
	m, err := p.Synthesizer.Chat(ctx, []llm.Message{
		{Role: "system", Content: "Você é analista de engenharia reversa de PS1. Escreva em português um resumo geral de 4 a 6 linhas sobre o que o programa parece fazer, com base nos resumos das funções. Não cite números de evidência, não liste instruções e não invente endereços ou nomes. Diga o que for incerto."},
		{Role: "user", Content: forModel.String()},
	}, nil)
	if err != nil {
		return "", err
	}
	return "# Relatório de engenharia reversa (PS1)\n\n" + body.String() +
		"\n## Resumo geral (hipótese do modelo, não verificada)\n\n" + strings.TrimSpace(m.Content) + "\n", nil
}

// groupHW agrupa acessos repetidos: "I_STAT (0x1f801070) ×2, GPU_GP1 (0x1f801814)".
func groupHW(acc []ps1.HWAccess) string {
	type key struct {
		name string
		addr uint32
	}
	var order []key
	count := map[key]int{}
	for _, a := range acc {
		k := key{a.Name, a.Addr & 0x1FFFFFFF}
		if count[k] == 0 {
			order = append(order, k)
		}
		count[k]++
	}
	parts := make([]string, len(order))
	for i, k := range order {
		parts[i] = fmt.Sprintf("%s (0x%08x)", k.name, k.addr)
		if n := count[k]; n > 1 {
			parts[i] += fmt.Sprintf(" ×%d", n)
		}
	}
	return strings.Join(parts, ", ")
}

func hexList(addrs []uint32) string {
	parts := make([]string, len(addrs))
	for i, a := range addrs {
		parts[i] = fmt.Sprintf("0x%08x", a)
	}
	return strings.Join(parts, ", ")
}

// oneLine junta a resposta do modelo numa linha para não quebrar a lista do relatório.
func oneLine(s string) string { return strings.Join(strings.Fields(s), " ") }

// role descreve como a função foi achada: o ponto de entrada não é chamado por jal.
func role(exe *ps1.Exe, f ps1.Func) string {
	if f.Addr == exe.PC {
		if f.Calls > 0 {
			return fmt.Sprintf("ponto de entrada, também chamada %dx", f.Calls)
		}
		return "ponto de entrada"
	}
	return fmt.Sprintf("chamada %dx", f.Calls)
}

// funcContext reúne fatos determinísticos que ajudam o modelo: papel da função e o que ela chama.
func funcContext(exe *ps1.Exe, f ps1.Func, maxInsns int) string {
	var b strings.Builder
	if f.Addr == exe.PC {
		b.WriteString(" É o ponto de entrada do programa.")
	}
	if cs := exe.Callees(f.Addr, maxInsns); len(cs) > 0 {
		b.WriteString(" Ela chama:")
		for _, c := range cs {
			fmt.Fprintf(&b, " 0x%08x", c)
		}
		b.WriteString(".")
	}
	return b.String()
}
