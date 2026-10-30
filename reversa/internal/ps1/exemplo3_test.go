package ps1

import (
	"os"
	"strings"
	"testing"
)

// Endereços conferidos com `llvm-objdump -t` no ELF montado a partir de testdata/exemplo3.s.
const (
	e3Start      = 0x80010000
	e3BIOSMalloc = 0x8001002c
	e3BIOSB      = 0x80010038
	e3PutsLike   = 0x80010044
	e3Countdown  = 0x80010064
	e3Msg        = 0x8001008c
)

func loadExemplo3(t *testing.T) *Exe {
	raw, err := os.ReadFile("../../testdata/exemplo3.exe")
	if err != nil {
		t.Fatal(err)
	}
	e, err := ParseExe(raw)
	if err != nil {
		t.Fatal(err)
	}
	return e
}

func TestExemplo3StubsDeBIOS(t *testing.T) {
	e := loadExemplo3(t)
	if c, ok := e.BIOSStub(e3BIOSMalloc); !ok || c.Table != 0xA0 || c.Func != 0x33 {
		t.Errorf("bios_malloc: %+v ok=%v", c, ok)
	}
	if c, ok := e.BIOSStub(e3BIOSB); !ok || c.Table != 0xB0 || c.Func != 0x07 {
		t.Errorf("bios_b_stub: %+v ok=%v", c, ok)
	}
	// funções comuns não são stubs
	for _, a := range []uint32{e3Start, e3PutsLike, e3Countdown} {
		if c, ok := e.BIOSStub(a); ok {
			t.Errorf("%08x não é stub de BIOS: %+v", a, c)
		}
	}
	// exemplo2 também não tem stubs
	for _, f := range loadExemplo2(t).FindFunctions() {
		if _, ok := loadExemplo2(t).BIOSStub(f.Addr); ok {
			t.Errorf("exemplo2 %08x não é stub", f.Addr)
		}
	}
}

func TestExemplo3Recursao(t *testing.T) {
	e := loadExemplo3(t)
	if !e.Recursive(e3Countdown, 96) {
		t.Error("countdown chama a si mesma")
	}
	for _, a := range []uint32{e3Start, e3PutsLike, e3BIOSMalloc} {
		if e.Recursive(a, 96) {
			t.Errorf("%08x não é recursiva", a)
		}
	}
	// puts_like chama bios_b_stub, que não é ela: era o erro "chama recursivamente" do modelo
	if cs := e.Callees(e3PutsLike, 96); len(cs) != 1 || cs[0] != e3BIOSB {
		t.Errorf("callees de puts_like: %x", cs)
	}
}

func TestExemplo3Strings(t *testing.T) {
	e := loadExemplo3(t)
	refs := e.StringRefs(e3Start, 96)
	if len(refs) != 1 || refs[0].Addr != e3Msg || refs[0].Text != "Ola, mundo PS1 teste" || refs[0].PC != 0x80010010 {
		t.Fatalf("strings de _start: %+v", refs)
	}
	for _, a := range []uint32{e3PutsLike, e3Countdown} {
		if r := e.StringRefs(uint32(a), 96); len(r) != 0 {
			t.Errorf("%08x não referencia string: %+v", a, r)
		}
	}
	// constantes que não apontam para texto não viram string (0x100 em $a0, 0x1f801810 etc.)
	if r := loadExemplo2(t).StringRefs(e2DMA, 96); len(r) != 0 {
		t.Errorf("exemplo2 dma_to_gpu: %+v", r)
	}
	if _, ok := e.asciiAt(e3Start); ok {
		t.Error("código não é string ASCII")
	}
	if !strings.Contains(e.DisasmRange(e3Start, 96), "jal 0x8001002c") {
		t.Error("desmontagem de _start")
	}
}

// Regressão: o delay slot de um jal executa antes da chamada e enxerga os registradores de antes dela.
func TestDelaySlotUsaRegistradorAnteriorAoJal(t *testing.T) {
	e := &Exe{Load: 0x80010000, Text: make([]byte, 16)}
	le.PutUint32(e.Text[0:], 0x3C041F80)  // lui $a0,0x1f80
	le.PutUint32(e.Text[4:], 0x0C004004)  // jal 0x80010010
	le.PutUint32(e.Text[8:], 0xAC801810)  // sw $zero,0x1810($a0)  (delay slot: $a0 ainda vale 0x1f800000)
	le.PutUint32(e.Text[12:], 0xAC801810) // sw $zero,0x1810($a0)  (depois da chamada: $a0 é desconhecido)
	acc := e.HWAccesses(0x80010000, 16)
	if len(acc) != 1 || acc[0].PC != 0x80010008 || acc[0].Name != "GPU_GP0" {
		t.Errorf("só o delay slot acessa hardware; depois do jal $a0 é desconhecido: %+v", acc)
	}
}

func TestExemplo3ContraLLVM(t *testing.T) {
	need(t, "clang", "ld.lld", "llvm-objcopy", "llvm-objdump")
	src, err := os.ReadFile("../../testdata/exemplo3.s")
	if err != nil {
		t.Fatal(err)
	}
	raw, elf := buildFrom(t, string(src))
	built, err := ParseExe(raw)
	if err != nil {
		t.Fatal(err)
	}
	if string(built.Text[:164]) != string(loadExemplo3(t).Text[:164]) {
		t.Error("testdata/exemplo3.exe está desatualizado em relação a exemplo3.s")
	}
	// 164 bytes = 40 instruções + a string; o llvm-objdump desmonta a string como instruções, então só
	// comparamos o trecho de código (até a etiqueta msg, 0x8001008c)
	if n := compareAll(t, raw, elf); n < 35 {
		t.Fatalf("comparou só %d instruções", n)
	}
}
