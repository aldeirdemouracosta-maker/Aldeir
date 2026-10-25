// Comando rea: núcleo do REA-Laboratorio OS. Somente leitura por padrão.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"rea-lab/internal/aibridge"
	"rea-lab/internal/archive"
	"rea-lab/internal/binfmt"
	"rea-lab/internal/evidence"
	"rea-lab/internal/guardian"
	"rea-lab/internal/labs"
	"rea-lab/internal/manifest"
	"rea-lab/internal/tools"
	"rea-lab/modules"
)

const uso = `REA-Laboratorio OS — núcleo (somente leitura por padrão)

Uso: rea <comando> [opções] [argumentos]

  modulos [-json]            estado REAL de cada laboratório (disponivel/instalavel/quebrado/planejado)
  ferramentas [-json] [-v]   ferramentas externas detectadas no PATH (-v consulta a versão)
  hash <arquivo>             SHA-256 do arquivo
  detectar <arquivo>         formato por assinatura (PE/ELF/ZIP/ISO/PDF/GGUF...)
  zip <arquivo.zip>          lista ZIP com alertas anti-bomba/traversal (não extrai)
  analisar [opções] <arquivo>  pipeline estático + relatório (JSON e Markdown) em --saida
        --saida DIR  --autorizado-por NOME  --origem TEXTO
  ia [-json] [-remoto URL]   detecta motores de IA e aceleradores (remoto só com -autorizo-remoto)
  versao
`

func main() {
	if len(os.Args) < 2 {
		fmt.Print(uso)
		os.Exit(2)
	}
	ctx := context.Background()
	cmd, args := os.Args[1], os.Args[2:]
	var err error
	switch cmd {
	case "modulos":
		err = cmdModulos(args)
	case "ferramentas":
		err = cmdFerramentas(ctx, args)
	case "hash":
		err = cmdHash(args)
	case "detectar":
		err = cmdDetectar(args)
	case "zip":
		err = cmdZip(args)
	case "analisar":
		err = cmdAnalisar(ctx, args)
	case "ia":
		err = cmdIA(ctx, args)
	case "versao":
		fmt.Println("rea", evidence.Versao)
	case "-h", "--help", "ajuda":
		fmt.Print(uso)
	default:
		fmt.Fprintf(os.Stderr, "comando desconhecido: %s\n\n%s", cmd, uso)
		os.Exit(2)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "erro:", err)
		os.Exit(1)
	}
}

func printJSON(v any) {
	b, _ := json.MarshalIndent(v, "", "  ")
	fmt.Println(string(b))
}

func cmdModulos(args []string) error {
	fs := flag.NewFlagSet("modulos", flag.ContinueOnError)
	asJSON := fs.Bool("json", false, "saída JSON")
	if err := fs.Parse(args); err != nil {
		return err
	}
	mods, err := manifest.LoadAll(modules.FS)
	if err != nil {
		return err
	}
	est := labs.Avaliar(mods, exec.LookPath)
	if *asJSON {
		printJSON(est)
		return nil
	}
	for _, e := range est {
		fmt.Printf("%-14s %-11s %s\n", e.ID, strings.ToUpper(e.Estado), e.Motivo)
		if len(e.Encontradas) > 0 {
			fmt.Printf("%-14s %-11s ferramentas encontradas: %s\n", "", "", strings.Join(e.Encontradas, ", "))
		}
	}
	return nil
}

func cmdFerramentas(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("ferramentas", flag.ContinueOnError)
	asJSON := fs.Bool("json", false, "saída JSON")
	ver := fs.Bool("v", false, "consultar versão (executa a ferramenta com argumentos de versão)")
	if err := fs.Parse(args); err != nil {
		return err
	}
	det := tools.Detectar(ctx, exec.LookPath, guardian.Policy{}, *ver)
	if *asJSON {
		printJSON(det)
		return nil
	}
	for _, d := range det {
		switch {
		case !d.Presente:
			fmt.Printf("%-20s AUSENTE\n", d.Nome)
		case d.Adaptador:
			fmt.Printf("%-20s presente, com adaptador  %s  %s\n", d.Nome, d.Caminho, d.Versao)
		default:
			fmt.Printf("%-20s presente, SEM adaptador ainda  %s\n", d.Nome, d.Caminho)
		}
	}
	return nil
}

func oneFile(name string, args []string) (string, error) {
	if len(args) != 1 {
		return "", fmt.Errorf("uso: rea %s <arquivo>", name)
	}
	abs, err := filepath.Abs(args[0])
	if err != nil {
		return "", err
	}
	return abs, guardian.Policy{}.CheckRead(abs)
}

func cmdHash(args []string) error {
	p, err := oneFile("hash", args)
	if err != nil {
		return err
	}
	h, n, err := evidence.HashFile(p)
	if err != nil {
		return err
	}
	fmt.Printf("%s  %s  (%d bytes)\n", h, p, n)
	return nil
}

func cmdDetectar(args []string) error {
	p, err := oneFile("detectar", args)
	if err != nil {
		return err
	}
	i, err := binfmt.DetectFile(p)
	if err != nil {
		return err
	}
	printJSON(i)
	return nil
}

func cmdZip(args []string) error {
	p, err := oneFile("zip", args)
	if err != nil {
		return err
	}
	r, err := archive.ListZip(p, archive.DefaultLimits)
	if err != nil {
		return err
	}
	printJSON(r)
	return nil
}

func cmdAnalisar(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("analisar", flag.ContinueOnError)
	saida := fs.String("saida", "rea-saida", "diretório de trabalho para relatórios")
	por := fs.String("autorizado-por", "", "quem autorizou a análise")
	origem := fs.String("origem", "", "origem declarada do arquivo")
	if err := fs.Parse(args); err != nil {
		return err
	}
	pol := guardian.Policy{WorkDir: *saida}
	abs, err := oneFile("analisar", fs.Args())
	if err != nil {
		return err
	}
	if err := pol.CheckWrite(filepath.Join(*saida, "x")); err != nil {
		return err
	}
	h0, n, err := evidence.HashFile(abs)
	if err != nil {
		return err
	}
	info, err := binfmt.DetectFile(abs)
	if err != nil {
		return err
	}
	fmtDesc := info.Formato
	if info.Bits > 0 || info.Arquitetura != "" {
		fmtDesc = fmt.Sprintf("%s %d-bit %s", info.Formato, info.Bits, info.Arquitetura)
	}
	rel := evidence.Novo(evidence.Entrada{Caminho: abs, SHA256: h0, Tamanho: n, Formato: fmtDesc}, *por, *origem)
	rel.Avisos = append(rel.Avisos, "Análise estática: a amostra NUNCA é executada.")

	for _, f := range tools.Catalogo {
		if !f.Auto || f.Args == nil || (f.Aplica != nil && !f.Aplica(info.Formato)) {
			continue
		}
		bin, err := exec.LookPath(f.Nome)
		if err != nil {
			rel.Avisos = append(rel.Avisos, fmt.Sprintf("ferramenta %q não encontrada; passo ignorado", f.Nome))
			continue
		}
		comando, r := tools.Executar(ctx, pol, f, bin, abs)
		rel.AddPasso(evidence.Passo{Ferramenta: f.Nome, Versao: tools.Versao(ctx, pol, bin, f.VersaoArgs),
			Comando: comando, Quando: time.Now().UTC(), Saida: r.Saida, Truncada: r.Truncada, Erro: r.Erro})
	}
	if info.Formato == "ZIP" {
		if z, err := archive.ListZip(abs, archive.DefaultLimits); err == nil {
			b, _ := json.MarshalIndent(z, "", "  ")
			rel.AddPasso(evidence.Passo{Ferramenta: "rea:zip", Versao: evidence.Versao, Comando: "ListZip", Quando: time.Now().UTC(), Saida: string(b)})
			for _, a := range z.Alertas {
				rel.Avisos = append(rel.Avisos, "ZIP: "+a)
			}
		} else {
			rel.Avisos = append(rel.Avisos, "ZIP não pôde ser lido: "+err.Error())
		}
	}
	if h1, _, err := evidence.HashFile(abs); err != nil || h1 != h0 {
		rel.Avisos = append(rel.Avisos, "ALERTA: o arquivo mudou durante a análise")
	} else {
		rel.Avisos = append(rel.Avisos, "Integridade: SHA-256 do arquivo idêntico antes e depois da análise.")
	}
	jp, mp, err := rel.Salvar(*saida)
	if err != nil {
		return err
	}
	fmt.Printf("SHA-256: %s\nFormato: %s\nRelatórios:\n  %s\n  %s\n", h0, fmtDesc, jp, mp)
	return nil
}

func cmdIA(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("ia", flag.ContinueOnError)
	asJSON := fs.Bool("json", false, "saída JSON")
	remoto := fs.String("remoto", "", "URL de motor remoto OpenAI-compatível (LM Studio em rede etc.)")
	aut := fs.Bool("autorizo-remoto", false, "autoriza consultar o motor remoto informado")
	if err := fs.Parse(args); err != nil {
		return err
	}
	engines := aibridge.DefaultEngines()
	if *remoto != "" {
		engines = append(engines, aibridge.Engine{Nome: "Remoto (OpenAI-compatível)", Tipo: "openai", URL: *remoto})
	}
	c := &http.Client{Timeout: 3 * time.Second}
	var sts []aibridge.Status
	for _, e := range engines {
		sts = append(sts, aibridge.Probe(ctx, c, guardian.Policy{}, e, *aut))
	}
	acc := aibridge.Aceleradores(exec.LookPath)
	if *asJSON {
		printJSON(map[string]any{"motores": sts, "aceleradores": acc})
		return nil
	}
	for _, s := range sts {
		est := "AUSENTE"
		if s.Presente {
			est = "PRESENTE"
		}
		fmt.Printf("%-28s %-9s %s %s\n", s.Nome, est, s.URL, s.Detalhe)
		for _, m := range s.Modelos {
			fmt.Printf("    modelo: %s\n", m)
		}
	}
	fmt.Println("Aceleradores:", strings.Join(acc, "; "))
	fmt.Println("O sistema funciona sem nenhum motor de IA.")
	return nil
}
