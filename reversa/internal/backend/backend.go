// Package backend abstrai as ferramentas de análise (objdump, Ghidra, rizin, jadx...).
package backend

import (
	"context"
)

// Tool é uma operação que o agente pode chamar.
type Tool struct {
	Name        string
	Description string
	// Params descreve os parâmetros como JSON Schema (properties).
	Params   map[string]string
	Required []string
	Limits   string
	Run      func(ctx context.Context, args map[string]string) (string, error)
}

// Backend agrupa ferramentas de um mesmo programa externo.
type Backend interface {
	Name() string
	Available() bool
	Tools(target string) []Tool
}
