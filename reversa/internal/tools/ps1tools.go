// Package tools monta as ferramentas MCP do reversa sobre ps1, disc e evidence.
package tools

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"path/filepath"
	"strings"

	"reversa/internal/disc"
	"reversa/internal/evidence"
	"reversa/internal/mcp"
	"reversa/internal/orchestrator"
	"reversa/internal/ps1"
	"reversa/internal/target"
)

// Set guarda a raiz permitida e o log de evidências compartilhado entre as chamadas.
type Set struct {
	Root string
	Log  *evidence.Log
}

// resolve só aceita caminhos dentro de Root, mesmo via ".." ou link simbólico.
func (s *Set) resolve(p string) (string, error) {
	if p == "" {
		return "", fmt.Errorf("parâmetro 'path' é obrigatório")
	}
	root, err := filepath.EvalSymlinks(s.Root)
	if err != nil {
		return "", err
	}
	if !filepath.IsAbs(p) {
		p = filepath.Join(root, p)
	}
	real, err := filepath.EvalSymlinks(p)
	if err != nil {
		return "", err
	}
	rel, err := filepath.Rel(root, real)
	if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return "", fmt.Errorf("caminho fora da raiz permitida")
	}
	return real, nil
}

func str(a map[string]any, k string) string { v, _ := a[k].(string); return v }

func num(a map[string]any, k string, def, max int) int {
	if f, ok := a[k].(float64); ok && f >= 1 {
		return min(int(f), max)
	}
	return def
}

func (s *Set) record(c evidence.Confidence, tool string, args map[string]any, out, limits string) string {
	a, _ := json.Marshal(args)
	r := s.Log.AddAs(c, tool, string(a), out, limits)
	return fmt.Sprintf("[E%d] (%s) %s\nLimites: %s", r.ID, c, out, limits)
}

func (s *Set) loadExe(ctx context.Context, a map[string]any) (*ps1.Exe, error) {
	p, err := s.resolve(str(a, "path"))
	if err != nil {
		return nil, err
	}
	raw, _, err := target.LoadPS1(p)
	if err != nil {
		return nil, err
	}
	sum := sha256.Sum256(raw)
	s.Log.Subject = hex.EncodeToString(sum[:])
	return ps1.ParseExe(raw)
}

func pathSchema(extra map[string]any, required ...string) map[string]any {
	props := map[string]any{"path": map[string]any{"type": "string", "description": "executável PS-X EXE ou imagem de disco (.cue/.bin/.iso), dentro da raiz permitida"}}
	for k, v := range extra {
		props[k] = v
	}
	return map[string]any{"type": "object", "properties": props, "required": append([]string{"path"}, required...)}
}

// MCP devolve as ferramentas prontas para o servidor.
func (s *Set) MCP() []mcp.Tool {
	return []mcp.Tool{
		{
			Name: "ps1_header", Description: "Cabeçalho de um PS-X EXE (entrada, carga, gp, sp, região).",
			Schema: pathSchema(nil),
			Handler: func(ctx context.Context, a map[string]any) (string, error) {
				e, err := s.loadExe(ctx, a)
				if err != nil {
					return "", err
				}
				out := fmt.Sprintf("entrada=0x%08x carga=0x%08x gp=0x%08x sp=0x%08x região=%q tamanho=%d", e.PC, e.Load, e.GP, e.SP, e.Region, len(e.Text))
				return s.record(evidence.Observed, "ps1_header", a, out, "Lido do cabeçalho; o conteúdo não é validado."), nil
			},
		},
		{
			Name: "ps1_functions", Description: "Funções candidatas (alvos de jal), da mais chamada para a menos chamada.",
			Schema: pathSchema(map[string]any{"top": map[string]any{"type": "integer", "description": "quantas listar (padrão 30, máximo 500)"}}),
			Handler: func(ctx context.Context, a map[string]any) (string, error) {
				e, err := s.loadExe(ctx, a)
				if err != nil {
					return "", err
				}
				fs := e.FindFunctions()
				fs = fs[:min(len(fs), num(a, "top", 30, 500))]
				var b strings.Builder
				for _, f := range fs {
					fmt.Fprintf(&b, "0x%08x chamadas=%d\n", f.Addr, f.Calls)
				}
				return s.record(evidence.Derived, "ps1_functions", a, b.String(), "Só chamadas diretas (jal); funções chamadas por jalr ou tabelas de salto não aparecem."), nil
			},
		},
		{
			Name: "ps1_disasm", Description: "Desmonta MIPS R3000 a partir de um endereço, anotando registradores de hardware do PS1.",
			Schema: pathSchema(map[string]any{
				"address": map[string]any{"type": "string", "description": "endereço virtual em hexadecimal, por exemplo 0x80010000"},
				"count":   map[string]any{"type": "integer", "description": "instruções (padrão 64, máximo 512)"},
			}, "address"),
			Handler: func(ctx context.Context, a map[string]any) (string, error) {
				e, err := s.loadExe(ctx, a)
				if err != nil {
					return "", err
				}
				var addr uint32
				if _, err := fmt.Sscanf(strings.TrimPrefix(str(a, "address"), "0x"), "%x", &addr); err != nil {
					return "", fmt.Errorf("endereço inválido: %q", str(a, "address"))
				}
				n := num(a, "count", 64, 512)
				out := e.DisasmRange(addr, n)
				if out == "" {
					return "", fmt.Errorf("endereço 0x%08x fora do executável", addr)
				}
				if ind := e.Indirects(addr, n); len(ind) > 0 {
					s.record(evidence.Unknown, "ps1_indirect", a, fmt.Sprintf("%x", ind), "Destino de jr/jalr não é estático.")
					out += fmt.Sprintf("; atenção: %d salto(s) indireto(s) sem destino conhecido\n", len(ind))
				}
				return s.record(evidence.Derived, "ps1_disasm", a, out, "Desmontagem linear; propagação de constantes sem seguir desvios; dados no meio do código aparecem como instruções."), nil
			},
		},
		{
			Name: "ps1_function", Description: "Relatório de uma função só com fatos: tamanho, chamadores, funções chamadas, hardware, laços, strings, stubs e desmontagem anotada.",
			Schema: pathSchema(map[string]any{
				"address": map[string]any{"type": "string", "description": "endereço da função em hexadecimal, por exemplo 0x80026538"},
				"insns":   map[string]any{"type": "integer", "description": "máximo de instruções (padrão 256, máximo 1024)"},
			}, "address"),
			Handler: func(ctx context.Context, a map[string]any) (string, error) {
				e, err := s.loadExe(ctx, a)
				if err != nil {
					return "", err
				}
				var addr uint32
				if _, err := fmt.Sscanf(strings.TrimPrefix(strings.ToLower(str(a, "address")), "0x"), "%x", &addr); err != nil {
					return "", fmt.Errorf("endereço inválido: %q", str(a, "address"))
				}
				out, err := orchestrator.FuncReport(e, addr, num(a, "insns", 256, 1024))
				if err != nil {
					return "", err
				}
				return s.record(evidence.Derived, "ps1_function", a, out, "Fatos derivados; fim de função, chamadores e condições de laço são heurísticas."), nil
			},
		},
		{
			Name: "ps1_names", Description: "Funções com evidência de nome ou padrão: stubs de BIOS/syscall, instaladores de callback e strings de depuração parecidas com identificadores.",
			Schema: pathSchema(map[string]any{"insns": map[string]any{"type": "integer", "description": "máximo de instruções examinadas por função (padrão 256)"}}),
			Handler: func(ctx context.Context, a map[string]any) (string, error) {
				e, err := s.loadExe(ctx, a)
				if err != nil {
					return "", err
				}
				out := orchestrator.NamesReport(e, num(a, "insns", 256, 1024))
				return s.record(evidence.Derived, "ps1_names", a, out, "Pistas heurísticas; o executável não tem símbolos, os nomes não são confirmados."), nil
			},
		},
		{
			Name: "ps1_xref", Description: "Quem lê, escreve ou monta um endereço (ou intervalo de bytes), por função; mostra o valor escrito quando constante e acessos a tabelas com índice variável.",
			Schema: pathSchema(map[string]any{
				"address": map[string]any{"type": "string", "description": "endereço em hexadecimal, por exemplo 0x8002d6d8"},
				"bytes":   map[string]any{"type": "integer", "description": "tamanho do intervalo (padrão 1; use o tamanho de uma tabela)"},
			}, "address"),
			Handler: func(ctx context.Context, a map[string]any) (string, error) {
				e, err := s.loadExe(ctx, a)
				if err != nil {
					return "", err
				}
				var addr uint32
				if _, err := fmt.Sscanf(strings.TrimPrefix(strings.ToLower(str(a, "address")), "0x"), "%x", &addr); err != nil {
					return "", fmt.Errorf("endereço inválido: %q", str(a, "address"))
				}
				out := orchestrator.XrefReport(e, addr, num(a, "bytes", 1, 4096), 200)
				return s.record(evidence.Derived, "ps1_xref", a, out, "Só acessos com endereço constante ou tabela com base constante; ponteiros calculados de outro jeito não aparecem."), nil
			},
		},
		{
			Name: "ps1_mem", Description: "Bytes da imagem do executável a partir de um endereço (valores iniciais), com interpretação de palavras que parecem endereços.",
			Schema: pathSchema(map[string]any{
				"address": map[string]any{"type": "string", "description": "endereço em hexadecimal, por exemplo 0x8002d640"},
				"bytes":   map[string]any{"type": "integer", "description": "quantos bytes (padrão 64, máximo 1024)"},
			}, "address"),
			Handler: func(ctx context.Context, a map[string]any) (string, error) {
				e, err := s.loadExe(ctx, a)
				if err != nil {
					return "", err
				}
				var addr uint32
				if _, err := fmt.Sscanf(strings.TrimPrefix(strings.ToLower(str(a, "address")), "0x"), "%x", &addr); err != nil {
					return "", fmt.Errorf("endereço inválido: %q", str(a, "address"))
				}
				out, err := orchestrator.MemReport(e, addr, num(a, "bytes", 64, 1024))
				if err != nil {
					return "", err
				}
				return s.record(evidence.Observed, "ps1_mem", a, out, "Valores iniciais do arquivo; a memória em execução pode ter mudado e .bss não está no arquivo."), nil
			},
		},
		{
			Name: "disc_info", Description: "Volume, executável de boot e arquivos da raiz de uma imagem de disco do PS1.",
			Schema: pathSchema(nil),
			Handler: func(ctx context.Context, a map[string]any) (string, error) {
				p, err := s.resolve(str(a, "path"))
				if err != nil {
					return "", err
				}
				img, err := disc.Open(p)
				if err != nil {
					return "", err
				}
				defer img.Close()
				var b strings.Builder
				fmt.Fprintf(&b, "volume: %s\n", img.VolumeID)
				if boot, err := img.BootPath(); err == nil {
					fmt.Fprintf(&b, "boot: %s\n", boot)
				}
				files, err := img.List("/")
				if err != nil {
					return "", err
				}
				for _, f := range files {
					fmt.Fprintf(&b, "%10d  %s\n", f.Size, f.Name)
				}
				return s.record(evidence.Observed, "disc_info", a, b.String(), "Somente a raiz do ISO 9660; nomes Joliet e extensões Rock Ridge não são lidos."), nil
			},
		},
		{
			Name: "evidence_list", Description: "Todas as evidências registradas nesta sessão, em JSON.",
			Schema: map[string]any{"type": "object", "properties": map[string]any{}},
			Handler: func(ctx context.Context, a map[string]any) (string, error) {
				b, err := json.MarshalIndent(s.Log.All(), "", "  ")
				return string(b), err
			},
		},
	}
}
