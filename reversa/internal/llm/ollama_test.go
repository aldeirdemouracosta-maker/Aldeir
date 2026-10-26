package llm

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

// Servidor falso no formato documentado da API do Ollama (/api/chat, stream=false).
func TestOllamaFormatoDaAPI(t *testing.T) {
	var got map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/chat" || r.Method != http.MethodPost {
			t.Errorf("rota inesperada: %s %s", r.Method, r.URL.Path)
		}
		_ = json.NewDecoder(r.Body).Decode(&got)
		_, _ = w.Write([]byte(`{"model":"m","message":{"role":"assistant","content":"","tool_calls":[{"function":{"name":"ps1_header","arguments":{"path":"a.exe"}}}]},"done":true}`))
	}))
	defer srv.Close()
	o := NewOllama("m")
	o.BaseURL = srv.URL
	o.Seed = 7
	msgs := []Message{{Role: "user", Content: "oi"}, {Role: "tool", ToolName: "ps1_header", Content: "x"}}
	tools := []ToolDef{{Type: "function", Function: FuncDef{Name: "ps1_header", Parameters: Schema{Type: "object"}}}}
	reply, err := o.Chat(context.Background(), msgs, tools)
	if err != nil {
		t.Fatal(err)
	}
	if got["stream"] != false || got["model"] != "m" {
		t.Errorf("requisição: %v", got)
	}
	opts := got["options"].(map[string]any)
	if opts["temperature"] != float64(0) || opts["seed"] != float64(7) {
		t.Errorf("amostragem não determinística: %v", opts)
	}
	if m := got["messages"].([]any)[1].(map[string]any); m["tool_name"] != "ps1_header" {
		t.Errorf("mensagem de ferramenta sem tool_name: %v", m)
	}
	if len(reply.ToolCalls) != 1 || reply.ToolCalls[0].Function.Arguments["path"] != "a.exe" {
		t.Errorf("tool_calls: %+v", reply.ToolCalls)
	}
}

func TestOllamaErroHTTP(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		http.Error(w, `{"error":"model not found"}`, http.StatusNotFound)
	}))
	defer srv.Close()
	o := NewOllama("m")
	o.BaseURL = srv.URL
	if _, err := o.Chat(context.Background(), nil, nil); err == nil {
		t.Fatal("esperava erro para 404")
	}
}

func TestOllamaSemFerramentasOmiteCampo(t *testing.T) {
	var got map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewDecoder(r.Body).Decode(&got)
		_, _ = w.Write([]byte(`{"message":{"role":"assistant","content":"ok"},"done":true}`))
	}))
	defer srv.Close()
	o := NewOllama("m")
	o.BaseURL = srv.URL
	if _, err := o.Chat(context.Background(), []Message{{Role: "user", Content: "x"}}, nil); err != nil {
		t.Fatal(err)
	}
	if _, ok := got["tools"]; ok {
		t.Errorf("campo tools deveria ser omitido: %v", got["tools"])
	}
}
