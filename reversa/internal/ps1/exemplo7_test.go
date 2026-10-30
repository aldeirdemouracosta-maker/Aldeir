package ps1

import (
	"os"
	"testing"
)

// Endereços conferidos com `llvm-objdump -t` no ELF montado a partir de testdata/exemplo7.s.
const (
	e7SetCB    = 0x80010030
	e7Fire     = 0x8001003c
	e7SetFlag  = 0x80010058
	e7WaitFlag = 0x80010068
	e7Lookup   = 0x80010084
	e7CBPtr    = 0x8001009c
	e7Flag     = 0x800100a0
	e7Table    = 0x800100a4
)

func loadExemplo7(t *testing.T) *Exe {
	raw, err := os.ReadFile("../../testdata/exemplo7.exe")
	if err != nil {
		t.Fatal(err)
	}
	e, err := ParseExe(raw)
	if err != nil {
		t.Fatal(err)
	}
	return e
}

func TestExemplo7XrefDoCallback(t *testing.T) {
	x := loadExemplo7(t).DataXrefs(e7CBPtr, 1)
	if len(x) != 2 {
		t.Fatalf("referências ao callback: %+v", x)
	}
	// quem instala (escreve) e quem dispara (lê)
	if s := x[0]; s.PC != 0x80010038 || s.Op != "sw" || !s.Store || s.Known || s.Func != e7SetCB || s.Indexed {
		t.Errorf("instalação do callback: %+v", s)
	}
	if l := x[1]; l.PC != 0x80010040 || l.Op != "lw" || l.Store || l.Func != e7Fire {
		t.Errorf("disparo do callback: %+v", l)
	}
}

func TestExemplo7XrefDaFlagComValor(t *testing.T) {
	x := loadExemplo7(t).DataXrefs(e7Flag, 1)
	if len(x) != 2 {
		t.Fatalf("referências à flag: %+v", x)
	}
	if s := x[0]; s.PC != 0x80010064 || s.Op != "sb" || !s.Store || !s.Known || s.Value != 5 || s.Width != 1 || s.Func != e7SetFlag {
		t.Errorf("escrita da flag: %+v", s)
	}
	if l := x[1]; l.PC != 0x8001006c || l.Op != "lbu" || l.Store || l.Func != e7WaitFlag {
		t.Errorf("leitura da flag (espera): %+v", l)
	}
}

func TestExemplo7XrefDeTabelaIndexada(t *testing.T) {
	e := loadExemplo7(t)
	x := e.DataXrefs(e7Table, 12) // a tabela tem 3 palavras
	if len(x) != 1 || x[0].PC != 0x80010090 || x[0].Op != "lw" || !x[0].Indexed || x[0].Addr != e7Table || x[0].Func != e7Lookup {
		t.Fatalf("acesso indexado à tabela: %+v", x)
	}
	// um endereço sem referências devolve vazio; e a flag não aparece como tabela
	if got := e.DataXrefs(0x80012000, 4); len(got) != 0 {
		t.Errorf("endereço sem referências: %+v", got)
	}
	// range que cobre cb_ptr, flag e table inclui todos os acessos, em ordem de endereço de código
	all := e.DataXrefs(e7CBPtr, 0x20)
	if len(all) != 5 {
		t.Errorf("todas as referências: %+v", all)
	}
	for i := 1; i < len(all); i++ {
		if all[i].PC <= all[i-1].PC {
			t.Errorf("fora de ordem: %+v", all)
		}
	}
}

func TestSomaDeConstantes(t *testing.T) {
	e := &Exe{Load: 0x80010000, Text: make([]byte, 16)}
	le.PutUint32(e.Text[0:], 0x3C041F80)  // lui $a0,0x1f80
	le.PutUint32(e.Text[4:], 0x24051810)  // addiu $a1,$zero,0x1810
	le.PutUint32(e.Text[8:], 0x00851021)  // addu $v0,$a0,$a1     -> 0x1f801810
	le.PutUint32(e.Text[12:], 0xAC400000) // sw $zero,0($v0)
	acc := e.HWAccesses(0x80010000, 16)
	if len(acc) != 1 || acc[0].Name != "GPU_GP0" || !acc[0].Known || acc[0].Value != 0 {
		t.Errorf("addu de duas constantes deveria dar o endereço do GP0: %+v", acc)
	}
}
