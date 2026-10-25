package backend

import (
	"context"
	"os/exec"
	"time"
)

// Objdump usa GNU objdump: leve, sem dependências, bom para triagem inicial.
type Objdump struct{}

func (Objdump) Name() string { return "objdump" }
func (Objdump) Available() bool {
	_, err := exec.LookPath("objdump")
	return err == nil
}

func (Objdump) Tools(target string) []Tool {
	limits := "Desmontagem linear: pode confundir dados com código e não resolve chamadas indiretas."
	return []Tool{
		{
			Name:        "objdump_headers",
			Description: "Cabeçalhos do arquivo, seções e símbolos dinâmicos (formato, arquitetura, bibliotecas).",
			Limits:      limits,
			Run: func(ctx context.Context, _ map[string]string) (string, error) {
				return run(ctx, 30*time.Second, "objdump", "-f", "-h", "-T", target)
			},
		},
		{
			Name:        "objdump_disasm",
			Description: "Desmonta um símbolo ou o início de .text.",
			Params:      map[string]string{"symbol": "nome do símbolo (opcional)"},
			Limits:      limits,
			Run: func(ctx context.Context, a map[string]string) (string, error) {
				args := []string{"-d", "--no-show-raw-insn"}
				if s := a["symbol"]; s != "" {
					args = append(args, "--disassemble="+s)
				}
				return run(ctx, 60*time.Second, "objdump", append(args, target)...)
			},
		},
		{
			Name:        "strings",
			Description: "Strings imprimíveis do binário (mínimo 6 caracteres).",
			Limits:      "Não decodifica strings ofuscadas nem UTF-16.",
			Run: func(ctx context.Context, _ map[string]string) (string, error) {
				return run(ctx, 30*time.Second, "strings", "-n", "6", target)
			},
		},
	}
}
