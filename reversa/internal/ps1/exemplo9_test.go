package ps1

import (
	"os"
	"testing"
)

// Endereços conferidos com `llvm-objdump -t` no ELF montado a partir de testdata/exemplo9.s.
const (
	e9SwapA   = 0x80010030
	e9SwapB   = 0x80010040
	e9OnlySet = 0x80010054
	e9Ident   = 0x80010060
	e9NoIdent = 0x8001006c
	e9CBA     = 0x80010078
	e9CBB     = 0x8001007c
	e9NmIdent = 0x80010080
)

func loadExemplo9(t *testing.T) *Exe {
	raw, err := os.ReadFile("../../testdata/exemplo9.exe")
	if err != nil {
		t.Fatal(err)
	}
	e, err := ParseExe(raw)
	if err != nil {
		t.Fatal(err)
	}
	return e
}

func TestExemplo9InstaladorDeCallback(t *testing.T) {
	e := loadExemplo9(t)
	if g, ok := e.PointerSwap(e9SwapA); !ok || g != e9CBA {
		t.Errorf("swap_a: %x %v", g, ok)
	}
	if g, ok := e.PointerSwap(e9SwapB); !ok || g != e9CBB {
		t.Errorf("swap_b: %x %v", g, ok)
	}
	// só grava, sem devolver o antigo: não é troca
	for _, a := range []uint32{e9OnlySet, e9Ident, e9NoIdent, e9Start()} {
		if g, ok := e.PointerSwap(a); ok {
			t.Errorf("%08x não é instalador de callback: %x", a, g)
		}
	}
}

func e9Start() uint32 { return 0x80010000 }

func TestExemplo9NomePorStringDeDepuracao(t *testing.T) {
	e := loadExemplo9(t)
	h := e.NameHints(e9Ident, 96)
	if len(h) != 1 || h[0].Text != "CD_sync" || h[0].Addr != e9NmIdent {
		t.Fatalf("pista de nome: %+v", h)
	}
	// "hello world foo" é uma string, mas tem espaços: não parece identificador
	if got := e.NameHints(e9NoIdent, 96); len(got) != 0 {
		t.Errorf("frase não é nome: %+v", got)
	}
	if got := e.StringRefs(e9NoIdent, 96); len(got) != 1 || got[0].Text != "hello world foo" {
		t.Errorf("a frase ainda é uma string referenciada: %+v", got)
	}
	// o nome também não pode vir de funções sem strings
	if got := e.NameHints(e9SwapA, 96); len(got) != 0 {
		t.Errorf("swap_a não referencia string: %+v", got)
	}
}

func TestExemplo9ContraLLVM(t *testing.T) {
	need(t, "clang", "ld.lld", "llvm-objcopy", "llvm-objdump")
	src, err := os.ReadFile("../../testdata/exemplo9.s")
	if err != nil {
		t.Fatal(err)
	}
	raw, elf := buildFrom(t, string(src))
	built, err := ParseExe(raw)
	if err != nil {
		t.Fatal(err)
	}
	if string(built.Text[:152]) != string(loadExemplo9(t).Text[:152]) {
		t.Error("testdata/exemplo9.exe está desatualizado em relação a exemplo9.s")
	}
	if n := compareUntil(t, raw, elf, e9CBA); n < 25 { // só o código, antes das variáveis e strings
		t.Fatalf("comparou só %d instruções", n)
	}
}
