package orchestrator

import (
	"fmt"
	"sort"
	"strings"

	"reversa/internal/ps1"
)

// nameEvidence reúne pistas de nome e padrão de uma função, sem inventar: instalador de callback e string de
// depuração parecida com identificador. (Stubs de BIOS e de syscall são tratados à parte, por stubKind.)
func nameEvidence(exe *ps1.Exe, addr uint32, maxInsns int) []string {
	var ev []string
	if g, ok := exe.PointerSwap(addr); ok {
		ev = append(ev, fmt.Sprintf("instala callback: troca o ponteiro global 0x%08x e devolve o antigo", g))
	}
	for _, h := range exe.NameHints(addr, maxInsns) {
		ev = append(ev, fmt.Sprintf("nome provável %q: string de depuração referenciada em 0x%08x (heurística)", h.Text, h.Addr))
	}
	return ev
}

// NamesReport varre todas as funções achadas por chamada direta e lista só as que têm alguma evidência de nome
// ou de padrão (stub de BIOS/syscall, instalador de callback, string de depuração). Nada é inventado: cada linha
// cita a evidência, e os nomes continuam sem confirmação, porque o executável não tem símbolos.
func NamesReport(exe *ps1.Exe, maxInsns int) string {
	funcs := exe.FindFunctions()
	sort.Slice(funcs, func(i, j int) bool { return funcs[i].Addr < funcs[j].Addr })
	var lines []string
	for _, f := range funcs {
		var ev []string
		if k := stubKind(exe, f.Addr); k != "" {
			ev = append(ev, k)
		}
		ev = append(ev, nameEvidence(exe, f.Addr, maxInsns)...)
		if len(ev) == 0 {
			continue
		}
		lines = append(lines, fmt.Sprintf("- 0x%08x (%s): %s", f.Addr, role(exe, f), strings.Join(ev, "; ")))
	}
	var b strings.Builder
	fmt.Fprintf(&b, "# Nomes e padrões por evidência\n\n")
	fmt.Fprintf(&b, "- Funções com alguma evidência: %d de %d achadas por chamada direta (jal)\n", len(lines), len(funcs))
	b.WriteString("- Os nomes são pistas, não confirmações: o executável não tem símbolos, e uma string de depuração pode ser o nome de outra função usada na mensagem.\n\n")
	if len(lines) == 0 {
		b.WriteString("Nenhuma função com evidência de nome ou padrão.\n")
		return b.String()
	}
	b.WriteString(strings.Join(lines, "\n"))
	b.WriteString("\n")
	return b.String()
}
