// reversa: engenharia reversa automatizada com IA local (Ollama + ferramentas de análise).
package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"os/signal"

	"reversa/internal/agent"
	"reversa/internal/backend"
	"reversa/internal/evidence"
	"reversa/internal/llm"
	"reversa/internal/orchestrator"
	"reversa/internal/ps1"
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
	case "ps1":
		analyzePS1(os.Args[2:])
	default:
		usage()
	}
}

func usage() {
	fmt.Fprintln(os.Stderr, "uso: reversa doctor | reversa ps1 [opções] <arquivo.exe> | reversa analyze [-model m] [-steps n] [-evidence arq.json] <binário>")
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

func analyzePS1(args []string) {
	fs := flag.NewFlagSet("ps1", flag.ExitOnError)
	workerModel := fs.String("worker-model", "qwen2.5-coder:7b", "modelo pequeno que resume cada função")
	synthModel := fs.String("synth-model", "qwen2.5-coder:14b", "modelo maior que escreve o relatório")
	workers := fs.Int("workers", 2, "chamadas simultâneas ao Ollama (igual a OLLAMA_NUM_PARALLEL)")
	top := fs.Int("top", 24, "quantas funções analisar")
	insns := fs.Int("insns", 96, "instruções por função enviadas ao modelo")
	cache := fs.String("cache", ".reversa-cache", "pasta do cache de respostas ('' desliga)")
	evOut := fs.String("evidence", "", "grava o log de evidências neste arquivo JSON")
	_ = fs.Parse(args)
	if fs.NArg() != 1 {
		usage()
	}
	raw, err := os.ReadFile(fs.Arg(0))
	if err != nil {
		fatal(err)
	}
	exe, err := ps1.ParseExe(raw)
	if err != nil {
		fatal(err)
	}
	mk := func(model string) llm.Chatter {
		var c llm.Chatter = llm.NewOllama(model)
		if *cache != "" {
			c = llm.Cached{Inner: c, Model: model, Dir: *cache}
		}
		return c
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	sum := sha256.Sum256(raw)
	log := &evidence.Log{Subject: hex.EncodeToString(sum[:])}
	p := &orchestrator.PS1{Worker: mk(*workerModel), Synthesizer: mk(*synthModel), Evidence: log,
		Workers: *workers, TopN: *top, MaxInsns: *insns}
	report, err := p.Run(ctx, exe)
	if *evOut != "" {
		data, _ := json.MarshalIndent(log.All(), "", "  ")
		_ = os.WriteFile(*evOut, data, 0o644)
	}
	if err != nil {
		fatal(err)
	}
	fmt.Println(report)
}
