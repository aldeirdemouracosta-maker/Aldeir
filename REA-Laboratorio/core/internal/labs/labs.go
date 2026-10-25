// Package labs calcula o estado real de cada módulo. "disponivel" exige código implementado,
// dependências presentes e teste de fumaça aprovado agora.
package labs

import (
	"archive/zip"
	"bytes"
	"fmt"
	"strings"

	"rea-lab/internal/archive"
	"rea-lab/internal/binfmt"
	"rea-lab/internal/manifest"
	"rea-lab/internal/tools"
)

type Estado struct {
	ID          string   `json:"id"`
	Nome        string   `json:"nome"`
	Estado      string   `json:"estado"` // disponivel | instalavel | quebrado | planejado
	Motivo      string   `json:"motivo,omitempty"`
	Encontradas []string `json:"ferramentas_encontradas,omitempty"`
	Ausentes    []string `json:"ferramentas_ausentes,omitempty"`
}

// Smoke: testes de fumaça com dados sintéticos e inofensivos, em memória.
var Smoke = map[string]func() error{
	"lab.formatos": func() error {
		elf := make([]byte, 64)
		copy(elf, "\x7fELF")
		elf[4], elf[5], elf[18] = 2, 1, 62
		i := binfmt.Detect(elf)
		if i.Formato != "ELF" || i.Bits != 64 || i.Arquitetura != "x86-64" {
			return fmt.Errorf("detecção ELF incorreta: %+v", i)
		}
		return nil
	},
	"lab.zip": func() error {
		var buf bytes.Buffer
		zw := zip.NewWriter(&buf)
		for _, n := range []string{"ok.txt", "../fora.txt"} {
			w, _ := zw.Create(n)
			w.Write([]byte("x"))
		}
		zw.Close()
		zr, err := zip.NewReader(bytes.NewReader(buf.Bytes()), int64(buf.Len()))
		if err != nil {
			return err
		}
		r := archive.List(zr, archive.DefaultLimits)
		if len(r.Entradas) != 2 || len(r.Alertas) == 0 {
			return fmt.Errorf("path traversal não sinalizado")
		}
		return nil
	},
}

func Avaliar(mods []manifest.Module, look tools.LookPath) []Estado {
	var out []Estado
	for _, m := range mods {
		e := Estado{ID: m.ID, Nome: m.Nome}
		for _, b := range m.Dependencias.Binarios {
			if _, err := look(b); err == nil {
				e.Encontradas = append(e.Encontradas, b)
			} else {
				e.Ausentes = append(e.Ausentes, b)
			}
		}
		switch {
		case !m.Implementado:
			e.Estado, e.Motivo = "planejado", fmt.Sprintf("adaptador do módulo ainda não implementado (fase %d)", m.Fase)
		case len(e.Ausentes) > 0:
			e.Estado, e.Motivo = "instalavel", "faltam: "+strings.Join(e.Ausentes, ", ")
		default:
			fn, ok := Smoke[m.ID]
			if !ok {
				e.Estado, e.Motivo = "quebrado", "sem teste de fumaça registrado"
			} else if err := fn(); err != nil {
				e.Estado, e.Motivo = "quebrado", "teste de fumaça falhou: "+err.Error()
			} else {
				e.Estado, e.Motivo = "disponivel", "teste de fumaça aprovado"
			}
		}
		out = append(out, e)
	}
	return out
}
