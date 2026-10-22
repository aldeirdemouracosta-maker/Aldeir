package main

import (
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"hrail/catalog"
	"hrail/internal/discovery"
	"hrail/internal/experiments"
	"hrail/internal/gitscan"
	"hrail/internal/research"
	"hrail/internal/security"
)

func newFlags(name string) *flag.FlagSet {
	fs := flag.NewFlagSet(name, flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	return fs
}

func splitCSV(s string) []string {
	var out []string
	for _, p := range strings.Split(s, ",") {
		if p = strings.TrimSpace(p); p != "" {
			out = append(out, p)
		}
	}
	return out
}

// overlayVerifications aplica verificações gravadas, se o banco já existir (sem criá-lo).
func (a *App) overlayVerifications(srcs []research.Source) []research.Source {
	p, err := a.dbPath()
	if err != nil {
		return srcs
	}
	if _, err := os.Stat(p); err != nil {
		return srcs
	}
	db, err := a.openDB()
	if err != nil {
		return srcs
	}
	vs, err := research.LoadVerifications(db)
	if err != nil {
		return srcs
	}
	return research.Overlay(srcs, vs)
}

func (a *App) cloneDir() (string, error) { return security.ConfinePath(a.Root, "data/clones") }

func (a *App) cmdVerificar(opts []string) error {
	fs := newFlags("research verificar")
	online := fs.Bool("online", false, "")
	clonar := fs.Bool("clonar", false, "")
	id := fs.String("id", "", "")
	prof := fs.Int("profundidade", 200, "")
	if err := fs.Parse(opts); err != nil {
		return err
	}
	srcs, err := research.ParseCatalog(catalog.SourcesJSON)
	if srcs == nil {
		return err
	}
	if *id != "" {
		s, ok := research.Find(srcs, *id)
		if !ok {
			return fmt.Errorf("fonte %q não cadastrada", *id)
		}
		srcs = []research.Source{s}
	}
	db, err := a.openDB()
	if err != nil {
		return err
	}
	if !*online {
		a.printf("Modo offline: nada foi consultado na rede. Estado gravado:\n\n")
		vs, _ := research.LoadVerifications(db)
		for _, s := range srcs {
			if r, ok := vs[s.ID]; ok {
				a.printf("  %-15s %-11s %s\n", s.ID, r.Status, r.Note)
			} else {
				a.printf("  %-15s nao_verificado\n", s.ID)
			}
		}
		a.printf("\nPara verificar: hrail research verificar --online [--clonar]\n")
		return nil
	}
	cd, err := a.cloneDir()
	if err != nil {
		return err
	}
	v := research.Verifier{Runner: a.runner, CloneDir: cd, Depth: *prof, NetTimeout: 3 * time.Minute}
	a.printf("Consultando %d fonte(s) em modo SOMENTE LEITURA (ls-remote/clone raso sem checkout/HEAD HTTP)%s...\n\n", len(srcs),
		map[bool]string{true: " com clone raso", false: ""}[*clonar])
	for _, s := range srcs {
		r := v.Verify(a.ctx, s, *clonar)
		if err := research.SaveVerification(db, r); err != nil {
			return err
		}
		head := ""
		if r.HeadCommit != "" {
			head = r.HeadCommit[:min(12, len(r.HeadCommit))] + " " + r.HeadDate
		}
		a.printf("  %-15s %-11s %s\n", s.ID, r.Status, head)
		a.printf("      %s\n", r.Note)
		if r.LicenseDetected != "" {
			a.printf("      licença detectada: %s (declarada: %s)\n", r.LicenseDetected, s.License)
		}
	}
	return nil
}

func (a *App) cmdHistorico(opts []string) error {
	fs := newFlags("research historico")
	fonte := fs.String("fonte", "", "")
	repo := fs.String("repo", "", "")
	palavras := fs.String("palavras", "polaris,gfx8,gfx803,radv,aco,revert", "")
	desde := fs.String("desde", "", "")
	max := fs.Int("max", 500, "")
	caminhos := fs.String("caminhos", "", "")
	todos := fs.Bool("todos", false, "")
	if err := fs.Parse(opts); err != nil {
		return err
	}
	if *fonte == "" {
		return errors.New("informe --fonte ID (use 'hrail research sources' para ver os ids)")
	}
	dir := *repo
	if dir == "" {
		cd, err := a.cloneDir()
		if err != nil {
			return err
		}
		dir = filepath.Join(cd, *fonte)
	}
	if _, err := os.Stat(dir); err != nil {
		return fmt.Errorf("repositório local %q não existe; execute 'hrail research verificar --online --clonar --id %s' ou informe --repo", dir, *fonte)
	}
	cs, err := gitscan.Scanner{Runner: a.runner}.Scan(a.ctx, dir, gitscan.Options{
		Since: *desde, MaxCommits: *max, Keywords: splitCSV(*palavras), Paths: splitCSV(*caminhos), OnlyMatches: !*todos})
	if err != nil {
		return err
	}
	db, err := a.openDB()
	if err != nil {
		return err
	}
	if err := gitscan.Save(db, *fonte, cs); err != nil {
		return err
	}
	rev := 0
	for _, c := range cs {
		if c.IsRevert {
			rev++
		}
	}
	a.printf("%d achado(s) gravado(s) para %q (%d reversão/ões). Palavras-chave: %s\n", len(cs), *fonte, rev, *palavras)
	a.printf("Achados são pistas, não conclusões: 'sem achados' NÃO significa compatível nem incompatível.\n")
	return nil
}

func (a *App) cmdCommits(opts []string) error {
	fs := newFlags("research commits")
	fonte := fs.String("fonte", "", "")
	rev := fs.Bool("revertidos", false, "")
	pal := fs.String("palavra", "", "")
	asJSON := fs.Bool("json", false, "")
	if err := fs.Parse(opts); err != nil {
		return err
	}
	db, err := a.openDB()
	if err != nil {
		return err
	}
	cs, srcs, err := gitscan.List(db, gitscan.Query{SourceID: *fonte, OnlyReverts: *rev, Keyword: strings.ToLower(*pal)})
	if err != nil {
		return err
	}
	if *asJSON {
		return a.writeJSON(a.Out, cs)
	}
	if len(cs) == 0 {
		a.printf("Nenhum achado gravado. Use 'hrail research historico --fonte ID'.\n")
		return nil
	}
	w := a.tab()
	fmt.Fprintln(w, "FONTE\tCOMMIT\tDATA\tREVERT\tPALAVRAS\tISSUES\tASSUNTO")
	for i, c := range cs {
		r := ""
		if c.IsRevert {
			r = "sim"
			if c.RevertedHash != "" {
				r = "→" + c.RevertedHash[:min(8, len(c.RevertedHash))]
			}
		}
		fmt.Fprintf(w, "%s\t%s\t%s\t%s\t%s\t%s\t%s\n", srcs[i], c.Hash[:min(10, len(c.Hash))], c.Date[:min(10, len(c.Date))], r,
			strings.Join(c.Keywords, ","), strings.Join(c.IssueRefs, ","), c.Subject)
	}
	return w.Flush()
}

func commitURL(s research.Source, hash string) (string, error) {
	switch s.HostKind {
	case "github":
		return strings.TrimSuffix(s.URL, "/") + "/commit/" + hash, nil
	case "gitlab":
		return strings.TrimSuffix(s.URL, "/") + "/-/commit/" + hash, nil
	}
	return "", fmt.Errorf("fonte %q não é um repositório Git", s.ID)
}

// cmdEvidencia registra uma evidência decidida por uma PESSOA, sempre ancorada num commit analisado.
func (a *App) cmdEvidencia(opts []string) error {
	fs := newFlags("research evidencia")
	exp := fs.String("experimento", "", "")
	fonte := fs.String("fonte", "", "")
	commit := fs.String("commit", "", "")
	postura := fs.String("postura", "", "")
	resumo := fs.String("resumo", "", "")
	if err := fs.Parse(opts); err != nil {
		return err
	}
	if *exp == "" || *fonte == "" || *commit == "" || *postura == "" || *resumo == "" {
		return errors.New("uso: hrail research evidencia --experimento ID --fonte ID --commit HASH --postura favoravel|contraria --resumo \"texto\"")
	}
	if !gitscan.ValidateHash(*commit) {
		return fmt.Errorf("commit %q não parece um hash", *commit)
	}
	srcs, err := research.ParseCatalog(catalog.SourcesJSON)
	if srcs == nil {
		return err
	}
	s, ok := research.Find(srcs, *fonte)
	if !ok {
		return fmt.Errorf("fonte %q não cadastrada", *fonte)
	}
	db, err := a.openDB()
	if err != nil {
		return err
	}
	full, found, err := gitscan.Exists(db, *fonte, strings.ToLower(*commit))
	if err != nil {
		return err
	}
	if !found {
		return fmt.Errorf("commit %s não consta nos achados de %q; analise antes com 'hrail research historico'", *commit, *fonte)
	}
	u, err := commitURL(s, full)
	if err != nil {
		return err
	}
	st, err := experiments.AddEvidence(db, *exp, *postura, experiments.Evidence{Summary: *resumo, URL: u})
	if err != nil {
		return err
	}
	a.printf("Evidência (%s) registrada em %s: %s\nEstado de evidência do experimento: %s\n", *postura, *exp, u, st)
	return nil
}

// cmdImportarVulkan importa um vulkaninfo coletado em outra máquina/SO (somente leitura do arquivo).
func (a *App) cmdImportarVulkan(opts []string) error {
	fs := newFlags("hardware importar")
	arq := fs.String("vulkan", "", "")
	salvar := fs.Bool("salvar", false, "")
	if err := fs.Parse(opts); err != nil {
		return err
	}
	if *arq == "" {
		return errors.New("uso: hrail hardware importar --vulkan ARQUIVO [--salvar]")
	}
	b, err := os.ReadFile(*arq)
	if err != nil {
		return err
	}
	if len(b) > 8<<20 {
		return errors.New("arquivo acima de 8 MiB")
	}
	v := discovery.ParseVulkanInfo(discovery.DecodeText(b))
	if v == nil {
		return errors.New("nenhum dispositivo reconhecido no arquivo (é a saída do vulkaninfo?)")
	}
	inv := discovery.FromVulkan(v, "importado: vulkaninfo ("+filepath.Base(*arq)+")")
	if *salvar {
		db, err := a.openDB()
		if err != nil {
			return err
		}
		id, err := db.SaveHardware(inv.Origin, inv)
		if err != nil {
			return err
		}
		a.printf("(snapshot de hardware #%d gravado; fonte: %s)\n", id, inv.Source)
	}
	return a.writeJSON(a.Out, inv)
}
