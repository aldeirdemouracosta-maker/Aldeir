package orchestrator

import (
	"context"
	"fmt"
	"strings"

	"reversa/internal/llm"
	"reversa/internal/ps1"
)

// FuncReport descreve uma função só com fatos do programa (sem modelo): tamanho, quem a chama, o que ela
// chama, hardware, laços, strings, recursão, saltos indiretos e a desmontagem anotada.
func FuncReport(exe *ps1.Exe, addr uint32, maxInsns int) (string, error) {
	if _, ok := exe.Word(addr); !ok {
		return "", fmt.Errorf("endereço 0x%08x fora do código (0x%08x a 0x%08x) ou desalinhado", addr, exe.Load, exe.Load+uint32(len(exe.Text)))
	}
	n := exe.FuncLen(addr, maxInsns)
	var b strings.Builder
	fmt.Fprintf(&b, "# Função 0x%08x\n\n", addr)
	fmt.Fprintf(&b, "- Tamanho (heurístico): %d instruções, 0x%08x a 0x%08x\n", n, addr, addr+uint32(n)*4-4)
	if exe.Truncated(addr, maxInsns) {
		fmt.Fprintf(&b, "- AVISO: a função continua além de %d instruções; a análise abaixo está truncada (use -insns maior)\n", maxInsns)
	}
	callers := exe.Callers(addr)
	switch {
	case addr == exe.PC && len(callers) == 0:
		b.WriteString("- Papel: ponto de entrada do programa\n")
	case addr == exe.PC:
		fmt.Fprintf(&b, "- Papel: ponto de entrada do programa, também chamada %dx\n", len(callers))
	}
	if len(callers) > 0 {
		const max = 15
		parts := make([]string, 0, max)
		for i, pc := range callers {
			if i == max {
				parts = append(parts, fmt.Sprintf("... e mais %d", len(callers)-max))
				break
			}
			if from, ok := exe.NearestStart(pc); ok {
				parts = append(parts, fmt.Sprintf("0x%08x (a partir de 0x%08x)", pc, from))
			} else {
				parts = append(parts, fmt.Sprintf("0x%08x", pc))
			}
		}
		fmt.Fprintf(&b, "- Chamada por %d instrução(ões) jal: %s\n", len(callers), strings.Join(parts, ", "))
		b.WriteString("  (\"a partir de\" é o início de função conhecido mais próximo antes da chamada: aproximação)\n")
	} else if addr != exe.PC {
		b.WriteString("- Nenhuma chamada direta (jal) a esta função: só é alcançável por jalr, salto ou tabela\n")
	}
	if k := stubKind(exe, addr); k != "" {
		fmt.Fprintf(&b, "- Tipo (derivado): %s\n", k)
	}
	if cs := exe.Callees(addr, maxInsns); len(cs) > 0 {
		fmt.Fprintf(&b, "- Chama: %s\n", hexList(cs))
	}
	if exe.Recursive(addr, maxInsns) {
		b.WriteString("- Recursão (derivado): chama a si mesma\n")
	}
	if hw := hwFacts(exe.HWAccesses(addr, maxInsns)); hw != "" {
		fmt.Fprintf(&b, "- Hardware tocado (derivado): %s\n", hw)
	}
	if lp := loopFacts(exe.Loops(addr, maxInsns)); lp != "" {
		fmt.Fprintf(&b, "- Laços (derivado): %s\n", lp)
	}
	if st := stringFacts(exe.StringRefs(addr, maxInsns)); st != "" {
		fmt.Fprintf(&b, "- Strings referenciadas (derivado): %s\n", st)
	}
	if jt := jumpTableFacts(exe.JumpTables(addr, maxInsns)); jt != "" {
		fmt.Fprintf(&b, "- Tabelas de salto (derivado): %s\n", jt)
		b.WriteString("  (as entradas são lidas da imagem até a primeira palavra que não aponta para dentro da função)\n")
	}
	if ind := unresolved(exe, addr, maxInsns); len(ind) > 0 {
		fmt.Fprintf(&b, "- Saltos indiretos sem destino conhecido: %s\n", hexList(ind))
	}
	fmt.Fprintf(&b, "\n## Desmontagem\n\n```\n%s```\n", exe.DisasmRange(addr, maxInsns))
	return b.String(), nil
}

// ExplainFunction pede ao modelo uma explicação de UMA função, com os mesmos fatos do relatório no prompt.
// Devolve o texto e, se a hipótese contradiz fatos derivados, os motivos (ela deve ser descartada).
func ExplainFunction(ctx context.Context, chat llm.Chatter, exe *ps1.Exe, addr uint32, maxInsns int) (string, []string, error) {
	if _, ok := exe.Word(addr); !ok {
		return "", nil, fmt.Errorf("endereço 0x%08x fora do código", addr)
	}
	f := ps1.Func{Addr: addr, Calls: len(exe.Callers(addr))}
	prompt := fmt.Sprintf(workerPrompt, funcContext(exe, f, maxInsns), exe.DisasmRange(addr, maxInsns))
	m, err := chat.Chat(ctx, []llm.Message{{Role: "user", Content: prompt}}, nil)
	if err != nil {
		return "", nil, err
	}
	text := strings.TrimSpace(m.Content)
	return text, contradictions(exe, f, text, maxInsns), nil
}
