package ps1

import (
	"encoding/binary"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
)

// Programa MIPS-I montado por um assembler independente (clang/lld). Não foi escrito em hexadecimal por nós.
const asmProg = `
	.set noreorder
	.set noat
	.text
	.globl _start
_start:
	lui	$t0, 0x1f80
	ori	$t0, $t0, 0x1810
	jal	init_gpu
	nop
	jal	send
	addiu	$a0, $zero, 7
	jal	send
	addiu	$a0, $zero, 9
loop:
	j	loop
	nop
init_gpu:
	lui	$t1, 0x1f80
	sw	$zero, 0x1814($t1)
	lui	$t2, 0x1f80
	lw	$v0, 0x1070($t2)
	jr	$ra
	nop
send:
	lui	$t1, 0x1f80
	sw	$a0, 0x1810($t1)
	lui	$t3, 0x8002
	lw	$t4, 0($t3)
	jalr	$t4
	nop
	jr	$ra
	nop
`

func need(t *testing.T, tools ...string) {
	for _, tl := range tools {
		if _, err := exec.LookPath(tl); err != nil {
			t.Skipf("%s não instalado", tl)
		}
	}
}

func sh(t *testing.T, dir, name string, args ...string) string {
	cmd := exec.Command(name, args...)
	cmd.Dir = dir
	out, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("%s %v: %v\n%s", name, args, err, out)
	}
	return string(out)
}

// buildExe monta, liga em 0x80010000 e embrulha em PS-X EXE. Devolve o EXE e o ELF.
func buildExe(t *testing.T) (exe []byte, elf string) {
	need(t, "clang", "ld.lld", "llvm-objcopy")
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "p.s"), []byte(asmProg), 0o644); err != nil {
		t.Fatal(err)
	}
	sh(t, dir, "clang", "--target=mipsel-none-elf", "-march=mips1", "-mno-abicalls", "-c", "p.s", "-o", "p.o")
	sh(t, dir, "ld.lld", "-m", "elf32ltsmip", "-Ttext=0x80010000", "-e", "_start", "-o", "p.elf", "p.o")
	sh(t, dir, "llvm-objcopy", "-O", "binary", "-j", ".text", "p.elf", "p.bin")
	text, err := os.ReadFile(filepath.Join(dir, "p.bin"))
	if err != nil {
		t.Fatal(err)
	}
	// o tamanho do segmento no PS-X EXE é múltiplo de 2048
	for len(text)%2048 != 0 {
		text = append(text, 0)
	}
	h := make([]byte, headerSize)
	copy(h, "PS-X EXE")
	put := func(off int, v uint32) { binary.LittleEndian.PutUint32(h[off:], v) }
	put(0x10, 0x80010000)
	put(0x18, 0x80010000)
	put(0x1C, uint32(len(text)))
	put(0x30, 0x801FFFF0)
	copy(h[0x4C:], "Sony Computer Entertainment Inc. for Europe area")
	return append(h, text...), filepath.Join(dir, "p.elf")
}

func TestPontaAPonta(t *testing.T) {
	raw, _ := buildExe(t)
	e, err := ParseExe(raw)
	if err != nil {
		t.Fatal(err)
	}
	fs := e.FindFunctions()
	if len(fs) < 3 || fs[0].Addr != 0x80010040 || fs[0].Calls != 2 {
		t.Fatalf("funções: %+v", fs)
	}
	var sawInit bool
	for _, f := range fs {
		sawInit = sawInit || (f.Addr == 0x80010028 && f.Calls == 1)
	}
	if !sawInit {
		t.Errorf("init_gpu não encontrada: %+v", fs)
	}
	send := e.DisasmRange(0x80010040, 64)
	for _, want := range []string{"; GPU_GP0", "jalr $ra,$t4"} {
		if !strings.Contains(send, want) {
			t.Errorf("send sem %q:\n%s", want, send)
		}
	}
	init := e.DisasmRange(0x80010028, 64)
	for _, want := range []string{"; GPU_GP1", "; I_STAT"} {
		if !strings.Contains(init, want) {
			t.Errorf("init_gpu sem %q:\n%s", want, init)
		}
	}
	if ind := e.Indirects(0x80010040, 16); len(ind) != 1 || ind[0] != 0x80010050 {
		t.Errorf("indiretos de send: %x", ind)
	}
	if ind := e.Indirects(0x80010028, 16); len(ind) != 0 {
		t.Errorf("init_gpu não tem salto indireto: %x", ind)
	}
}

var objdumpLine = regexp.MustCompile(`^\s*([0-9a-f]{8}):\s+(?:[0-9a-f]{2} ){4}\s*(\S+)`)

// TestProgramaInteiroContraLLVM compara o mnemônico de cada instrução do programa com o llvm-objdump.
func TestProgramaInteiroContraLLVM(t *testing.T) {
	need(t, "llvm-objdump")
	raw, elf := buildExe(t)
	e, err := ParseExe(raw)
	if err != nil {
		t.Fatal(err)
	}
	out := sh(t, "", "llvm-objdump", "-d", "--triple=mipsel", "--mcpu=mips1", elf)
	compared := 0
	for _, l := range strings.Split(out, "\n") {
		m := objdumpLine.FindStringSubmatch(l)
		if m == nil {
			continue
		}
		var pc uint32
		fmt.Sscanf(m[1], "%x", &pc)
		w, ok := e.Word(pc)
		if !ok {
			t.Fatalf("endereço %08x fora do EXE", pc)
		}
		if ours := strings.Fields(Disasm(w, pc))[0]; ours != m[2] {
			t.Errorf("%08x: nosso=%q llvm=%q", pc, Disasm(w, pc), m[2])
		}
		compared++
	}
	if compared != 24 {
		t.Fatalf("comparou %d instruções, esperava 24", compared)
	}
}
