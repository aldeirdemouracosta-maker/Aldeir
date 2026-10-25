package backend

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"time"
)

// Ghidra usa o modo headless (analyzeHeadless). Cada chamada importa o binário em um
// projeto persistente, então a análise automática só roda uma vez por arquivo.
type Ghidra struct {
	InstallDir string // GHIDRA_INSTALL_DIR
	ProjectDir string
}

func NewGhidra() Ghidra {
	dir := os.Getenv("GHIDRA_INSTALL_DIR")
	return Ghidra{InstallDir: dir, ProjectDir: filepath.Join(os.TempDir(), "reversa-ghidra")}
}

func (g Ghidra) Name() string { return "ghidra" }

func (g Ghidra) headless() string {
	return filepath.Join(g.InstallDir, "support", "analyzeHeadless")
}

func (g Ghidra) Available() bool {
	if g.InstallDir == "" {
		return false
	}
	_, err := exec.LookPath(g.headless())
	return err == nil
}

func (g Ghidra) Tools(target string) []Tool {
	_ = os.MkdirAll(g.ProjectDir, 0o755)
	script := func(name string, extra ...string) func(context.Context, map[string]string) (string, error) {
		return func(ctx context.Context, a map[string]string) (string, error) {
			args := []string{g.ProjectDir, "reversa", "-import", target, "-overwrite",
				"-scriptPath", filepath.Join("scripts", "ghidra"), "-postScript", name}
			args = append(args, extra...)
			return run(ctx, 10*time.Minute, g.headless(), args...)
		}
	}
	return []Tool{
		{
			Name:        "ghidra_functions",
			Description: "Lista funções reconhecidas pelo Ghidra com endereço e tamanho.",
			Limits:      "Depende da análise automática; funções só alcançáveis por salto indireto podem faltar.",
			Run:         script("ListFunctions.java"),
		},
		{
			Name:        "ghidra_decompile",
			Description: "Decompila uma função para pseudo-C.",
			Params:      map[string]string{"function": "nome ou endereço da função"},
			Required:    []string{"function"},
			Limits:      "Pseudo-C aproximado: tipos e nomes de variáveis são inferidos.",
			Run: func(ctx context.Context, a map[string]string) (string, error) {
				return script("Decompile.java", a["function"])(ctx, a)
			},
		},
	}
}
