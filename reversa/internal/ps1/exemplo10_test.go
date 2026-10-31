package ps1

import (
	"os"
	"testing"
)

const (
	e10SwapCB  = 0x80010020
	e10Fire    = 0x80010030
	e10SwapLvl = 0x8001004c
	e10CB      = 0x8001005c
	e10Lvl     = 0x80010060
	e10JalrPC  = 0x8001003c
)

func loadExemplo10(t *testing.T) *Exe {
	raw, err := os.ReadFile("../../testdata/exemplo10.exe")
	if err != nil {
		t.Fatal(err)
	}
	e, err := ParseExe(raw)
	if err != nil {
		t.Fatal(err)
	}
	return e
}

func TestExemplo10GlobaisChamadasPorPonteiro(t *testing.T) {
	e := loadExemplo10(t)
	cbs := e.CallbackGlobals()
	if len(cbs) != 1 || cbs[e10CB] != e10JalrPC {
		t.Fatalf("globais chamadas por jalr: %x", cbs)
	}
	if _, ok := cbs[e10Lvl]; ok {
		t.Error("a global de nível nunca é chamada por jalr")
	}
	// as duas funções têm o padrão de troca; só a de callback usa a global como destino de chamada
	for _, c := range []struct{ fn, g uint32 }{{e10SwapCB, e10CB}, {e10SwapLvl, e10Lvl}} {
		if g, ok := e.PointerSwap(c.fn); !ok || g != c.g {
			t.Errorf("PointerSwap(%08x): %x %v", c.fn, g, ok)
		}
	}
	// nos outros exemplos nenhuma global é chamada por ponteiro, exceto o callback de exemplo7
	if got := loadExemplo9(t).CallbackGlobals(); len(got) != 0 {
		t.Errorf("exemplo9 não chama globais: %x", got)
	}
	if got := loadExemplo7(t).CallbackGlobals(); len(got) != 1 || got[e7CBPtr] != 0x80010048 {
		t.Errorf("exemplo7 chama cb_ptr por jalr em 0x80010048: %x", got)
	}
}

func TestExemplo10ContraLLVM(t *testing.T) {
	need(t, "clang", "ld.lld", "llvm-objcopy", "llvm-objdump")
	src, err := os.ReadFile("../../testdata/exemplo10.s")
	if err != nil {
		t.Fatal(err)
	}
	raw, elf := buildFrom(t, string(src))
	built, err := ParseExe(raw)
	if err != nil {
		t.Fatal(err)
	}
	if string(built.Text[:100]) != string(loadExemplo10(t).Text[:100]) {
		t.Error("testdata/exemplo10.exe está desatualizado em relação a exemplo10.s")
	}
	if n := compareUntil(t, raw, elf, e10CB); n < 20 {
		t.Fatalf("comparou só %d instruções", n)
	}
}
