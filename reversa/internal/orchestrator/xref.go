package orchestrator

import (
	"fmt"
	"strings"

	"reversa/internal/ps1"
)

// XrefReport lista quem lê, escreve ou monta um endereço (ou intervalo de n bytes), por função. Mostra o
// valor escrito quando é constante e marca os acessos a tabelas com índice variável.
func XrefReport(exe *ps1.Exe, addr uint32, n, max int) string {
	if n < 1 {
		n = 1
	}
	xs := exe.DataXrefs(addr, n)
	var writes, known, reads, builds, indexed int
	for _, x := range xs {
		switch {
		case x.Op == "monta endereço":
			builds++
		case x.Store:
			writes++
			if x.Known {
				known++
			}
		default:
			reads++
		}
		if x.Indexed {
			indexed++
		}
	}
	var b strings.Builder
	if n == 1 {
		fmt.Fprintf(&b, "# Referências a 0x%08x\n\n", addr)
	} else {
		fmt.Fprintf(&b, "# Referências a 0x%08x..0x%08x (%d bytes)\n\n", addr, addr+uint32(n)-1, n)
	}
	fmt.Fprintf(&b, "- Escritas: %d (com valor constante conhecido: %d); leituras: %d; montagens do endereço: %d; acessos a tabela com índice variável: %d\n", writes, known, reads, builds, indexed)
	if len(xs) == 0 {
		b.WriteString("- Nenhuma referência encontrada. O programa só enxerga endereços constantes e tabelas com base constante e índice variável.\n")
		return b.String()
	}
	b.WriteString("\n## Referências (em ordem de endereço de código)\n\n")
	for i, x := range xs {
		if max > 0 && i == max {
			fmt.Fprintf(&b, "- ... e mais %d\n", len(xs)-max)
			break
		}
		where := fmt.Sprintf("0x%08x", x.PC)
		if x.Func != 0 {
			where += fmt.Sprintf(" (a partir de 0x%08x)", x.Func)
		}
		var what string
		switch {
		case x.Op == "monta endereço":
			what = fmt.Sprintf("monta o endereço 0x%08x (addiu/ori): ponteiro, string ou função passada adiante", x.Addr)
		case x.Store && x.Known:
			what = fmt.Sprintf("%s escreve 0x%0*x", x.Op, x.Width*2, x.Value)
		case x.Store:
			what = fmt.Sprintf("%s escreve valor variável", x.Op)
		default:
			what = x.Op + " lê"
		}
		if x.Indexed {
			what += fmt.Sprintf(" [tabela de base 0x%08x, índice variável]", x.Addr)
		} else if n > 1 && x.Op != "monta endereço" {
			what += fmt.Sprintf(" [em 0x%08x]", x.Addr)
		}
		fmt.Fprintf(&b, "- %s: %s\n", where, what)
	}
	b.WriteString("\nNota: acessos por ponteiros calculados de outro jeito, e escritas feitas fora do executável, não aparecem.\n")
	return b.String()
}

// MemReport mostra os bytes da imagem do executável a partir de addr, com interpretações das palavras de 32 bits
// alinhadas (registrador de hardware, início de função, string, ponteiro para dentro da imagem). São os valores
// INICIAIS do arquivo: a memória em execução pode ter mudado, e dados não inicializados (.bss) não estão no arquivo.
func MemReport(exe *ps1.Exe, addr uint32, n int) (string, error) {
	end := exe.Load + uint32(len(exe.Text))
	if addr < exe.Load || addr >= end {
		return "", fmt.Errorf("endereço 0x%08x fora da imagem do executável (0x%08x a 0x%08x); dados não inicializados (.bss) não estão no arquivo", addr, exe.Load, end)
	}
	if n < 1 {
		n = 64
	}
	if addr+uint32(n) > end {
		n = int(end - addr)
	}
	var b strings.Builder
	fmt.Fprintf(&b, "# Memória em 0x%08x (%d bytes, valores iniciais da imagem)\n\n```\n", addr, n)
	for off := 0; off < n; off += 16 {
		row := n - off
		if row > 16 {
			row = 16
		}
		fmt.Fprintf(&b, "0x%08x: ", addr+uint32(off))
		var ascii strings.Builder
		for i := 0; i < 16; i++ {
			if i < row {
				v := exe.Text[addr-exe.Load+uint32(off+i)]
				fmt.Fprintf(&b, "%02x ", v)
				if v >= 0x20 && v <= 0x7E {
					ascii.WriteByte(v)
				} else {
					ascii.WriteByte('.')
				}
			} else {
				b.WriteString("   ")
			}
			if i%4 == 3 {
				b.WriteByte(' ')
			}
		}
		fmt.Fprintf(&b, "|%s|\n", ascii.String())
	}
	b.WriteString("```\n")
	if addr%4 != 0 {
		b.WriteString("\n(endereço desalinhado: sem interpretação de palavras de 32 bits)\n")
		return b.String(), nil
	}
	var notes []string
	for off := 0; off+4 <= n; off += 4 {
		v, _ := exe.Word(addr + uint32(off))
		at := addr + uint32(off)
		switch {
		case ps1.HWName(v) != "":
			notes = append(notes, fmt.Sprintf("0x%08x: 0x%08x = registrador de hardware %s", at, v, ps1.HWName(v)))
		default:
			if c, ok := exe.CallCount(v); ok && v >= exe.Load && v < end {
				notes = append(notes, fmt.Sprintf("0x%08x: 0x%08x = início de função conhecido (chamada %dx)", at, v, c))
			} else if s, ok := exe.StringAt(v); ok {
				notes = append(notes, fmt.Sprintf("0x%08x: 0x%08x = string %q", at, v, s))
			} else if v >= exe.Load && v < end && v != 0 {
				notes = append(notes, fmt.Sprintf("0x%08x: 0x%08x = ponteiro para dentro da imagem", at, v))
			}
		}
	}
	if len(notes) > 0 {
		b.WriteString("\n## Palavras de 32 bits que parecem endereços\n\n")
		for i, s := range notes {
			if i == 64 {
				fmt.Fprintf(&b, "- ... e mais %d\n", len(notes)-64)
				break
			}
			fmt.Fprintf(&b, "- %s\n", s)
		}
	}
	return b.String(), nil
}
