package orchestrator

import (
	"context"
	"encoding/binary"
	"fmt"
	"os"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"reversa/internal/evidence"
	"reversa/internal/llm"
	"reversa/internal/ps1"
)

func TestMapRespeitaLimiteEOrdem(t *testing.T) {
	var cur, peak atomic.Int32
	items := []int{0, 1, 2, 3, 4, 5, 6, 7}
	out := Map(context.Background(), items, 3, func(_ context.Context, n int) (int, error) {
		c := cur.Add(1)
		for {
			p := peak.Load()
			if c <= p || peak.CompareAndSwap(p, c) {
				break
			}
		}
		time.Sleep(5 * time.Millisecond)
		cur.Add(-1)
		return n * 2, nil
	})
	if peak.Load() > 3 {
		t.Fatalf("pico de %d execuções simultâneas, limite 3", peak.Load())
	}
	for i, r := range out {
		if r.Val != i*2 {
			t.Fatalf("ordem quebrada em %d: %d", i, r.Val)
		}
	}
}

func TestMapCancelamento(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	out := Map(ctx, []int{1, 2, 3}, 1, func(context.Context, int) (int, error) { return 0, nil })
	if out[2].Err == nil {
		t.Fatal("tarefa não iniciada deveria ter erro de cancelamento")
	}
}

type stub struct{ reply string }

func (s stub) Chat(context.Context, []llm.Message, []llm.ToolDef) (llm.Message, error) {
	return llm.Message{Role: "assistant", Content: s.reply}, nil
}

func TestPipelinePS1(t *testing.T) {
	b := make([]byte, 0x800)
	copy(b, "PS-X EXE")
	binary.LittleEndian.PutUint32(b[0x10:], 0x80010000)
	binary.LittleEndian.PutUint32(b[0x18:], 0x80010000)
	code := []uint32{0x0C004004, 0, 0x0100F809, 0, 0x24020001, 0x03E00008, 0} // a função tem um jalr
	binary.LittleEndian.PutUint32(b[0x1C:], uint32(len(code)*4))
	for _, w := range code {
		b = binary.LittleEndian.AppendUint32(b, w)
	}
	exe, err := ps1.ParseExe(b)
	if err != nil {
		t.Fatal(err)
	}
	log := &evidence.Log{}
	p := &PS1{Worker: stub{"retorna 1"}, Synthesizer: stub{"relatório final"}, Evidence: log, Workers: 2, TopN: 4, MaxInsns: 32}
	out, err := p.Run(context.Background(), exe)
	if err != nil || !strings.Contains(out, "relatório final") {
		t.Fatalf("saída %q err %v", out, err)
	}
	tools := map[string]int{}
	for _, r := range log.All() {
		tools[r.Tool]++
	}
	if tools["ps1_indirect"] != 1 {
		t.Fatalf("esperava 1 registro de salto indireto: %v", tools)
	}
	if tools["ps1_header"] != 1 || tools["ps1_disasm"] < 1 || tools["llm_hipotese"] != tools["ps1_disasm"] {
		t.Fatalf("evidências inesperadas: %v", tools)
	}
	for _, r := range log.All() {
		if r.Tool == "llm_hipotese" && (r.Confidence != evidence.Inferred || !strings.Contains(r.Limits, "não verificada")) {
			t.Fatal("hipótese deve ser 'inferred' e trazer aviso de limite")
		}
		if r.Tool == "ps1_header" && r.Confidence != evidence.Observed {
			t.Fatal("cabeçalho deve ser 'observed'")
		}
	}
}

// capture guarda o texto de cada pedido recebido, com segurança para uso concorrente.
type capture struct {
	mu   sync.Mutex
	seen []string
}

func (c *capture) Chat(_ context.Context, msgs []llm.Message, _ []llm.ToolDef) (llm.Message, error) {
	c.mu.Lock()
	c.seen = append(c.seen, msgs[len(msgs)-1].Content)
	c.mu.Unlock()
	return llm.Message{Role: "assistant", Content: "ok"}, nil
}

func TestPromptDoOperarioTemContexto(t *testing.T) {
	raw, err := os.ReadFile("../../testdata/exemplo2.exe")
	if err != nil {
		t.Fatal(err)
	}
	exe, err := ps1.ParseExe(raw)
	if err != nil {
		t.Fatal(err)
	}
	w := &capture{}
	p := &PS1{Worker: w, Synthesizer: stub{"fim"}, Evidence: &evidence.Log{}, Workers: 2, TopN: 20, MaxInsns: 96}
	if _, err := p.Run(context.Background(), exe); err != nil {
		t.Fatal(err)
	}
	var entry, waitVblank string
	for _, s := range w.seen {
		switch {
		case strings.Contains(s, "ponto de entrada do programa"):
			entry = s
		case strings.Contains(s, "; I_STAT") && strings.Contains(s, "andi"):
			waitVblank = s
		}
	}
	if entry == "" || !strings.Contains(entry, "Ela chama: 0x80010058 0x80010074") {
		t.Errorf("prompt da entrada sem papel ou sem callees:\n%s", entry)
	}
	if waitVblank == "" || strings.Contains(waitVblank, "Ela chama") {
		t.Errorf("wait_vblank não chama ninguém e não deve listar callees:\n%s", waitVblank)
	}
	var sawLabel bool
	for _, r := range p.Evidence.All() {
		sawLabel = sawLabel || (r.Tool == "ps1_disasm" && strings.Contains(r.Args, "ponto de entrada"))
	}
	if !sawLabel {
		t.Error("evidência da entrada deveria dizer 'ponto de entrada', não 'chamada 0x'")
	}
}

func TestProgressoPorEstagio(t *testing.T) {
	raw, err := os.ReadFile("../../testdata/exemplo2.exe")
	if err != nil {
		t.Fatal(err)
	}
	exe, err := ps1.ParseExe(raw)
	if err != nil {
		t.Fatal(err)
	}
	var mu sync.Mutex
	var lines []string
	p := &PS1{Worker: stub{"ok"}, Synthesizer: stub{"fim"}, Evidence: &evidence.Log{}, Workers: 2, TopN: 5, MaxInsns: 96,
		Progress: func(f string, a ...any) { mu.Lock(); lines = append(lines, fmt.Sprintf(f, a...)); mu.Unlock() }}
	if _, err := p.Run(context.Background(), exe); err != nil {
		t.Fatal(err)
	}
	all := strings.Join(lines, "\n")
	for _, want := range []string{"estágio 1/3", "estágio 2/3: 5/5", "estágio 3/3"} {
		if !strings.Contains(all, want) {
			t.Errorf("progresso sem %q:\n%s", want, all)
		}
	}
}

// O modelo pode escrever qualquer coisa no resumo geral; as citações e o hardware vêm do programa.
func TestRelatorioTemCitacoesCorretas(t *testing.T) {
	raw, err := os.ReadFile("../../testdata/exemplo2.exe")
	if err != nil {
		t.Fatal(err)
	}
	exe, err := ps1.ParseExe(raw)
	if err != nil {
		t.Fatal(err)
	}
	log := &evidence.Log{}
	p := &PS1{Worker: stub{"faz algo [E99] em 0x4256"}, Synthesizer: stub{"resumo inventado [E77]"}, Evidence: log, Workers: 2, TopN: 20, MaxInsns: 96}
	out, err := p.Run(context.Background(), exe)
	if err != nil {
		t.Fatal(err)
	}
	// seção de cada função: o [E#] de "Desmontagem" tem de ser a evidência ps1_disasm daquele endereço
	secs := strings.Split(out, "\n### ")[1:]
	if len(secs) < 8 {
		t.Fatalf("esperava 8 seções, veio %d:\n%s", len(secs), out)
	}
	for _, sec := range secs {
		addr := sec[:10]
		var want int
		for _, r := range log.All() {
			if r.Tool == "ps1_disasm" && strings.HasPrefix(r.Args, addr) {
				want = r.ID
			}
		}
		if want == 0 || !strings.Contains(sec, fmt.Sprintf("- Desmontagem: [E%d] (derivada)", want)) {
			t.Errorf("citação errada na seção %s (esperava E%d):\n%s", addr, want, sec)
		}
	}
	for _, want := range []string{
		"### 0x80010074 (chamada 2x)", "lê I_STAT (0x1f801070); escreve 0x00000000 em I_STAT (0x1f801070)",
		"escreve valor variável em DMA2_GPU_MADR (0x1f8010a0)", "escreve 0x01000201 em DMA2_GPU_CHCR (0x1f8010a8)", "lê TIMER0_COUNT (0x1f801100)",
		"escreve 0x03000001 em GPU_GP1 (0x1f801814)", "desvio em 0x80010084 volta para 0x80010078 (condicional; espera ativa em I_STAT (0x1f801070): repete enquanto (I_STAT & 0x1) == 0; sai quando (I_STAT & 0x1) != 0)",
		"desvio em 0x80010050 volta para 0x80010040 (incondicional; chama dentro do laço: 0x80010074, 0x800100e8)",
		"Cobertura: 8 de 8 funções",
		"Saltos indiretos sem destino conhecido: 0x80010124", "## Resumo geral (hipótese do modelo, não verificada)", "resumo inventado [E77]",
	} {
		if !strings.Contains(out, want) {
			t.Errorf("relatório sem %q", want)
		}
	}
}

// O worker recebe os fatos de hardware e laços que o programa já verificou.
func TestPromptDoOperarioTemFatosVerificados(t *testing.T) {
	raw, err := os.ReadFile("../../testdata/exemplo2.exe")
	if err != nil {
		t.Fatal(err)
	}
	exe, err := ps1.ParseExe(raw)
	if err != nil {
		t.Fatal(err)
	}
	w := &capture{}
	p := &PS1{Worker: w, Synthesizer: stub{"fim"}, Evidence: &evidence.Log{}, Workers: 2, TopN: 20, MaxInsns: 96}
	if _, err := p.Run(context.Background(), exe); err != nil {
		t.Fatal(err)
	}
	var vblank string
	for _, s := range w.seen {
		if strings.Contains(s, "andi $t1,$t1,0x1") {
			vblank = s
		}
	}
	for _, want := range []string{"Fatos verificados (não contradiga): lê I_STAT", "repete enquanto (I_STAT & 0x1) == 0; sai quando (I_STAT & 0x1) != 0"} {
		if !strings.Contains(vblank, want) {
			t.Errorf("prompt de wait_vblank sem %q:\n%s", want, vblank)
		}
	}
}
