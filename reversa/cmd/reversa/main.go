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
	"runtime/debug"
	"strconv"
	"strings"
	"time"

	"reversa/internal/agent"
	"reversa/internal/backend"
	"reversa/internal/disc"
	"reversa/internal/evidence"
	"reversa/internal/llm"
	"reversa/internal/mcp"
	"reversa/internal/orchestrator"
	"reversa/internal/ps1"
	"reversa/internal/target"
	"reversa/internal/tools"
)

func backends() []backend.Backend {
	return []backend.Backend{backend.Objdump{}, backend.NewGhidra()}
}

func main() {
	if len(os.Args) < 2 {
		usage()
	}
	switch os.Args[1] {
	case "version":
		fmt.Println("reversa", buildInfo())
	case "doctor":
		fmt.Println("reversa", buildInfo())
		for _, b := range backends() {
			fmt.Printf("%-10s disponível=%v\n", b.Name(), b.Available())
		}
	case "analyze":
		analyze(os.Args[2:])
	case "ps1":
		analyzePS1(os.Args[2:])
	case "disc":
		discInfo(os.Args[2:])
	case "func":
		funcCmd(os.Args[2:])
	case "nomes":
		nomesCmd(os.Args[2:])
	case "find":
		findCmd(os.Args[2:])
	case "sector":
		sectorCmd(os.Args[2:])
	case "mem":
		memCmd(os.Args[2:])
	case "xref":
		xrefCmd(os.Args[2:])
	case "mcp":
		serveMCP(os.Args[2:])
	default:
		usage()
	}
}

func usage() {
	fmt.Fprintln(os.Stderr, "uso: reversa doctor | reversa func [-explain] <alvo> <endereço> | reversa nomes <alvo> | reversa find [-i|-utf16|-hex|-relative] <disco> <texto> | reversa sector [-n bytes] <disco> <setor> | reversa xref [-n bytes] <alvo> <endereço> | reversa mem [-n bytes] <alvo> <endereço> | reversa version | reversa mcp -root <pasta> | reversa disc <imagem> | reversa ps1 [opções] <exe|cue|bin|iso> | reversa analyze [-model m] [-steps n] [-evidence arq.json] <binário>")
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

// loadExeAddr carrega o alvo e interpreta o endereço (hexadecimal, com ou sem 0x) para os comandos de consulta.
func loadExeAddr(target, addrText string) (*ps1.Exe, uint32) {
	raw, err := loadPS1(target)
	if err != nil {
		fatal(err)
	}
	exe, err := ps1.ParseExe(raw)
	if err != nil {
		fatal(err)
	}
	addr, err := strconv.ParseUint(strings.TrimPrefix(strings.ToLower(addrText), "0x"), 16, 32)
	if err != nil {
		fatal(fmt.Errorf("endereço inválido %q: use hexadecimal, por exemplo 0x8002d640", addrText))
	}
	return exe, uint32(addr)
}

// parseHexBytes lê "46 72 65", "467265" ou "0x46 0x72" como bytes.
func parseHexBytes(s string) ([]byte, error) {
	s = strings.NewReplacer("0x", "", "0X", "", " ", "", ",", "").Replace(s)
	b, err := hex.DecodeString(s)
	if err != nil || len(b) == 0 {
		return nil, fmt.Errorf("bytes em hexadecimal inválidos: %q", s)
	}
	return b, nil
}

// findCmd procura texto ou bytes em TODOS os setores do disco, inclusive os fora dos arquivos do ISO 9660.
func findCmd(args []string) {
	fs := flag.NewFlagSet("find", flag.ExitOnError)
	fold := fs.Bool("i", false, "ignora maiúsculas e minúsculas (ASCII)")
	u16 := fs.Bool("utf16", false, "procura o texto em UTF-16 little-endian")
	hexMode := fs.Bool("hex", false, "o argumento são bytes em hexadecimal, por exemplo \"46 72 65\"")
	rel := fs.Bool("relative", false, "busca relativa: acha o texto em tabela de caracteres desconhecida (dá falsos positivos)")
	max := fs.Int("max", 30, "máximo de ocorrências")
	ctx := fs.Int("ctx", 24, "bytes de contexto antes e depois")
	out := fs.String("out", "", "grava o resultado neste arquivo .md (UTF-8)")
	_ = fs.Parse(args)
	if fs.NArg() != 2 {
		usage()
	}
	img, err := disc.Open(fs.Arg(0))
	if err != nil {
		fatal(err)
	}
	defer img.Close()
	text := fs.Arg(1)
	var window int
	var test func([]byte) bool
	var mode string
	switch {
	case *hexMode:
		b, err := parseHexBytes(text)
		if err != nil {
			fatal(err)
		}
		window, test, mode = len(b), disc.ExactTest(b, false), "bytes"
	case *rel:
		if len(text) < 3 {
			fatal(fmt.Errorf("a busca relativa precisa de pelo menos 3 letras (use a parte em minúsculas, por exemplo \"reya\")"))
		}
		window, test, mode = len(text), disc.RelativeTest([]byte(text)), "relativa: qualquer tabela com as mesmas distâncias entre as letras"
	case *u16:
		b := disc.UTF16LE(text)
		window, test, mode = len(b), disc.ExactTest(b, *fold), "UTF-16"
	default:
		window, test, mode = len(text), disc.ExactTest([]byte(text), *fold), "ASCII"
	}
	report, err := img.FindReport(fmt.Sprintf("%q (%s)", text, mode), window, test, *max, *ctx)
	if err != nil {
		fatal(err)
	}
	emit(report, *out)
}

// sectorCmd mostra bytes a partir de um setor do disco.
func sectorCmd(args []string) {
	fs := flag.NewFlagSet("sector", flag.ExitOnError)
	n := fs.Int("n", 256, "quantos bytes mostrar (máximo 4096)")
	out := fs.String("out", "", "grava o resultado neste arquivo .md (UTF-8)")
	_ = fs.Parse(args)
	if fs.NArg() != 2 {
		usage()
	}
	lba, err := strconv.ParseUint(fs.Arg(1), 0, 32)
	if err != nil {
		fatal(fmt.Errorf("setor inválido %q: use decimal ou 0x hexadecimal", fs.Arg(1)))
	}
	img, err := disc.Open(fs.Arg(0))
	if err != nil {
		fatal(err)
	}
	defer img.Close()
	report, err := img.SectorReport(uint32(lba), min(*n, 4096))
	if err != nil {
		fatal(err)
	}
	emit(report, *out)
}

// nomesCmd lista as funções com evidência de nome ou padrão (stubs, instaladores de callback, strings de depuração).
func nomesCmd(args []string) {
	fs := flag.NewFlagSet("nomes", flag.ExitOnError)
	insns := fs.Int("insns", 256, "máximo de instruções examinadas por função")
	out := fs.String("out", "", "grava o resultado neste arquivo .md (UTF-8)")
	_ = fs.Parse(args)
	if fs.NArg() != 1 {
		usage()
	}
	raw, err := loadPS1(fs.Arg(0))
	if err != nil {
		fatal(err)
	}
	exe, err := ps1.ParseExe(raw)
	if err != nil {
		fatal(err)
	}
	emit(orchestrator.NamesReport(exe, *insns), *out)
}

// memCmd mostra os valores iniciais da imagem em um endereço (tabelas, ponteiros).
func memCmd(args []string) {
	fs := flag.NewFlagSet("mem", flag.ExitOnError)
	n := fs.Int("n", 64, "quantos bytes mostrar (máximo 1024)")
	out := fs.String("out", "", "grava o resultado neste arquivo .md (UTF-8)")
	_ = fs.Parse(args)
	if fs.NArg() != 2 {
		usage()
	}
	exe, addr := loadExeAddr(fs.Arg(0), fs.Arg(1))
	report, err := orchestrator.MemReport(exe, addr, min(*n, 1024))
	if err != nil {
		fatal(err)
	}
	emit(report, *out)
}

// xrefCmd lista quem lê, escreve ou monta um endereço (ou intervalo).
func xrefCmd(args []string) {
	fs := flag.NewFlagSet("xref", flag.ExitOnError)
	n := fs.Int("n", 1, "tamanho do intervalo em bytes (use o tamanho de uma tabela para ver todos os acessos a ela)")
	max := fs.Int("max", 200, "máximo de linhas")
	out := fs.String("out", "", "grava o resultado neste arquivo .md (UTF-8)")
	_ = fs.Parse(args)
	if fs.NArg() != 2 {
		usage()
	}
	exe, addr := loadExeAddr(fs.Arg(0), fs.Arg(1))
	emit(orchestrator.XrefReport(exe, addr, *n, *max), *out)
}

func fatal(err error) {
	fmt.Fprintln(os.Stderr, "erro:", err)
	os.Exit(1)
}

func analyzePS1(args []string) {
	fs := flag.NewFlagSet("ps1", flag.ExitOnError)
	workerModel := fs.String("worker-model", "qwen2.5-coder:7b", "modelo pequeno que resume cada função")
	synthModel := fs.String("synth-model", "qwen2.5-coder:7b", "modelo que escreve o resumo geral (o 14B é ~3,5x mais lento e pouco melhor)")
	workers := fs.Int("workers", 2, "chamadas simultâneas ao Ollama (igual a OLLAMA_NUM_PARALLEL)")
	top := fs.Int("top", 24, "quantas funções analisar")
	insns := fs.Int("insns", 96, "instruções por função enviadas ao modelo")
	host := fs.String("ollama", os.Getenv("OLLAMA_HOST"), "endereço do Ollama (padrão http://127.0.0.1:11434)")
	workerTokens := fs.Int("worker-tokens", 200, "limite de tokens por resumo de função (0 = sem limite)")
	synthTokens := fs.Int("synth-tokens", 450, "limite de tokens do resumo geral (0 = sem limite)")
	cache := fs.String("cache", ".reversa-cache", "pasta do cache de respostas ('' desliga)")
	evOut := fs.String("evidence", "", "grava o log de evidências neste arquivo JSON")
	out := fs.String("out", "", "grava o relatório neste arquivo .md (UTF-8), além de mostrá-lo")
	_ = fs.Parse(args)
	if fs.NArg() != 1 {
		usage()
	}
	raw, err := loadPS1(fs.Arg(0))
	if err != nil {
		fatal(err)
	}
	exe, err := ps1.ParseExe(raw)
	if err != nil {
		fatal(err)
	}
	mk := func(model string, tokens int) llm.Chatter {
		o := llm.NewOllama(model)
		o.NumPredict = tokens
		if h := *host; h != "" {
			if !strings.Contains(h, "://") {
				h = "http://" + h
			}
			o.BaseURL = h
		}
		var c llm.Chatter = o
		if *cache != "" {
			c = llm.Cached{Inner: c, Model: fmt.Sprintf("%s|num_predict=%d", model, tokens), Dir: *cache}
		}
		return c
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	sum := sha256.Sum256(raw)
	log := &evidence.Log{Subject: hex.EncodeToString(sum[:])}
	p := &orchestrator.PS1{Worker: mk(*workerModel, *workerTokens), Synthesizer: mk(*synthModel, *synthTokens), Evidence: log,
		Workers: *workers, TopN: *top, MaxInsns: *insns}
	start := time.Now()
	p.Progress = func(format string, args ...any) {
		fmt.Fprintf(os.Stderr, "[%s] %s\n", time.Since(start).Round(time.Second), fmt.Sprintf(format, args...))
	}
	report, err := p.Run(ctx, exe)
	if *evOut != "" {
		data, _ := json.MarshalIndent(log.All(), "", "  ")
		_ = os.WriteFile(*evOut, data, 0o644)
	}
	if err != nil {
		fatal(err)
	}
	emit(report, *out)
}

// buildInfo identifica a versão do programa (commit e data), para saber se o binário está atualizado.
func buildInfo() string {
	bi, ok := debug.ReadBuildInfo()
	if !ok {
		return "versão desconhecida"
	}
	var rev, when, dirty string
	for _, s := range bi.Settings {
		switch s.Key {
		case "vcs.revision":
			rev = s.Value
		case "vcs.time":
			when = s.Value
		case "vcs.modified":
			if s.Value == "true" {
				dirty = " (com alterações locais)"
			}
		}
	}
	if rev == "" {
		return "versão desconhecida (compilado fora de um repositório git)"
	}
	if len(rev) > 7 {
		rev = rev[:7]
	}
	return fmt.Sprintf("commit %s de %s%s", rev, when, dirty)
}

// emit mostra o relatório e, se pedido, também o grava em arquivo. O rodapé registra qual versão o gerou.
func emit(report, path string) {
	report = strings.TrimRight(report, "\n") + "\n\n---\nGerado por reversa " + buildInfo() + "\n"
	fmt.Println(report)
	if path == "" {
		return
	}
	if err := os.WriteFile(path, []byte(report), 0o644); err != nil {
		fatal(err)
	}
	fmt.Fprintln(os.Stderr, "relatório salvo em", path)
}

// funcCmd mostra uma função só com fatos do programa; com -explain pede também uma explicação ao modelo.
func funcCmd(args []string) {
	fs := flag.NewFlagSet("func", flag.ExitOnError)
	insns := fs.Int("insns", 256, "máximo de instruções da função")
	explain := fs.Bool("explain", false, "pede ao modelo uma explicação (mais lento)")
	model := fs.String("model", "qwen2.5-coder:7b", "modelo usado por -explain")
	host := fs.String("ollama", os.Getenv("OLLAMA_HOST"), "endereço do Ollama")
	out := fs.String("out", "", "grava o relatório neste arquivo .md (UTF-8)")
	_ = fs.Parse(args)
	if fs.NArg() != 2 {
		usage()
	}
	raw, err := loadPS1(fs.Arg(0))
	if err != nil {
		fatal(err)
	}
	exe, err := ps1.ParseExe(raw)
	if err != nil {
		fatal(err)
	}
	addr, err := strconv.ParseUint(strings.TrimPrefix(strings.ToLower(fs.Arg(1)), "0x"), 16, 32)
	if err != nil {
		fatal(fmt.Errorf("endereço inválido %q: use hexadecimal, por exemplo 0x80026538", fs.Arg(1)))
	}
	report, err := orchestrator.FuncReport(exe, uint32(addr), *insns)
	if err != nil {
		fatal(err)
	}
	if *explain {
		o := llm.NewOllama(*model)
		o.NumPredict = 300
		if h := *host; h != "" {
			if !strings.Contains(h, "://") {
				h = "http://" + h
			}
			o.BaseURL = h
		}
		ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
		defer stop()
		fmt.Fprintln(os.Stderr, "consultando o modelo...")
		text, bad, err := orchestrator.ExplainFunction(ctx, o, exe, uint32(addr), *insns)
		if err != nil {
			fatal(err)
		}
		status := "inferida, não verificada"
		if len(bad) > 0 {
			status = "inferida, DESCARTADA: " + strings.Join(bad, "; ")
		}
		report += fmt.Sprintf("\n## Hipótese do modelo (%s)\n\n%s\n", status, text)
	}
	emit(report, *out)
}

func loadPS1(path string) ([]byte, error) {
	raw, origem, err := target.LoadPS1(path)
	if err == nil {
		fmt.Fprintln(os.Stderr, "alvo:", origem)
	}
	return raw, err
}

func discInfo(args []string) {
	if len(args) != 1 {
		usage()
	}
	img, err := disc.Open(args[0])
	if err != nil {
		fatal(err)
	}
	defer img.Close()
	fmt.Println("volume:", img.VolumeID)
	if boot, err := img.BootPath(); err == nil {
		fmt.Println("boot:", boot)
	}
	files, err := img.List("/")
	if err != nil {
		fatal(err)
	}
	for _, f := range files {
		kind := "arq"
		if f.IsDir {
			kind = "dir"
		}
		fmt.Printf("%s %10d  %s\n", kind, f.Size, f.Name)
	}
}

// serveMCP expõe as ferramentas do PS1 por stdio. Só lê arquivos dentro de -root.
func serveMCP(args []string) {
	fs := flag.NewFlagSet("mcp", flag.ExitOnError)
	root := fs.String("root", ".", "única pasta de onde as ferramentas podem ler arquivos")
	_ = fs.Parse(args)
	set := &tools.Set{Root: *root, Log: &evidence.Log{}}
	srv := mcp.NewServer("reversa", "0.1.0", set.MCP())
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	if err := srv.Serve(ctx, os.Stdin, os.Stdout); err != nil {
		fatal(err)
	}
}
