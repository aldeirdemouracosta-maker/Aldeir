// Package llm fala com um modelo local via API do Ollama (/api/chat com tool calling).
package llm

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

type Message struct {
	Role      string     `json:"role"`
	Content   string     `json:"content"`
	ToolCalls []ToolCall `json:"tool_calls,omitempty"`
}

type ToolCall struct {
	Function struct {
		Name      string         `json:"name"`
		Arguments map[string]any `json:"arguments"`
	} `json:"function"`
}

type ToolDef struct {
	Type     string  `json:"type"`
	Function FuncDef `json:"function"`
}

type FuncDef struct {
	Name        string `json:"name"`
	Description string `json:"description"`
	Parameters  Schema `json:"parameters"`
}

type Schema struct {
	Type       string              `json:"type"`
	Properties map[string]Property `json:"properties"`
	Required   []string            `json:"required,omitempty"`
}

type Property struct {
	Type        string `json:"type"`
	Description string `json:"description"`
}

// Chatter é a interface que o agente usa; permite trocar o modelo ou simular nos testes.
type Chatter interface {
	Chat(ctx context.Context, msgs []Message, tools []ToolDef) (Message, error)
}

type Ollama struct {
	BaseURL string // padrão http://127.0.0.1:11434
	Model   string
	Client  *http.Client
}

func NewOllama(model string) *Ollama {
	return &Ollama{BaseURL: "http://127.0.0.1:11434", Model: model, Client: &http.Client{Timeout: 10 * time.Minute}}
}

func (o *Ollama) Chat(ctx context.Context, msgs []Message, tools []ToolDef) (Message, error) {
	body, _ := json.Marshal(map[string]any{"model": o.Model, "messages": msgs, "tools": tools, "stream": false})
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, o.BaseURL+"/api/chat", bytes.NewReader(body))
	if err != nil {
		return Message{}, err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := o.Client.Do(req)
	if err != nil {
		return Message{}, fmt.Errorf("ollama indisponível em %s: %w", o.BaseURL, err)
	}
	defer resp.Body.Close()
	raw, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != http.StatusOK {
		return Message{}, fmt.Errorf("ollama: %s: %s", resp.Status, raw)
	}
	var out struct {
		Message Message `json:"message"`
	}
	if err := json.Unmarshal(raw, &out); err != nil {
		return Message{}, err
	}
	return out.Message, nil
}
