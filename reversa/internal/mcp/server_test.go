package mcp

import (
	"bytes"
	"context"
	"encoding/json"
	"strings"
	"testing"
)

func run(t *testing.T, lines ...string) []map[string]any {
	srv := NewServer("t", "0", []Tool{{
		Name: "eco", Description: "d", Schema: map[string]any{"type": "object"},
		Handler: func(_ context.Context, a map[string]any) (string, error) {
			if a["falha"] == true {
				return "", context.DeadlineExceeded
			}
			return "oi " + a["x"].(string), nil
		},
	}})
	var out bytes.Buffer
	if err := srv.Serve(context.Background(), strings.NewReader(strings.Join(lines, "\n")+"\n"), &out); err != nil {
		t.Fatal(err)
	}
	var res []map[string]any
	for _, l := range strings.Split(strings.TrimSpace(out.String()), "\n") {
		if l == "" {
			continue
		}
		var m map[string]any
		if err := json.Unmarshal([]byte(l), &m); err != nil {
			t.Fatalf("resposta inválida %q", l)
		}
		res = append(res, m)
	}
	return res
}

func TestProtocolo(t *testing.T) {
	res := run(t,
		`{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26"}}`,
		`{"jsonrpc":"2.0","method":"notifications/initialized"}`,
		`{"jsonrpc":"2.0","id":2,"method":"tools/list"}`,
		`{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"eco","arguments":{"x":"mundo"}}}`,
		`{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"eco","arguments":{"falha":true}}}`,
		`{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"nada"}}`,
		`{"jsonrpc":"2.0","id":6,"method":"inexistente"}`,
		`lixo`,
	)
	if len(res) != 7 { // a notificação não responde
		t.Fatalf("%d respostas, esperava 7: %v", len(res), res)
	}
	if res[0]["result"].(map[string]any)["protocolVersion"] != "2025-03-26" {
		t.Error("deveria ecoar a versão do cliente")
	}
	if tl := res[1]["result"].(map[string]any)["tools"].([]any); len(tl) != 1 {
		t.Error("tools/list")
	}
	if c := res[2]["result"].(map[string]any)["content"].([]any)[0].(map[string]any)["text"]; c != "oi mundo" {
		t.Errorf("tools/call: %v", c)
	}
	if res[3]["result"].(map[string]any)["isError"] != true {
		t.Error("erro da ferramenta deve vir como isError")
	}
	if res[4]["error"].(map[string]any)["code"].(float64) != -32602 {
		t.Error("ferramenta desconhecida")
	}
	if res[5]["error"].(map[string]any)["code"].(float64) != -32601 {
		t.Error("método desconhecido")
	}
	if res[6]["error"].(map[string]any)["code"].(float64) != -32700 {
		t.Error("JSON inválido")
	}
}
