// Package manifest carrega e valida os manifestos de módulos.
package manifest

import (
	"encoding/json"
	"fmt"
	"io/fs"
	"sort"
	"strings"
)

type Dependencias struct {
	Modulos       []string `json:"modulos"`
	PacotesDebian []string `json:"pacotes_debian"`
	Binarios      []string `json:"binarios"`
}

type Permissoes struct {
	Leitura         []string `json:"leitura"`
	Escrita         []string `json:"escrita"`
	Rede            bool     `json:"rede"`
	ExecutaAmostras bool     `json:"executa_amostras"`
	GravaFirmware   bool     `json:"grava_firmware"`
}

type Module struct {
	ID           string       `json:"id"`
	Nome         string       `json:"nome"`
	Versao       string       `json:"versao"`
	Local        string       `json:"local"`
	TamanhoMB    int          `json:"tamanho_mb"`
	Descricao    string       `json:"descricao"`
	Implementado bool         `json:"implementado"`
	Fase         int          `json:"fase"`
	Dependencias Dependencias `json:"dependencias"`
	Permissoes   Permissoes   `json:"permissoes"`
	Testes       []string     `json:"testes"`
}

// Validate rejeita manifestos que tentem habilitar permissões proibidas.
func (m Module) Validate() error {
	if !strings.HasPrefix(m.ID, "lab.") && m.ID != "core" {
		return fmt.Errorf("id inválido %q", m.ID)
	}
	if m.Nome == "" || m.Versao == "" {
		return fmt.Errorf("%s: nome e versão são obrigatórios", m.ID)
	}
	if m.Permissoes.ExecutaAmostras {
		return fmt.Errorf("%s: executa_amostras não pode ser verdadeiro", m.ID)
	}
	if m.Permissoes.GravaFirmware {
		return fmt.Errorf("%s: grava_firmware não pode ser verdadeiro", m.ID)
	}
	return nil
}

// LoadAll lê todos os *.json do diretório raiz do fs, validando cada um.
func LoadAll(fsys fs.FS) ([]Module, error) {
	files, err := fs.Glob(fsys, "*.json")
	if err != nil {
		return nil, err
	}
	var out []Module
	for _, f := range files {
		b, err := fs.ReadFile(fsys, f)
		if err != nil {
			return nil, err
		}
		var m Module
		if err := json.Unmarshal(b, &m); err != nil {
			return nil, fmt.Errorf("%s: %w", f, err)
		}
		if err := m.Validate(); err != nil {
			return nil, fmt.Errorf("%s: %w", f, err)
		}
		out = append(out, m)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].ID < out[j].ID })
	return out, nil
}
