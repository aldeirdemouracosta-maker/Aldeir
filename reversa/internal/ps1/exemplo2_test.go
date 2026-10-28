package ps1

import (
	"bytes"
	"os"
	"strings"
	"testing"
)

// Endereços conferidos com `llvm-objdump -t` no ELF montado a partir de testdata/exemplo2.s.
const (
	e2Start      = 0x80010000
	e2MainLoop   = 0x80010040
	e2GPUReset   = 0x80010058
	e2WaitVblank = 0x80010074
	e2Checksum   = 0x80010098
	e2DMA        = 0x800100c0
	e2ReadTimer  = 0x800100e8
	e2CDCommand  = 0x800100f8
	e2Dispatch   = 0x8001010c
	e2HandlerA   = 0x8001012c
	e2HandlerB   = 0x8001014c
)

func loadExemplo2(t *testing.T) *Exe {
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

func TestExemplo2Funcoes(t *testing.T) {
	e := loadExemplo2(t)
	got := map[uint32]int{}
	for _, f := range e.FindFunctions() {
		got[f.Addr] = f.Calls
	}
	want := map[uint32]int{
		e2Start: 0, e2GPUReset: 1, e2WaitVblank: 2, e2Checksum: 1, e2DMA: 1, e2Dispatch: 1, e2ReadTimer: 2, e2CDCommand: 1,
	}
	for a, c := range want {
		if g, ok := got[a]; !ok || g != c {
			t.Errorf("função %08x: chamadas=%d achada=%v, esperado %d", a, g, ok, c)
		}
	}
	// Limitação documentada: só são alcançados por tabela de salto, nunca por jal.
	for _, a := range []uint32{e2HandlerA, e2HandlerB} {
		if _, ok := got[a]; ok {
			t.Errorf("handler %08x não deveria ser achado por jal", a)
		}
	}
}

func TestExemplo2FimDeFuncaoEHardware(t *testing.T) {
	e := loadExemplo2(t)
	cases := []struct {
		name     string
		addr     uint32
		has, not []string
		lastLine string
		hwCount  map[string]int
	}{
		{"gpu_reset", e2GPUReset, nil, []string{"I_STAT"}, "nop", map[string]int{"GPU_GP1": 2}},
		{"wait_vblank", e2WaitVblank, []string{"andi"}, []string{"lbu", "GPU_GP1"}, "nop", map[string]int{"I_STAT": 2}},
		{"checksum", e2Checksum, []string{"lbu", "addu"}, []string{"; "}, "nop", nil},
		{"dma_to_gpu", e2DMA, nil, []string{"I_STAT"}, "nop", map[string]int{"DMA2_GPU_MADR": 1, "DMA2_GPU_BCR": 1, "DMA2_GPU_CHCR": 1}},
		{"read_timer", e2ReadTimer, nil, nil, "nop", map[string]int{"TIMER0_COUNT": 1}},
		{"cd_command", e2CDCommand, nil, nil, "nop", map[string]int{"CDROM_INDEX": 1, "CDROM_REG1": 1}},
	}
	for _, c := range cases {
		out := e.DisasmRange(c.addr, 96)
		lines := strings.Split(strings.TrimSpace(out), "\n")
		for _, h := range c.has {
			if !strings.Contains(out, h) {
				t.Errorf("%s: faltou %q\n%s", c.name, h, out)
			}
		}
		for _, n := range c.not {
			if strings.Contains(out, n) {
				t.Errorf("%s: não deveria conter %q (vazou para outra função?)\n%s", c.name, n, out)
			}
		}
		if !strings.HasSuffix(lines[len(lines)-1], c.lastLine) || !strings.Contains(lines[len(lines)-2], "jr $ra") {
			t.Errorf("%s: deveria terminar em 'jr $ra' + delay slot:\n%s", c.name, out)
		}
		for hw, n := range c.hwCount {
			if got := strings.Count(out, "; "+hw); got != n {
				t.Errorf("%s: %s aparece %dx, esperado %dx\n%s", c.name, hw, got, n, out)
			}
		}
	}
}

func TestExemplo2SaltoIndiretoPorTabela(t *testing.T) {
	e := loadExemplo2(t)
	out := e.DisasmRange(e2Dispatch, 96)
	if strings.Contains(out, "sw $ra") {
		t.Errorf("dispatch invadiu o handler seguinte:\n%s", out)
	}
	lines := strings.Split(strings.TrimSpace(out), "\n")
	if !strings.Contains(lines[len(lines)-2], "jr $t1") {
		t.Errorf("dispatch deveria terminar em 'jr $t1' + delay slot:\n%s", out)
	}
	if ind := e.Indirects(e2Dispatch, 96); len(ind) != 1 || ind[0] != e2Dispatch+6*4 {
		t.Errorf("indiretos de dispatch: %x", ind)
	}
	for _, a := range []uint32{e2GPUReset, e2WaitVblank, e2Checksum, e2DMA, e2ReadTimer} {
		if ind := e.Indirects(uint32(a), 96); len(ind) != 0 {
			t.Errorf("%08x não tem salto indireto: %x", a, ind)
		}
	}
}

func TestExemplo2Callees(t *testing.T) {
	e := loadExemplo2(t)
	got := e.Callees(e2Start, 96)
	want := []uint32{e2GPUReset, e2WaitVblank, e2Checksum, e2DMA, e2Dispatch, e2ReadTimer}
	if len(got) != len(want) {
		t.Fatalf("callees de _start: %x", got)
	}
	for i := range want {
		if got[i] != want[i] {
			t.Errorf("callee %d: %08x, esperado %08x", i, got[i], want[i])
		}
	}
	// o laço principal de _start termina em 'j main_loop': a função não pode invadir gpu_reset
	if out := e.DisasmRange(e2Start, 96); strings.Contains(out, "lw $t1,6228") || strings.Contains(out, "; GPU_GP1") {
		t.Errorf("_start invadiu a função seguinte:\n%s", out)
	}
}

// O exe commitado precisa corresponder ao fonte; e a desmontagem inteira concorda com o llvm-objdump.
func TestExemplo2ContraFonteELLVM(t *testing.T) {
	need(t, "clang", "ld.lld", "llvm-objcopy", "llvm-objdump")
	src, err := os.ReadFile("../../testdata/exemplo2.s")
	if err != nil {
		t.Fatal(err)
	}
	raw, elf := buildFrom(t, string(src))
	built, err := ParseExe(raw)
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(built.Text[:364], loadExemplo2(t).Text[:364]) {
		t.Error("testdata/exemplo2.exe está desatualizado em relação a exemplo2.s")
	}
	if n := compareAll(t, raw, elf); n != 91 {
		t.Fatalf("comparou %d instruções, esperava 91", n)
	}
}

func TestExemplo2ValoresEscritos(t *testing.T) {
	e := loadExemplo2(t)
	// gpu_reset: escreve 0 e depois 0x03000001 em GP1 (lui 0x0300; ori 0x1)
	gp := e.HWAccesses(e2GPUReset, 96)
	if len(gp) != 2 || !gp[0].Store || !gp[0].Known || gp[0].Value != 0 || !gp[1].Known || gp[1].Value != 0x03000001 || gp[1].Width != 4 {
		t.Errorf("gpu_reset: %+v", gp)
	}
	// dma_to_gpu: MADR e BCR dependem dos argumentos; CHCR é constante 0x01000201
	dma := e.HWAccesses(e2DMA, 96)
	if len(dma) != 3 || dma[0].Known || dma[1].Known || !dma[2].Known || dma[2].Value != 0x01000201 || dma[2].Name != "DMA2_GPU_CHCR" {
		t.Errorf("dma: %+v", dma)
	}
	// cd_command: índice recebe o byte 0; o comando vem de $a0 (desconhecido)
	cd := e.HWAccesses(e2CDCommand, 96)
	if len(cd) != 2 || !cd[0].Known || cd[0].Value != 0 || cd[0].Width != 1 || cd[1].Known {
		t.Errorf("cd_command: %+v", cd)
	}
	// read_timer só lê
	if rt := e.HWAccesses(e2ReadTimer, 96); len(rt) != 1 || rt[0].Store || rt[0].Name != "TIMER0_COUNT" {
		t.Errorf("read_timer: %+v", rt)
	}
}

// Regressão: o modelo inverteu a lógica de wait_vblank. O laço de espera precisa ser um fato do programa.
func TestExemplo2LacosEEsperaAtiva(t *testing.T) {
	e := loadExemplo2(t)
	loops := e.Loops(e2WaitVblank, 96)
	if len(loops) != 1 || loops[0].PC != 0x80010084 || loops[0].Target != 0x80010078 || !loops[0].Polling() ||
		loops[0].Reads[0].Name != "I_STAT" {
		t.Fatalf("wait_vblank: %+v", loops)
	}
	cs := e.Loops(e2Checksum, 96)
	if len(cs) != 1 || cs[0].PC != 0x800100b0 || cs[0].Target != 0x8001009c || !cs[0].Unconditional || cs[0].Polling() {
		t.Errorf("checksum deveria ter um laço incondicional sem polling: %+v", cs)
	}
	st := e.Loops(e2Start, 96)
	if len(st) != 1 || st[0].PC != 0x80010050 || st[0].Target != e2MainLoop || !st[0].Unconditional {
		t.Errorf("_start: laço principal 'j main_loop': %+v", st)
	}
	for _, a := range []uint32{e2GPUReset, e2DMA, e2ReadTimer, e2CDCommand} {
		if l := e.Loops(a, 96); len(l) != 0 {
			t.Errorf("%08x não tem laço: %+v", a, l)
		}
	}
}
