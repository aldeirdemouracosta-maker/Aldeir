package ps1

import (
	"encoding/binary"
	"os"
	"strings"
	"testing"
)

func TestDisasm(t *testing.T) {
	cases := map[uint32]string{
		0x3C08A001: "lui $t0,0xa001",
		0x24020001: "addiu $v0,$zero,0x1",
		0x03E00008: "jr $ra",
		0x8FBF0010: "lw $ra,0x10($sp)",
		0x00000000: "nop",
		0x00851021: "addu $v0,$a0,$a1",
	}
	for w, want := range cases {
		if got := Disasm(w, 0x80010000); got != want {
			t.Errorf("%08x: got %q want %q", w, got, want)
		}
	}
	if got := Disasm(0x0C004004, 0x80010000); got != "jal 0x80010010" {
		t.Errorf("jal: %q", got)
	}
}

// Monta um PS-X EXE mínimo: main chama f duas vezes.
func sample() []byte {
	b := make([]byte, headerSize)
	copy(b, "PS-X EXE")
	put := func(off int, v uint32) { binary.LittleEndian.PutUint32(b[off:], v) }
	code := []uint32{0x0C004004, 0, 0x0C004004, 0, 0x24020001, 0x03E00008, 0}
	put(0x10, 0x80010000)
	put(0x18, 0x80010000)
	put(0x1C, uint32(len(code)*4))
	copy(b[0x4C:], "Sony Computer Entertainment Inc. for North America area")
	for _, w := range code {
		b = binary.LittleEndian.AppendUint32(b, w)
	}
	return b
}

func TestParseEFuncoes(t *testing.T) {
	e, err := ParseExe(sample())
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(e.Region, "North America") {
		t.Errorf("região: %q", e.Region)
	}
	fs := e.FindFunctions()
	if fs[0].Addr != 0x80010010 || fs[0].Calls != 2 {
		t.Errorf("função mais chamada: %+v", fs[0])
	}
	if out := e.DisasmRange(0x80010010, 16); !strings.Contains(out, "addiu $v0,$zero,0x1") {
		t.Errorf("desmontagem: %s", out)
	}
	if _, err := ParseExe([]byte("lixo")); err == nil {
		t.Error("esperava erro para arquivo inválido")
	}
}

func TestHWName(t *testing.T) {
	cases := map[uint32]string{
		0x1F801810: "GPU_GP0", 0xBF801814: "GPU_GP1", 0x9F801070: "I_STAT",
		0x1F8010A8: "DMA2_GPU_CHCR", 0x1F801108: "TIMER0_TARGET", 0x1F801C10: "SPU_VOICE1_+0x0",
		0x80010000: "", 0x1F800000: "",
	}
	for a, want := range cases {
		if got := HWName(a); got != want {
			t.Errorf("%08x: %q, esperado %q", a, got, want)
		}
	}
}

func TestAnotacaoDeHardware(t *testing.T) {
	// lui t0,0x1f80 ; sw v0,0x1810(t0) ; lui t1,0x1f80 ; addiu t1,t1,0x1814 ; lw v1,0(t1) ; jr ra ; nop
	code := []uint32{0x3C081F80, 0xAD021810, 0x3C091F80, 0x25291814, 0x8D230000, 0x03E00008, 0}
	e := &Exe{Load: 0x80010000, Text: make([]byte, len(code)*4)}
	for i, w := range code {
		le.PutUint32(e.Text[i*4:], w)
	}
	out := e.DisasmRange(0x80010000, 16)
	if !strings.Contains(out, "sw $v0,0x1810($t0)  ; GPU_GP0 (0x1f801810)") {
		t.Errorf("faltou GP0:\n%s", out)
	}
	if !strings.Contains(out, "lw $v1,0x0($t1)  ; GPU_GP1 (0x1f801814)") {
		t.Errorf("faltou GP1 via addiu:\n%s", out)
	}
}

func TestIndirects(t *testing.T) {
	code := []uint32{0x0100F809, 0, 0x01000008, 0, 0x03E00008, 0} // jalr t0 ; jr t0 ; jr ra
	e := &Exe{Load: 0x80010000, Text: make([]byte, len(code)*4)}
	for i, w := range code {
		le.PutUint32(e.Text[i*4:], w)
	}
	got := e.Indirects(0x80010000, 6)
	if len(got) != 2 || got[0] != 0x80010000 || got[1] != 0x80010008 {
		t.Fatalf("indiretos: %x", got)
	}
}

// Regressão: deslocamentos em decimal levaram o modelo a escrever "0x4256" para 0x10a0.
func TestDeslocamentosEmHexadecimal(t *testing.T) {
	e := &Exe{Load: 0x80010000, Text: make([]byte, 8)}
	le.PutUint32(e.Text, 0x3C081F80)     // lui $t0,0x1f80
	le.PutUint32(e.Text[4:], 0xAD0410A0) // sw $a0,0x10a0($t0)
	out := e.DisasmRange(0x80010000, 8)
	if !strings.Contains(out, "sw $a0,0x10a0($t0)  ; DMA2_GPU_MADR (0x1f8010a0)") || strings.Contains(out, "4256") {
		t.Errorf("deslocamento deveria estar em hexadecimal:\n%s", out)
	}
	if got := Disasm(0x27BDFFF8, 0x80010000); got != "addiu $sp,$sp,-0x8" {
		t.Errorf("imediato negativo: %q", got)
	}
}

func TestHWAccesses(t *testing.T) {
	e := loadExemplo2ParaHW(t)
	acc := e.HWAccesses(0x80010074, 96) // wait_vblank
	if len(acc) != 2 || acc[0].Name != "I_STAT" || acc[0].Addr != 0x1F801070 || acc[1].PC != 0x8001008c {
		t.Errorf("acessos de wait_vblank: %+v", acc)
	}
}

func loadExemplo2ParaHW(t *testing.T) *Exe {
	raw, err := os.ReadFile("../../testdata/exemplo2.exe")
	if err != nil {
		t.Fatal(err)
	}
	e, err := ParseExe(raw)
	if err != nil {
		t.Fatal(err)
	}
	return e
}
