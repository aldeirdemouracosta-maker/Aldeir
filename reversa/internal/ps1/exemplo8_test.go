package ps1

import (
	"os"
	"testing"
)

// Endereços conferidos com `llvm-objdump -t` no ELF montado a partir de testdata/exemplo8.s.
const (
	e8SwFn    = 0x80010018
	e8SwC0    = 0x8001003c
	e8SwC1    = 0x80010048
	e8SwC2    = 0x80010054
	e8Bounded = 0x8001006c
	e8SwTbl   = 0x80010090
	e8JrPC    = 0x80010034
)

func loadExemplo8(t *testing.T) *Exe {
	raw, err := os.ReadFile("../../testdata/exemplo8.exe")
	if err != nil {
		t.Fatal(err)
	}
	e, err := ParseExe(raw)
	if err != nil {
		t.Fatal(err)
	}
	return e
}

func TestExemplo8TabelaDeSalto(t *testing.T) {
	e := loadExemplo8(t)
	jts := e.JumpTables(e8SwFn, 96)
	if len(jts) != 1 || jts[0].PC != e8JrPC || jts[0].Base != e8SwTbl {
		t.Fatalf("tabelas de salto: %+v", jts)
	}
	want := []uint32{e8SwC0, e8SwC1, e8SwC2}
	if got := jts[0].Targets; len(got) != 3 || got[0] != want[0] || got[1] != want[1] || got[2] != want[2] {
		t.Errorf("destinos: %x, esperado %x", got, want)
	}
	// o jr da tabela também aparece como salto indireto bruto; o jr $ra não
	if ind := e.Indirects(e8SwFn, 96); len(ind) != 1 || ind[0] != e8JrPC {
		t.Errorf("indiretos: %x", ind)
	}
	// sem tabela: nenhuma função dos outros exemplos tem switch por tabela
	for _, f := range []struct {
		e *Exe
		a uint32
	}{{loadExemplo2(t), e2Dispatch}, {loadExemplo2(t), e2Start}, {loadExemplo7(t), e7Lookup}} {
		if got := f.e.JumpTables(f.a, 96); len(got) != 0 {
			t.Errorf("%08x não tem jr por tabela: %+v", f.a, got)
		}
	}
	// a função inteira (com os casos) cabe no fim de função calculado, porque há desvio para frente pendente
	if n := e.FuncLen(e8SwFn, 96); n != 21 {
		t.Errorf("sw_fn deveria ter 21 instruções (inclui os casos), veio %d", n)
	}
}

// Regressão do jogo real: ler hardware dentro de um laço que termina por contador não é espera ativa.
func TestExemplo8LacoLimitadoNaoEhEsperaAtiva(t *testing.T) {
	e := loadExemplo8(t)
	loops := e.Loops(e8Bounded, 96)
	if len(loops) != 1 || !loops[0].ReadsHardware() || loops[0].Reads[0].Name != "CDROM_INDEX" {
		t.Fatalf("laço limitado: %+v", loops)
	}
	if loops[0].Polling() || loops[0].While != "" {
		t.Errorf("a saída é por contador, não pelo hardware: Polling=%v While=%q", loops[0].Polling(), loops[0].While)
	}
	// o laço de espera de VBlank continua sendo espera ativa comprovada
	if l := loadExemplo2(t).Loops(e2WaitVblank, 96); len(l) != 1 || !l[0].Polling() {
		t.Errorf("wait_vblank deve continuar como espera ativa: %+v", l)
	}
}

func TestExemplo8ContraLLVM(t *testing.T) {
	need(t, "clang", "ld.lld", "llvm-objcopy", "llvm-objdump")
	src, err := os.ReadFile("../../testdata/exemplo8.s")
	if err != nil {
		t.Fatal(err)
	}
	raw, elf := buildFrom(t, string(src))
	built, err := ParseExe(raw)
	if err != nil {
		t.Fatal(err)
	}
	if string(built.Text[:156]) != string(loadExemplo8(t).Text[:156]) {
		t.Error("testdata/exemplo8.exe está desatualizado em relação a exemplo8.s")
	}
	if n := compareAll(t, raw, elf); n < 35 {
		t.Fatalf("comparou só %d instruções", n)
	}
}
