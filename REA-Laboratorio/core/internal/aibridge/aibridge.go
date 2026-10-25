// Package aibridge detecta e usa motores de IA: Ollama, llama.cpp (llama-server), LM Studio e
// qualquer servidor compatível com a API OpenAI. Nenhum modelo é necessário para o sistema iniciar.
package aibridge

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"

	"rea-lab/internal/guardian"
	"rea-lab/internal/tools"
)

type Engine struct {
	Nome string `json:"nome"`
	Tipo string `json:"tipo"` // "ollama" | "openai"
	URL  string `json:"url"`
}

type Status struct {
	Engine
	Presente bool     `json:"presente"`
	Remoto   bool     `json:"remoto"`
	Detalhe  string   `json:"detalhe"`
	Modelos  []string `json:"modelos,omitempty"`
}

func DefaultEngines() []Engine {
	return []Engine{
		{"Ollama", "ollama", "http://127.0.0.1:11434"},
		{"llama.cpp (llama-server)", "openai", "http://127.0.0.1:8080"},
		{"LM Studio", "openai", "http://127.0.0.1:1234"},
	}
}

func isRemote(rawURL string) bool {
	h := strings.TrimPrefix(strings.TrimPrefix(rawURL, "http://"), "https://")
	h = strings.SplitN(h, "/", 2)[0]
	if i := strings.LastIndex(h, ":"); i > 0 && !strings.Contains(h[i:], "]") {
		h = h[:i]
	}
	return !guardian.IsLoopback(strings.Trim(h, "[]"))
}

// Probe consulta o motor. Para motores remotos exige autorização (Guardian) antes de enviar qualquer requisição.
func Probe(ctx context.Context, c *http.Client, pol guardian.Policy, e Engine, autorizado bool) Status {
	st := Status{Engine: e, Remoto: isRemote(e.URL)}
	if err := pol.CheckNetwork(e.URL, autorizado); err != nil {
		st.Detalhe = err.Error()
		return st
	}
	path := "/v1/models"
	if e.Tipo == "ollama" {
		path = "/api/tags"
	}
	body, code, err := get(ctx, c, strings.TrimRight(e.URL, "/")+path)
	if err != nil {
		st.Detalhe = "sem resposta em " + e.URL
		return st
	}
	if code != 200 {
		st.Detalhe = fmt.Sprintf("HTTP %d", code)
		return st
	}
	var v struct {
		Data []struct {
			ID string `json:"id"`
		} `json:"data"`
		Models []struct {
			Name string `json:"name"`
		} `json:"models"`
	}
	if json.Unmarshal(body, &v) != nil {
		st.Detalhe = "resposta inesperada (não é a API esperada)"
		return st
	}
	for _, m := range v.Data {
		st.Modelos = append(st.Modelos, m.ID)
	}
	for _, m := range v.Models {
		st.Modelos = append(st.Modelos, m.Name)
	}
	st.Presente = true
	st.Detalhe = fmt.Sprintf("%d modelo(s) disponível(is)", len(st.Modelos))
	return st
}

func get(ctx context.Context, c *http.Client, u string) ([]byte, int, error) {
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	resp, err := c.Do(req)
	if err != nil {
		return nil, 0, err
	}
	defer resp.Body.Close()
	b, _ := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
	return b, resp.StatusCode, nil
}

// Aceleradores informa o que foi realmente encontrado; CPU é sempre possível.
func Aceleradores(look tools.LookPath) []string {
	out := []string{"cpu"}
	if _, err := look("vulkaninfo"); err == nil {
		out = append(out, "vulkan (vulkaninfo presente; suporte efetivo não verificado)")
	}
	if _, err := look("nvidia-smi"); err == nil {
		out = append(out, "cuda (nvidia-smi presente; suporte efetivo não verificado)")
	}
	return out
}

type Msg struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// Erro classifica falhas sem inventar causas.
type Erro struct{ Tipo, Detalhe string }

func (e *Erro) Error() string { return e.Tipo + ": " + e.Detalhe }

func classifica(code int, body string) string {
	b := strings.ToLower(body)
	switch {
	case code == 429:
		return "limite"
	case (code == 401 || code == 403) && (strings.Contains(b, "policy") || strings.Contains(b, "content_filter")):
		return "politica"
	case code == 401 || code == 403:
		return "autenticacao"
	case code == 408 || code >= 500:
		return "temporario"
	}
	return "desconhecido"
}

// Complete envia uma conversa ao motor. Motor remoto sem autorização é bloqueado pelo Guardian.
func Complete(ctx context.Context, c *http.Client, pol guardian.Policy, e Engine, autorizado bool, apiKey, model string, msgs []Msg) (string, error) {
	if err := pol.CheckNetwork(e.URL, autorizado); err != nil {
		return "", &Erro{"politica", err.Error()}
	}
	path := "/v1/chat/completions"
	payload := map[string]any{"model": model, "messages": msgs}
	if e.Tipo == "ollama" {
		path = "/api/chat"
		payload["stream"] = false
	}
	b, _ := json.Marshal(payload)
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, strings.TrimRight(e.URL, "/")+path, bytes.NewReader(b))
	req.Header.Set("Content-Type", "application/json")
	if apiKey != "" {
		req.Header.Set("Authorization", "Bearer "+apiKey)
	}
	resp, err := c.Do(req)
	if err != nil {
		return "", &Erro{"rede", "falha de conexão"}
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 8<<20))
	if resp.StatusCode != 200 {
		return "", &Erro{classifica(resp.StatusCode, string(body)), fmt.Sprintf("HTTP %d", resp.StatusCode)}
	}
	var v struct {
		Choices []struct {
			Message Msg `json:"message"`
		} `json:"choices"`
		Message Msg `json:"message"`
	}
	if json.Unmarshal(body, &v) != nil {
		return "", &Erro{"desconhecido", "resposta inesperada"}
	}
	if len(v.Choices) > 0 {
		return v.Choices[0].Message.Content, nil
	}
	if v.Message.Content != "" {
		return v.Message.Content, nil
	}
	return "", &Erro{"desconhecido", "resposta sem conteúdo"}
}
