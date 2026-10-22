// Package config carrega a configuração do HRAIL e localiza a raiz do projeto.
package config

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"hrail/internal/security"
)

// Config é a configuração do laboratório (configs/hrail.json).
type Config struct {
	DatabasePath   string   `json:"database_path"`
	ReportsDir     string   `json:"reports_dir"`
	CatalogDir     string   `json:"catalog_dir"`
	CommandTimeout string   `json:"command_timeout"`
	EnabledLevels  []string `json:"enabled_levels"`
	Agents         Agents   `json:"agents"`
}

// Agents configura provedores de IA (somente verificação de disponibilidade na Fase 0).
type Agents struct {
	Enabled      bool   `json:"enabled"`
	OllamaURL    string `json:"ollama_url"`
	DefaultModel string `json:"default_model"`
}

// Default devolve a configuração padrão, segura para a Fase 0.
func Default() Config {
	return Config{
		DatabasePath:   "data/hrail.db",
		ReportsDir:     "reports",
		CatalogDir:     "catalog",
		CommandTimeout: "10s",
		EnabledLevels:  []string{"A", "B"},
		Agents:         Agents{Enabled: false, OllamaURL: "http://127.0.0.1:11434"},
	}
}

// Timeout interpreta CommandTimeout.
func (c Config) Timeout() time.Duration {
	d, err := time.ParseDuration(c.CommandTimeout)
	if err != nil || d <= 0 {
		return 10 * time.Second
	}
	return d
}

// Validate rejeita configurações que violam a política da Fase 0.
func (c Config) Validate() error {
	for _, l := range c.EnabledLevels {
		if l != "A" && l != "B" {
			return fmt.Errorf("nível %q não pode ser habilitado na Fase 0 (somente A e B)", l)
		}
	}
	if len(c.EnabledLevels) == 0 {
		return errors.New("enabled_levels vazio")
	}
	if _, err := time.ParseDuration(c.CommandTimeout); err != nil {
		return fmt.Errorf("command_timeout inválido: %w", err)
	}
	return nil
}

// Load lê root/configs/hrail.json; se ausente, usa o padrão.
func Load(root string) (Config, error) {
	c := Default()
	b, err := os.ReadFile(filepath.Join(root, "configs", "hrail.json"))
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return c, c.Validate()
		}
		return c, err
	}
	if err := json.Unmarshal(b, &c); err != nil {
		return c, fmt.Errorf("configs/hrail.json inválido: %w", err)
	}
	return c, c.Validate()
}

// FindRoot sobe a partir de start até achar configs/hrail.json.
func FindRoot(start string) (string, error) {
	dir, err := filepath.Abs(start)
	if err != nil {
		return "", err
	}
	for {
		if _, err := os.Stat(filepath.Join(dir, "configs", "hrail.json")); err == nil {
			return dir, nil
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			return "", errors.New("raiz do HRAIL não encontrada (configs/hrail.json); use --raiz")
		}
		dir = parent
	}
}

// Resolve devolve um caminho confinado à raiz do projeto.
func (c Config) Resolve(root, p string) (string, error) { return security.ConfinePath(root, p) }
