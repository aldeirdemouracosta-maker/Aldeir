// Package tools cataloga ferramentas externas, detecta as realmente instaladas e as executa
// apenas em modo estático/somente leitura, com limites de tempo e saída, através do Guardian.
package tools

import (
	"bytes"
	"context"
	"os"
	"os/exec"
	"strings"
	"time"

	"rea-lab/internal/guardian"
)

type LookPath func(string) (string, error)

// Ferramenta descreve uma ferramenta candidata. Adaptador == Args != nil.
type Ferramenta struct {
	Nome       string
	Descricao  string
	VersaoArgs []string
	Args       func(arquivo string) []string // arquivo é sempre caminho absoluto
	Aplica     func(formato string) bool
	Auto       bool // roda automaticamente em "rea analisar"
}

func is(fs ...string) func(string) bool {
	return func(f string) bool {
		for _, x := range fs {
			if f == x {
				return true
			}
		}
		return false
	}
}

// Catalogo: somente comandos de leitura/análise estática. Nenhuma ferramenta executa a amostra.
var Catalogo = []Ferramenta{
	{Nome: "file", Descricao: "identificação de tipo", VersaoArgs: []string{"--version"},
		Args: func(a string) []string { return []string{"-b", a} }, Auto: true},
	{Nome: "strings", Descricao: "strings legíveis", VersaoArgs: []string{"--version"},
		Args: func(a string) []string { return []string{"-a", "-n", "8", a} }, Auto: true},
	{Nome: "readelf", Descricao: "cabeçalho ELF", VersaoArgs: []string{"--version"},
		Args: func(a string) []string { return []string{"-h", a} }, Aplica: is("ELF"), Auto: true},
	{Nome: "objdump", Descricao: "formato de objeto (PE/ELF)", VersaoArgs: []string{"--version"},
		Args: func(a string) []string { return []string{"-f", a} }, Aplica: is("ELF", "PE"), Auto: true},
	{Nome: "unzip", Descricao: "listagem de ZIP", VersaoArgs: []string{"-v"},
		Args: func(a string) []string { return []string{"-l", a} }, Aplica: is("ZIP"), Auto: false},
	{Nome: "pdfinfo", Descricao: "metadados de PDF", VersaoArgs: []string{"-v"},
		Args: func(a string) []string { return []string{a} }, Aplica: is("PDF"), Auto: true},
	{Nome: "ffprobe", Descricao: "metadados de mídia", VersaoArgs: []string{"-version"},
		Args: func(a string) []string {
			return []string{"-hide_banner", "-v", "error", "-show_format", "-show_streams", a}
		}},
	// Apenas detecção (sem adaptador ainda): aparecem como "detectada, sem adaptador".
	{Nome: "binwalk"}, {Nome: "7z"}, {Nome: "xorriso"}, {Nome: "mediainfo"}, {Nome: "lsblk"}, {Nome: "smartctl"},
	{Nome: "nmap"}, {Nome: "tshark"}, {Nome: "tcpdump"}, {Nome: "curl"}, {Nome: "aapt"}, {Nome: "dtc"},
	{Nome: "simg2img"}, {Nome: "mmls"}, {Nome: "lspci"}, {Nome: "vulkaninfo"}, {Nome: "glxinfo"},
	{Nome: "ollama"}, {Nome: "llama-server"}, {Nome: "qemu-img"}, {Nome: "qemu-system-x86_64"},
}

type Deteccao struct {
	Nome      string `json:"nome"`
	Presente  bool   `json:"presente"`
	Caminho   string `json:"caminho,omitempty"`
	Versao    string `json:"versao,omitempty"`
	Adaptador bool   `json:"adaptador"`
	Descricao string `json:"descricao,omitempty"`
}

// Detectar procura cada ferramenta do catálogo no PATH. Se comVersao, executa a ferramenta só com seus argumentos de versão.
func Detectar(ctx context.Context, look LookPath, pol guardian.Policy, comVersao bool) []Deteccao {
	var out []Deteccao
	for _, f := range Catalogo {
		d := Deteccao{Nome: f.Nome, Adaptador: f.Args != nil, Descricao: f.Descricao}
		if p, err := look(f.Nome); err == nil {
			d.Presente, d.Caminho = true, p
			if comVersao && f.VersaoArgs != nil {
				d.Versao = Versao(ctx, pol, p, f.VersaoArgs)
			}
		}
		out = append(out, d)
	}
	return out
}

func Procurar(nome string) (Ferramenta, bool) {
	for _, f := range Catalogo {
		if f.Nome == nome {
			return f, true
		}
	}
	return Ferramenta{}, false
}

type Resultado struct {
	Saida    string
	Truncada bool
	Erro     string
}

type limitWriter struct {
	buf bytes.Buffer
	max int
	cut bool
}

func (w *limitWriter) Write(p []byte) (int, error) {
	if room := w.max - w.buf.Len(); room > 0 {
		if len(p) > room {
			w.buf.Write(p[:room])
			w.cut = true
		} else {
			w.buf.Write(p)
		}
	} else {
		w.cut = true
	}
	return len(p), nil // descarta o excesso sem bloquear o processo
}

func exec1(ctx context.Context, pol guardian.Policy, bin string, args []string, timeout time.Duration, max int) Resultado {
	if err := pol.CheckExec(bin); err != nil {
		return Resultado{Erro: err.Error()}
	}
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	cmd := exec.CommandContext(ctx, bin, args...)
	cmd.Env = append(os.Environ(), "LC_ALL=C")
	w := &limitWriter{max: max}
	cmd.Stdout, cmd.Stderr = w, w
	err := cmd.Run()
	r := Resultado{Saida: w.buf.String(), Truncada: w.cut}
	if ctx.Err() == context.DeadlineExceeded {
		r.Erro = "tempo limite excedido"
	} else if err != nil {
		r.Erro = err.Error()
	}
	return r
}

// Versao devolve a primeira linha da saída de versão ("" se falhar).
func Versao(ctx context.Context, pol guardian.Policy, bin string, args []string) string {
	r := exec1(ctx, pol, bin, args, 3*time.Second, 4096)
	line, _, _ := strings.Cut(strings.TrimSpace(r.Saida), "\n")
	return line
}

// Executar roda a ferramenta no arquivo (caminho absoluto) com limite de 20 s e 256 KiB de saída.
func Executar(ctx context.Context, pol guardian.Policy, f Ferramenta, bin, arquivoAbs string) (string, Resultado) {
	args := f.Args(arquivoAbs)
	return bin + " " + strings.Join(args, " "), exec1(ctx, pol, bin, args, 20*time.Second, 256<<10)
}
