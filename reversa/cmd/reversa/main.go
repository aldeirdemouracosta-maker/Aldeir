// reversa: engenharia reversa automatizada com IA local (Ollama + ferramentas de análise).
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"os/signal"

	"reversa/internal/agent"
	"reversa/internal/backend"
	"reversa/internal/evidence"
	"reversa/internal/llm"
)

func backends() []backend.Backend {
	return []backend.Backend{backend.Objdump{}, backend.NewGhidra()}
}

func main() {
	if len(os.Args) < 2 {
		usage()
	}
	switch os.Args[1] {
	case "doctor":
		for _, b := range backends() {
			fmt.Printf("%-10s disponível=%v\n", b.Name(), b.Available())
		}
	case "analyze":
		analyze(os.Args[2:])
	default:
		usage()
	}
}

func usage() {
	fmt.Fprintln(os.Stderr, "uso: reversa doctor | reversa analyze [-model m] [-steps n] [-evidence arq.json] <binário>")
	os.Exit(2)
}

func analyze(args []string) {
	fs := flag.NewFlagSet("analyze", flag.ExitOnError)
	model := fs.String("model", "qwen2.5-coder:14b", "modelo do Ollama com suporte a tools")
	steps := fs.Int("steps", 12, "máximo de passos do agente")
	evOut := fs.String("evidence", "", "grava o log de evidências neste arquivo JSON")
	_ = fs.Parse(args)
	if fs.NArg() != 1 {
		usage()
	}
	target := fs.Arg(0)
	if _, err := os.Stat(target); err != nil {
		fatal(err)
	}

	var tools []backend.Tool
	for _, b := range backends() {
		if b.Available() {
			tools = append(tools, b.Tools(target)...)
		}
	}
	if len(tools) == 0 {
		fatal(fmt.Errorf("nenhuma ferramenta de análise disponível; rode 'reversa doctor'"))
	}

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	log := &evidence.Log{}
	a := &agent.Agent{LLM: llm.NewOllama(*model), Tools: tools, Evidence: log, MaxSteps: *steps}
	report, err := a.Run(ctx, "Analise o binário "+target+" e explique o que ele faz, seus pontos de entrada e comportamentos suspeitos.")
	if *evOut != "" {
		data, _ := json.MarshalIndent(log.All(), "", "  ")
		_ = os.WriteFile(*evOut, data, 0o644)
	}
	if err != nil {
		fatal(err)
	}
	fmt.Println(report)
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, "erro:", err)
	os.Exit(1)
}
