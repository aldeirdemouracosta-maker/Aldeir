// Package agent roda o laço modelo -> ferramenta -> evidência até o modelo concluir.
package agent

import (
	"context"
	"fmt"

	"reversa/internal/backend"
	"reversa/internal/evidence"
	"reversa/internal/llm"
)

const systemPrompt = `Você é um analista de engenharia reversa. Use as ferramentas para obter fatos; não invente.
Cada afirmação do relatório final deve citar o número da evidência no formato [E#]. Se algo não puder ser
confirmado pelas ferramentas, diga isso explicitamente. Termine com um relatório em português.`

type Agent struct {
	LLM      llm.Chatter
	Tools    []backend.Tool
	Evidence *evidence.Log
	MaxSteps int
}

func (a *Agent) defs() []llm.ToolDef {
	defs := make([]llm.ToolDef, 0, len(a.Tools))
	for _, t := range a.Tools {
		props := map[string]llm.Property{}
		for name, desc := range t.Params {
			props[name] = llm.Property{Type: "string", Description: desc}
		}
		defs = append(defs, llm.ToolDef{Type: "function", Function: llm.FuncDef{
			Name: t.Name, Description: t.Description,
			Parameters: llm.Schema{Type: "object", Properties: props, Required: t.Required},
		}})
	}
	return defs
}

func (a *Agent) find(name string) *backend.Tool {
	for i := range a.Tools {
		if a.Tools[i].Name == name {
			return &a.Tools[i]
		}
	}
	return nil
}

// Run analisa o alvo e devolve o relatório final do modelo.
func (a *Agent) Run(ctx context.Context, goal string) (string, error) {
	msgs := []llm.Message{{Role: "system", Content: systemPrompt}, {Role: "user", Content: goal}}
	for step := 0; step < a.MaxSteps; step++ {
		reply, err := a.LLM.Chat(ctx, msgs, a.defs())
		if err != nil {
			return "", err
		}
		msgs = append(msgs, reply)
		if len(reply.ToolCalls) == 0 {
			return reply.Content, nil
		}
		for _, call := range reply.ToolCalls {
			msgs = append(msgs, llm.Message{Role: "tool", Content: a.exec(ctx, call)})
		}
	}
	return "", fmt.Errorf("limite de %d passos atingido sem relatório final", a.MaxSteps)
}

func (a *Agent) exec(ctx context.Context, call llm.ToolCall) string {
	name := call.Function.Name
	t := a.find(name)
	if t == nil {
		return "erro: ferramenta desconhecida " + name
	}
	args := map[string]string{}
	for k, v := range call.Function.Arguments {
		args[k] = fmt.Sprint(v)
	}
	out, err := t.Run(ctx, args)
	if err != nil {
		out += "\nerro: " + err.Error()
	}
	rec := a.Evidence.Add(name, fmt.Sprint(args), out, t.Limits)
	return fmt.Sprintf("[E%d] %s\nLimites: %s", rec.ID, out, t.Limits)
}
