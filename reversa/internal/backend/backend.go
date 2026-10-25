// Package backend abstrai as ferramentas de análise (objdump, Ghidra, rizin, jadx...).
package backend

import (
	"bytes"
	"context"
	"fmt"
	"os/exec"
	"time"
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

const maxOutput = 16 << 10

// run executa um comando externo com timeout e corta a saída para caber no contexto do modelo.
func run(ctx context.Context, timeout time.Duration, name string, args ...string) (string, error) {
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	var out, errb bytes.Buffer
	cmd := exec.CommandContext(ctx, name, args...)
	cmd.Stdout, cmd.Stderr = &out, &errb
	err := cmd.Run()
	s := out.String()
	if len(s) > maxOutput {
		s = s[:maxOutput] + fmt.Sprintf("\n...[cortado: %d bytes omitidos]", len(s)-maxOutput)
	}
	if err != nil {
		return s, fmt.Errorf("%s: %w: %s", name, err, errb.String())
	}
	return s, nil
}
