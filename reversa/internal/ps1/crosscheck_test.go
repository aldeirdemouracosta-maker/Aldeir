package ps1

import (
	"bytes"
	"fmt"
	"math/rand"
	"os/exec"
	"strings"
	"testing"
)

// llvmMnemonic devolve o mnemônico do llvm-mc (MIPS-I little-endian) ou "" se a palavra for inválida.
func llvmMnemonic(w uint32) string {
	in := fmt.Sprintf("0x%02x 0x%02x 0x%02x 0x%02x", byte(w), byte(w>>8), byte(w>>16), byte(w>>24))
	cmd := exec.Command("llvm-mc", "--disassemble", "-triple=mipsel", "-mcpu=mips1")
	cmd.Stdin = strings.NewReader(in)
	var out bytes.Buffer
	cmd.Stdout = &out
	if cmd.Run() != nil {
		return ""
	}
	for _, line := range strings.Split(out.String(), "\n") {
		f := strings.Fields(line)
		if len(f) > 0 && !strings.HasPrefix(f[0], ".") {
			return f[0]
		}
	}
	return ""
}

// aliases que o llvm imprime em vez do mnemônico real.
var aliases = map[string]bool{"move": true, "b": true, "beqz": true, "bnez": true, "negu": true, "not": true, "neg": true,
	"bal": true, "bgezal": true, "li": true, "jalr": true, "bc2f": true, "bc2t": true}

// TestContraLLVM compara o mnemônico do nosso desmontador com o do llvm-mc em instruções aleatórias.
// Pulado se o llvm-mc não estiver instalado.
func TestContraLLVM(t *testing.T) {
	if _, err := exec.LookPath("llvm-mc"); err != nil {
		t.Skip("llvm-mc não instalado")
	}
	rng := rand.New(rand.NewSource(1))
	var bad []string
	compared := 0
	for i := 0; i < 600; i++ {
		w := rng.Uint32()
		ref := llvmMnemonic(w)
		if ref == "" || aliases[ref] {
			continue
		}
		ours := strings.Fields(Disasm(w, 0x80010000))[0]
		if ours == ".word" || strings.HasPrefix(ours, "cop2") {
			continue // não coberto ainda; não é divergência
		}
		compared++
		if ours != ref {
			bad = append(bad, fmt.Sprintf("%08x: nosso=%q llvm=%q", w, Disasm(w, 0x80010000), ref))
		}
	}
	t.Logf("comparadas %d instruções", compared)
	if compared < 100 {
		t.Fatalf("só %d instruções comparadas; o teste ficou vazio", compared)
	}
	if len(bad) > 0 {
		t.Fatalf("%d divergências:\n%s", len(bad), strings.Join(bad[:min(len(bad), 15)], "\n"))
	}
}
