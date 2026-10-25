package agent

import (
	"context"
	"strings"
	"testing"

	"reversa/internal/backend"
	"reversa/internal/evidence"
	"reversa/internal/llm"
)

// fakeLLM chama uma ferramenta no primeiro passo e conclui no segundo.
type fakeLLM struct{ calls int }

func (f *fakeLLM) Chat(_ context.Context, msgs []llm.Message, _ []llm.ToolDef) (llm.Message, error) {
	f.calls++
	if f.calls == 1 {
		var c llm.ToolCall
		c.Function.Name = "echo"
		c.Function.Arguments = map[string]any{"x": "oi"}
		return llm.Message{Role: "assistant", ToolCalls: []llm.ToolCall{c}}, nil
	}
	last := msgs[len(msgs)-1].Content
	return llm.Message{Role: "assistant", Content: "relatório com " + strings.SplitN(last, " ", 2)[0]}, nil
}

func TestAgentRegistraEvidencia(t *testing.T) {
	log := &evidence.Log{}
	a := &Agent{
		LLM: &fakeLLM{}, Evidence: log, MaxSteps: 4,
		Tools: []backend.Tool{{Name: "echo", Limits: "nenhum", Run: func(_ context.Context, a map[string]string) (string, error) {
			return a["x"], nil
		}}},
	}
	out, err := a.Run(context.Background(), "analise")
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out, "[E1]") {
		t.Fatalf("relatório sem referência à evidência: %q", out)
	}
	if n := len(log.All()); n != 1 {
		t.Fatalf("esperava 1 evidência, veio %d", n)
	}
}

func TestAgentLimiteDePassos(t *testing.T) {
	loop := &Agent{LLM: loopLLM{}, Evidence: &evidence.Log{}, MaxSteps: 2,
		Tools: []backend.Tool{{Name: "echo", Run: func(context.Context, map[string]string) (string, error) { return "", nil }}}}
	if _, err := loop.Run(context.Background(), "x"); err == nil {
		t.Fatal("esperava erro de limite de passos")
	}
}

type loopLLM struct{}

func (loopLLM) Chat(context.Context, []llm.Message, []llm.ToolDef) (llm.Message, error) {
	var c llm.ToolCall
	c.Function.Name = "echo"
	return llm.Message{Role: "assistant", ToolCalls: []llm.ToolCall{c}}, nil
}
