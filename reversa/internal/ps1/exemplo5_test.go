package ps1

import (
	"os"
	"strings"
	"testing"
)

// Endereços conferidos com `llvm-objdump -t` no ELF montado a partir de testdata/exemplo5.s.
const (
	e5Start       = 0x80010000
	e5Init        = 0x80010028
	e5SendCmd     = 0x80010058
	e5UseConflict = 0x8001007c
	e5Fmt         = 0x80010094
)

func loadExemplo5(t *testing.T) *Exe {
	raw, err := os.ReadFile("../../testdata/exemplo5.exe")
	if err != nil {
		t.Fatal(err)
	}
	e, err := ParseExe(raw)
	if err != nil {
		t.Fatal(err)
	}
	return e
}

func TestExemplo5PonteirosGlobaisDeHardware(t *testing.T) {
	e := loadExemplo5(t)
	g := e.GlobalPointers()
	// as duas globais sempre inicializadas com o mesmo endereço de hardware são resolvidas;
	// a que recebe dois valores diferentes (0x80020020) não
	if len(g) != 2 || g[0x80020010] != 0x1F801800 || g[0x80020014] != 0x1F801801 {
		t.Fatalf("globais resolvidas: %x", g)
	}
	acc := e.HWAccesses(e5SendCmd, 96)
	if len(acc) != 2 {
		t.Fatalf("acessos de send_cmd: %+v", acc)
	}
	a0, a1 := acc[0], acc[1]
	if a0.Name != "CDROM_INDEX" || !a0.Store || !a0.Known || a0.Value != 0 || a0.Width != 1 || a0.ViaGlobal != 0x80020010 {
		t.Errorf("índice: %+v", a0)
	}
	if a1.Name != "CDROM_REG1" || !a1.Store || a1.Known || a1.ViaGlobal != 0x80020014 {
		t.Errorf("comando (valor vem de $a0, desconhecido): %+v", a1)
	}
	out := e.DisasmRange(e5SendCmd, 96)
	if !strings.Contains(out, "; CDROM_INDEX (0x1f801800) via ponteiro global 0x80020010") {
		t.Errorf("desmontagem sem a origem do ponteiro:\n%s", out)
	}
}

func TestExemplo5GlobalAmbiguaNaoViraHardware(t *testing.T) {
	e := loadExemplo5(t)
	if acc := e.HWAccesses(e5UseConflict, 96); len(acc) != 0 {
		t.Errorf("a global 0x80020020 recebe dois valores; não pode virar hardware: %+v", acc)
	}
	// o código de init guarda constantes em globais, mas a escrita em RAM não é hardware
	if acc := e.HWAccesses(e5Init, 96); len(acc) != 0 {
		t.Errorf("init só escreve em RAM: %+v", acc)
	}
	// nos exemplos anteriores não existem globais de hardware
	for _, f := range []*Exe{loadExemplo2(t), loadExemplo3(t)} {
		if g := f.GlobalPointers(); len(g) != 0 {
			t.Errorf("globais inesperadas: %x", g)
		}
	}
}

func TestExemplo5StringDeFormato(t *testing.T) {
	e := loadExemplo5(t)
	refs := e.StringRefs(e5UseConflict, 96)
	if len(refs) != 1 || refs[0].Addr != e5Fmt || refs[0].Text != "CD_cw: %s\n" {
		t.Errorf("string de formato com \\n e %%s: %+v", refs)
	}
	// código e bytes de controle continuam não sendo string
	if _, ok := e.asciiAt(e5Start); ok {
		t.Error("código não é string")
	}
}

func TestExemplo5ContraLLVM(t *testing.T) {
	need(t, "clang", "ld.lld", "llvm-objcopy", "llvm-objdump")
	src, err := os.ReadFile("../../testdata/exemplo5.s")
	if err != nil {
		t.Fatal(err)
	}
	raw, elf := buildFrom(t, string(src))
	built, err := ParseExe(raw)
	if err != nil {
		t.Fatal(err)
	}
	if string(built.Text[:160]) != string(loadExemplo5(t).Text[:160]) {
		t.Error("testdata/exemplo5.exe está desatualizado em relação a exemplo5.s")
	}
	if n := compareAll(t, raw, elf); n < 35 {
		t.Fatalf("comparou só %d instruções", n)
	}
}

func TestTruncated(t *testing.T) {
	e := loadExemplo2(t)
	if e.Truncated(e2WaitVblank, 96) {
		t.Error("wait_vblank termina em 9 instruções")
	}
	if !e.Truncated(e2WaitVblank, 5) {
		t.Error("com limite de 5 instruções wait_vblank está truncada")
	}
	if e.Truncated(e2WaitVblank, 9) { // limite exato: termina no jr+delay
		t.Error("com limite igual ao tamanho a função não está truncada")
	}
}
