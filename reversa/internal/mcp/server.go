// Package mcp implementa o mínimo do Model Context Protocol sobre stdio (JSON-RPC 2.0, uma mensagem por linha):
// initialize, ping, tools/list e tools/call.
package mcp

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"sort"
)

// Tool é uma ferramenta exposta ao cliente MCP.
type Tool struct {
	Name        string
	Description string
	Schema      map[string]any // JSON Schema de entrada
	Handler     func(ctx context.Context, args map[string]any) (string, error)
}

type Server struct {
	Name, Version string
	tools         map[string]Tool
}

func NewServer(name, version string, tools []Tool) *Server {
	s := &Server{Name: name, Version: version, tools: map[string]Tool{}}
	for _, t := range tools {
		s.tools[t.Name] = t
	}
	return s
}

type request struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id,omitempty"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params,omitempty"`
}

type rpcError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

type response struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      json.RawMessage `json:"id"`
	Result  any             `json:"result,omitempty"`
	Error   *rpcError       `json:"error,omitempty"`
}

const maxLine = 8 << 20

// Serve lê mensagens de in e escreve respostas em out até o fim da entrada ou do contexto.
func (s *Server) Serve(ctx context.Context, in io.Reader, out io.Writer) error {
	sc := bufio.NewScanner(in)
	sc.Buffer(make([]byte, 64<<10), maxLine)
	enc := json.NewEncoder(out)
	for sc.Scan() {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		line := sc.Bytes()
		if len(line) == 0 {
			continue
		}
		var req request
		if err := json.Unmarshal(line, &req); err != nil {
			if err := enc.Encode(response{JSONRPC: "2.0", ID: json.RawMessage("null"), Error: &rpcError{-32700, "JSON inválido"}}); err != nil {
				return err
			}
			continue
		}
		if len(req.ID) == 0 { // notificação: nunca recebe resposta
			continue
		}
		res, rerr := s.handle(ctx, req)
		resp := response{JSONRPC: "2.0", ID: req.ID, Result: res, Error: rerr}
		if err := enc.Encode(resp); err != nil {
			return err
		}
	}
	return sc.Err()
}

func (s *Server) handle(ctx context.Context, req request) (any, *rpcError) {
	switch req.Method {
	case "initialize":
		var p struct {
			ProtocolVersion string `json:"protocolVersion"`
		}
		_ = json.Unmarshal(req.Params, &p)
		if p.ProtocolVersion == "" {
			p.ProtocolVersion = "2025-06-18"
		}
		return map[string]any{
			"protocolVersion": p.ProtocolVersion,
			"capabilities":    map[string]any{"tools": map[string]any{}},
			"serverInfo":      map[string]any{"name": s.Name, "version": s.Version},
		}, nil
	case "ping":
		return map[string]any{}, nil
	case "tools/list":
		names := make([]string, 0, len(s.tools))
		for n := range s.tools {
			names = append(names, n)
		}
		sort.Strings(names) // ordem estável: o catálogo nunca decide qual operação roda
		list := make([]map[string]any, 0, len(names))
		for _, n := range names {
			t := s.tools[n]
			list = append(list, map[string]any{"name": t.Name, "description": t.Description, "inputSchema": t.Schema})
		}
		return map[string]any{"tools": list}, nil
	case "tools/call":
		var p struct {
			Name      string         `json:"name"`
			Arguments map[string]any `json:"arguments"`
		}
		if err := json.Unmarshal(req.Params, &p); err != nil {
			return nil, &rpcError{-32602, "parâmetros inválidos"}
		}
		t, ok := s.tools[p.Name]
		if !ok {
			return nil, &rpcError{-32602, fmt.Sprintf("ferramenta desconhecida: %s", p.Name)}
		}
		text, err := t.Handler(ctx, p.Arguments)
		if err != nil { // erro da ferramenta vai no resultado, para o modelo poder ler e reagir
			return map[string]any{"isError": true, "content": []map[string]any{{"type": "text", "text": err.Error()}}}, nil
		}
		return map[string]any{"content": []map[string]any{{"type": "text", "text": text}}}, nil
	}
	return nil, &rpcError{-32601, "método não suportado: " + req.Method}
}
