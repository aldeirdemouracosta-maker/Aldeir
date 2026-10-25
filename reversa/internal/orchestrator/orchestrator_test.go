package orchestrator

import (
	"context"
	"encoding/binary"
	"strings"
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
	code := []uint32{0x0C004004, 0, 0x24020001, 0x03E00008, 0}
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
	if err != nil || out != "relatório final" {
		t.Fatalf("saída %q err %v", out, err)
	}
	tools := map[string]int{}
	for _, r := range log.All() {
		tools[r.Tool]++
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
