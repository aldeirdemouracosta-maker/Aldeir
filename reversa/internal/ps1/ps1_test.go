package ps1

import (
	"encoding/binary"
	"strings"
	"testing"
)

func TestDisasm(t *testing.T) {
	cases := map[uint32]string{
		0x3C08A001: "lui $t0,0xa001",
		0x24020001: "addiu $v0,$zero,1",
		0x03E00008: "jr $ra",
		0x8FBF0010: "lw $ra,16($sp)",
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
	if out := e.DisasmRange(0x80010010, 16); !strings.Contains(out, "addiu $v0,$zero,1") {
		t.Errorf("desmontagem: %s", out)
	}
	if _, err := ParseExe([]byte("lixo")); err == nil {
		t.Error("esperava erro para arquivo inválido")
	}
}
