// Package evidence calcula SHA-256 e monta relatórios com proveniência.
package evidence

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"time"
)

const Versao = "0.1.0"

type Entrada struct {
	Caminho string `json:"caminho"`
	SHA256  string `json:"sha256"`
	Tamanho int64  `json:"tamanho"`
	Formato string `json:"formato"`
}

type Passo struct {
	Ferramenta  string    `json:"ferramenta"`
	Versao      string    `json:"versao,omitempty"`
	Comando     string    `json:"comando"`
	Quando      time.Time `json:"quando"`
	SaidaSHA256 string    `json:"saida_sha256"`
	Saida       string    `json:"saida"`
	Truncada    bool      `json:"saida_truncada,omitempty"`
	Erro        string    `json:"erro,omitempty"`
}

type Proveniencia struct {
	Gerador       string `json:"gerador"`
	SO            string `json:"so"`
	Arquitetura   string `json:"arquitetura"`
	AutorizadoPor string `json:"autorizado_por,omitempty"`
	Origem        string `json:"origem,omitempty"`
}

type Relatorio struct {
	Versao       string       `json:"versao_relatorio"`
	GeradoEm     time.Time    `json:"gerado_em"`
	Entrada      Entrada      `json:"entrada"`
	Passos       []Passo      `json:"passos"`
	Avisos       []string     `json:"avisos,omitempty"`
	Proveniencia Proveniencia `json:"proveniencia"`
}

func HashFile(path string) (string, int64, error) {
	f, err := os.Open(path)
	if err != nil {
		return "", 0, err
	}
	defer f.Close()
	h := sha256.New()
	n, err := io.Copy(h, f)
	if err != nil {
		return "", 0, err
	}
	return hex.EncodeToString(h.Sum(nil)), n, nil
}

func HashBytes(b []byte) string {
	s := sha256.Sum256(b)
	return hex.EncodeToString(s[:])
}

func Novo(entrada Entrada, autorizadoPor, origem string) *Relatorio {
	return &Relatorio{
		Versao: Versao, GeradoEm: time.Now().UTC(), Entrada: entrada,
		Proveniencia: Proveniencia{Gerador: "rea " + Versao, SO: runtime.GOOS, Arquitetura: runtime.GOARCH,
			AutorizadoPor: autorizadoPor, Origem: origem},
	}
}

func (r *Relatorio) AddPasso(p Passo) {
	p.SaidaSHA256 = HashBytes([]byte(p.Saida))
	r.Passos = append(r.Passos, p)
}

// Salvar grava <base>.json e <base>.md em dir (o chamador deve ter validado dir com o Guardian).
func (r *Relatorio) Salvar(dir string) (string, string, error) {
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return "", "", err
	}
	base := fmt.Sprintf("relatorio-%s-%s", r.GeradoEm.Format("20060102T150405Z"), r.Entrada.SHA256[:12])
	jp, mp := filepath.Join(dir, base+".json"), filepath.Join(dir, base+".md")
	b, err := json.MarshalIndent(r, "", "  ")
	if err != nil {
		return "", "", err
	}
	if err := os.WriteFile(jp, b, 0o644); err != nil {
		return "", "", err
	}
	return jp, mp, os.WriteFile(mp, []byte(r.Markdown()), 0o644)
}

func (r *Relatorio) Markdown() string {
	var b strings.Builder
	fmt.Fprintf(&b, "# Relatório REA\n\n- Gerado em: %s\n- Gerador: %s (%s/%s)\n", r.GeradoEm.Format(time.RFC3339),
		r.Proveniencia.Gerador, r.Proveniencia.SO, r.Proveniencia.Arquitetura)
	if r.Proveniencia.AutorizadoPor != "" {
		fmt.Fprintf(&b, "- Autorizado por: %s\n", r.Proveniencia.AutorizadoPor)
	}
	if r.Proveniencia.Origem != "" {
		fmt.Fprintf(&b, "- Origem declarada: %s\n", r.Proveniencia.Origem)
	}
	fmt.Fprintf(&b, "\n## Entrada\n\n- Arquivo: `%s`\n- SHA-256: `%s`\n- Tamanho: %d bytes\n- Formato: %s\n", r.Entrada.Caminho, r.Entrada.SHA256, r.Entrada.Tamanho, r.Entrada.Formato)
	if len(r.Avisos) > 0 {
		b.WriteString("\n## Avisos\n\n")
		for _, a := range r.Avisos {
			fmt.Fprintf(&b, "- %s\n", a)
		}
	}
	b.WriteString("\n## Passos\n")
	for _, p := range r.Passos {
		fmt.Fprintf(&b, "\n### %s %s\n\n- Comando: `%s`\n- Saída SHA-256: `%s`\n", p.Ferramenta, p.Versao, p.Comando, p.SaidaSHA256)
		if p.Erro != "" {
			fmt.Fprintf(&b, "- Erro: %s\n", p.Erro)
		}
		if p.Truncada {
			b.WriteString("- Saída truncada\n")
		}
		f := fence(p.Saida)
		fmt.Fprintf(&b, "\n%s\n%s\n%s\n", f, strings.TrimRight(p.Saida, "\n"), f)
	}
	return b.String()
}

// fence devolve uma cerca de crases maior que qualquer sequência de crases da saída,
// para que saída hostil de ferramentas não consiga fechar o bloco e injetar Markdown.
func fence(s string) string {
	max, run := 0, 0
	for _, c := range s {
		if c == '`' {
			run++
			if run > max {
				max = run
			}
		} else {
			run = 0
		}
	}
	if max < 3 {
		max = 2
	}
	return strings.Repeat("`", max+1)
}
