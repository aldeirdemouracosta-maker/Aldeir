package ps1

import (
	"os"
	"testing"
)

// Endereços conferidos com `llvm-objdump -t` no ELF montado a partir de testdata/exemplo6.s.
const (
	e6Send    = 0x80010020
	e6Clobber = 0x80010048
	e6UseBad  = 0x80010054
	e6PtrIdx  = 0x8001006c
	e6PtrCmd  = 0x80010070
	e6PtrBad  = 0x80010074
)

func loadExemplo6(t *testing.T) *Exe {
	raw, err := os.ReadFile("../../testdata/exemplo6.exe")
	if err != nil {
		t.Fatal(err)
	}
	e, err := ParseExe(raw)
	if err != nil {
		t.Fatal(err)
	}
	return e
}

// Regressão do primeiro jogo real: os ponteiros do CD-ROM vêm preenchidos na imagem, não por instruções.
func TestExemplo6PonteirosNosDadosIniciais(t *testing.T) {
	e := loadExemplo6(t)
	g := e.GlobalPointers()
	if len(g) != 2 || g[e6PtrIdx] != 0x1F801800 || g[e6PtrCmd] != 0x1F801801 {
		t.Fatalf("globais resolvidas: %x", g)
	}
	acc := e.HWAccesses(e6Send, 96)
	if len(acc) != 2 || acc[0].Name != "CDROM_INDEX" || acc[0].ViaGlobal != e6PtrIdx || !acc[0].Known || acc[0].Value != 0 ||
		acc[1].Name != "CDROM_REG1" || acc[1].ViaGlobal != e6PtrCmd || acc[1].Known {
		t.Errorf("acessos de send: %+v", acc)
	}
}

func TestExemplo6GlobalSobrescritaNaoViraHardware(t *testing.T) {
	e := loadExemplo6(t)
	// ptr_bad vem preenchida com 0x1f801810, mas clobber grava um valor desconhecido nela: ambígua
	if _, ok := e.GlobalPointers()[e6PtrBad]; ok {
		t.Error("ptr_bad é sobrescrita com valor desconhecido; não pode ser resolvida")
	}
	if acc := e.HWAccesses(e6UseBad, 96); len(acc) != 0 {
		t.Errorf("use_bad lê uma global ambígua: %+v", acc)
	}
	if acc := e.HWAccesses(e6Clobber, 96); len(acc) != 0 {
		t.Errorf("clobber só escreve em RAM: %+v", acc)
	}
}

func TestExemplo6ContraLLVM(t *testing.T) {
	need(t, "clang", "ld.lld", "llvm-objcopy", "llvm-objdump")
	src, err := os.ReadFile("../../testdata/exemplo6.s")
	if err != nil {
		t.Fatal(err)
	}
	raw, elf := buildFrom(t, string(src))
	built, err := ParseExe(raw)
	if err != nil {
		t.Fatal(err)
	}
	if string(built.Text[:120]) != string(loadExemplo6(t).Text[:120]) {
		t.Error("testdata/exemplo6.exe está desatualizado em relação a exemplo6.s")
	}
	if n := compareAll(t, raw, elf); n < 25 {
		t.Fatalf("comparou só %d instruções", n)
	}
}
