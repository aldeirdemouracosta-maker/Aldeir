package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"syscall"
	"text/tabwriter"
	"time"

	"hrail/catalog"
	"hrail/internal/agents"
	"hrail/internal/benchmark"
	"hrail/internal/compiler"
	"hrail/internal/config"
	"hrail/internal/discovery"
	"hrail/internal/experiments"
	"hrail/internal/report"
	"hrail/internal/research"
	"hrail/internal/security"
	"hrail/internal/simulation"
	"hrail/internal/storage"
	"hrail/internal/tools"
)

// Version da CLI.
const Version = "0.1.0-fase0"

// App agrupa dependências da CLI.
type App struct {
	Out, Err io.Writer
	Root     string // vazio = descobrir
	SysRoot  string // "/" em produção; diretório fictício em testes
	Fixture  bool

	cfg     config.Config
	runner  *security.Runner
	defs    []tools.Def
	db      *storage.DB
	flushed int
	ctx     context.Context
}

func newApp(out, err io.Writer) *App {
	a := &App{Out: out, Err: err, SysRoot: "/"}
	// HRAIL_SYSROOT aponta para uma árvore fictícia (testes). Nesse caso os dados
	// são SEMPRE marcados como 'fixture'.
	if r := os.Getenv("HRAIL_SYSROOT"); r != "" {
		a.SysRoot, a.Fixture = r, true
	}
	return a
}

func (a *App) printf(f string, v ...any) { fmt.Fprintf(a.Out, f, v...) }
func (a *App) errorf(f string, v ...any) { fmt.Fprintf(a.Err, "erro: "+f+"\n", v...) }

const ajuda = `HRAIL — Hardware Research AI Lab (Fase 0: fundação e diagnóstico)

Uso: hrail [--raiz DIR] <comando> [subcomando] [opções]

Comandos:
  init                      cria o banco SQLite, aplica migrações e sincroniza catálogos
  doctor                    verifica dependências e permissões (somente leitura)
  hardware list             lista o hardware detectado
  hardware inspect          exporta o inventário técnico em JSON [--salvar] [--saida ARQ]
  tools list                lista ferramentas cadastradas (sem executá-las)
  tools check               verifica disponibilidade/versão das ferramentas
  research sources          mostra o catálogo de fontes [--tipo T] [--json]
  research validar          valida o catálogo de fontes e sincroniza com o banco
  research verificar        confirma fontes ONLINE (--online [--clonar] [--id ID]); sem --online só mostra o já gravado
  research historico        analisa commits/reversões/issues de um clone (--fonte ID [--palavras a,b] [--desde D] [--max N])
  research commits          consulta achados gravados [--fonte ID] [--revertidos] [--palavra P]
  research evidencia        registra evidência com URL num experimento (--experimento --fonte --commit --postura --resumo)
  simulation info           detecta simuladores (MGPUSim, gem5) sem simular
  simulation preparar|revisar|aprovar|compilar|rodar|resultados   Fase 2: MGPUSim em sandbox (ver docs/FASE2_MGPUSIM.md)
  compiler info             inventário Mesa/RADV/NIR/ACO e ferramentas de shader
  agents check              verifica disponibilidade de provedores de IA
  benchmark selftest        autoteste de CPU que valida o pipeline (NÃO é benchmark de hardware)
  experiment list           lista experimentos registrados [--json]
  experiment registrar      registra experimento de um JSON (--arquivo ARQ)
  banco exportar            exporta o banco (--formato json|csv, --tabela T, --saida ARQ)
  report generate           gera relatório Markdown e JSON em reports/
  version                   mostra a versão
`

// Run executa a CLI e devolve o código de saída.
func (a *App) Run(args []string) (code int) {
	fs := flag.NewFlagSet("hrail", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	root := fs.String("raiz", os.Getenv("HRAIL_RAIZ"), "")
	if err := fs.Parse(args); err != nil {
		a.errorf("%v\n\n%s", err, ajuda)
		return 2
	}
	rest := fs.Args()
	if len(rest) == 0 || rest[0] == "ajuda" || rest[0] == "help" {
		a.printf("%s", ajuda)
		return 0
	}
	if rest[0] == "version" || rest[0] == "versao" {
		a.printf("hrail %s\n", Version)
		return 0
	}
	if err := a.setup(*root); err != nil {
		a.errorf("%v", err)
		return 1
	}
	defer a.finish()
	var err error
	cmd, sub := rest[0], ""
	if len(rest) > 1 {
		sub = rest[1]
	}
	var opts []string
	if len(rest) > 2 {
		opts = rest[2:]
	}
	switch cmd {
	case "init":
		err = a.cmdInit()
	case "doctor":
		err = a.cmdDoctor()
	case "hardware":
		err = a.cmdHardware(sub, opts)
	case "tools":
		err = a.cmdTools(sub)
	case "research":
		err = a.cmdResearch(sub, opts)
	case "simulation":
		err = a.cmdSimulation(sub, opts)
	case "compiler":
		err = a.cmdCompiler()
	case "agents":
		err = a.cmdAgents()
	case "benchmark":
		err = a.cmdBenchmark(sub)
	case "experiment":
		err = a.cmdExperiment(sub, opts)
	case "banco":
		err = a.cmdBanco(sub, opts)
	case "report":
		err = a.cmdReport(sub)
	default:
		a.errorf("comando desconhecido %q\n\n%s", cmd, ajuda)
		return 2
	}
	if err != nil {
		a.errorf("%v", err)
		return 1
	}
	return 0
}

func (a *App) setup(rootFlag string) error {
	a.ctx = context.Background()
	if a.Root == "" {
		a.Root = rootFlag
	}
	if a.Root == "" {
		wd, _ := os.Getwd()
		r, err := config.FindRoot(wd)
		if err != nil {
			return err
		}
		a.Root = r
	}
	abs, err := filepath.Abs(a.Root)
	if err != nil {
		return err
	}
	a.Root = abs
	cfg, err := config.Load(a.Root)
	if err != nil {
		return fmt.Errorf("configuração: %w", err)
	}
	a.cfg = cfg
	defs, err := tools.ParseCatalog(catalog.ToolsJSON)
	if err != nil {
		return err
	}
	a.defs = defs
	a.runner = security.NewRunner(cfg.Timeout(), tools.AllowList(defs)...)
	return nil
}

func (a *App) dbPath() (string, error) {
	return security.ConfinePath(a.Root, a.cfg.DatabasePath)
}

func (a *App) openDB() (*storage.DB, error) {
	if a.db != nil {
		return a.db, nil
	}
	p, err := a.dbPath()
	if err != nil {
		return nil, err
	}
	db, err := storage.Open(p)
	if err != nil {
		return nil, fmt.Errorf("banco de dados: %w", err)
	}
	a.db = db
	return db, nil
}

// finish persiste o registro de comandos externos (se o banco foi aberto) e fecha.
func (a *App) finish() {
	if a.db == nil {
		return
	}
	recs := a.runner.Records()
	for ; a.flushed < len(recs); a.flushed++ {
		if err := a.db.LogCommand(recs[a.flushed]); err != nil {
			a.errorf("registrando comando: %v", err)
		}
	}
	a.db.Close()
	a.db = nil
}

func (a *App) registry() *tools.Registry { return tools.New(a.defs, a.runner) }

func (a *App) collector() *discovery.Collector {
	c := discovery.NewCollector(a.runner)
	c.Root, c.Fixture = a.SysRoot, a.Fixture
	return c
}

func (a *App) writeJSON(w io.Writer, v any) error {
	enc := json.NewEncoder(w)
	enc.SetIndent("", "  ")
	return enc.Encode(v)
}

func (a *App) tab() *tabwriter.Writer { return tabwriter.NewWriter(a.Out, 0, 4, 2, ' ', 0) }

// ---------------- comandos ----------------

func (a *App) cmdInit() error {
	db, err := a.openDB()
	if err != nil {
		return err
	}
	v, _ := db.SchemaVersion()
	srcs, err := research.ParseCatalog(catalog.SourcesJSON)
	if err != nil {
		return err
	}
	if err := research.Save(db, srcs); err != nil {
		return err
	}
	if err := tools.Save(db, a.registry().List()); err != nil {
		return err
	}
	if err := experiments.Save(db, benchmark.SelfTestExperiment(), experiments.EnabledLevels(a.cfg.EnabledLevels)); err != nil && !strings.Contains(err.Error(), "UNIQUE") {
		return err
	}
	p, _ := a.dbPath()
	a.printf("Banco pronto em %s (esquema v%d).\n%d fontes e %d ferramentas catalogadas (ferramentas como nao_testado).\n", p, v, len(srcs), len(a.defs))
	a.printf("Próximo passo: hrail doctor && hrail tools check\n")
	return nil
}

func (a *App) cmdDoctor() error {
	fails := 0
	ok := func(f string, v ...any) { a.printf("  [OK]     "+f+"\n", v...) }
	warn := func(f string, v ...any) { a.printf("  [AVISO]  "+f+"\n", v...) }
	bad := func(f string, v ...any) { a.printf("  [FALHA]  "+f+"\n", v...); fails++ }

	a.printf("HRAIL doctor — verificação somente leitura\n\nProjeto: %s\n\n", a.Root)
	ok("configuração válida (níveis habilitados: %s; timeout: %s)", strings.Join(a.cfg.EnabledLevels, ","), a.cfg.Timeout())
	ok("catálogo de ferramentas: %d entradas", len(a.defs))
	if srcs, err := research.ParseCatalog(catalog.SourcesJSON); err != nil {
		bad("catálogo de fontes inválido: %v", err)
	} else {
		unv := 0
		for _, s := range srcs {
			if s.Verification.Status != research.Verificado {
				unv++
			}
		}
		ok("catálogo de fontes válido: %d fontes (%d ainda não verificadas online)", len(srcs), unv)
		if unv > 0 {
			warn("fontes não verificadas: confirme existência/autenticidade antes de usar")
		}
	}
	if p, err := a.dbPath(); err != nil {
		bad("caminho do banco: %v", err)
	} else if v, err := storage.Inspect(p); err != nil {
		warn("banco ainda não criado em %s (execute: hrail init)", p)
	} else {
		ok("banco SQLite em %s (esquema v%d)", p, v)
	}
	// Permissões / sistema (leitura)
	if _, err := os.ReadDir(filepath.Join(a.SysRoot, "sys/bus/pci/devices")); err != nil {
		warn("/sys/bus/pci/devices ilegível: inventário PCI ficará vazio")
	} else {
		ok("/sys/bus/pci/devices legível")
	}
	nodes, _ := filepath.Glob(filepath.Join(a.SysRoot, "dev/dri/*"))
	if len(nodes) == 0 {
		warn("nenhum nó em /dev/dri (sem GPU exposta ou sem driver)")
	}
	for _, n := range nodes {
		if syscall.Access(n, 4|2) == nil {
			ok("%s: leitura/escrita permitidas ao usuário atual", n)
		} else {
			warn("%s: sem permissão de leitura/escrita para o usuário atual (grupo render/video?) — nenhuma alteração será feita", n)
		}
	}
	if os.Geteuid() == 0 {
		warn("executando como root; o HRAIL nunca usa sudo e é recomendável rodar como usuário comum")
	}
	reg := a.registry()
	for _, c := range reg.CheckAll(a.ctx) {
		switch {
		case c.Status == tools.Disponivel:
			ok("%s: disponível %s", c.Def.ID, c.Version)
		case c.Def.Required && c.Status != tools.NaoTestado:
			bad("%s (obrigatória): %s — %s", c.Def.ID, c.Status, c.Detail)
		case c.Status == tools.Incompativel:
			warn("%s: incompatível — %s", c.Def.ID, c.Detail)
		case c.Status == tools.Ausente:
			warn("%s: ausente (opcional)", c.Def.ID)
		}
	}
	a.printf("\n")
	if fails > 0 {
		return fmt.Errorf("%d verificação(ões) obrigatória(s) falharam", fails)
	}
	a.printf("Diagnóstico concluído sem falhas obrigatórias. Avisos indicam recursos opcionais ausentes.\n")
	return nil
}

func (a *App) cmdHardware(sub string, opts []string) error {
	switch sub {
	case "list":
		inv := a.collector().Collect(a.ctx)
		a.printHardware(inv)
		return nil
	case "inspect":
		fs := flag.NewFlagSet("hardware inspect", flag.ContinueOnError)
		fs.SetOutput(io.Discard)
		salvar := fs.Bool("salvar", false, "")
		saida := fs.String("saida", "", "")
		if err := fs.Parse(opts); err != nil {
			return err
		}
		inv := a.collector().Collect(a.ctx)
		var w io.Writer = a.Out
		if *saida != "" {
			p, err := security.ConfinePath(a.Root, *saida)
			if err != nil {
				return err
			}
			if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
				return err
			}
			f, err := os.Create(p)
			if err != nil {
				return err
			}
			defer f.Close()
			w = f
			defer a.printf("Inventário salvo em %s\n", p)
		}
		if *salvar {
			db, err := a.openDB()
			if err != nil {
				return err
			}
			id, err := db.SaveHardware(inv.Origin, inv)
			if err != nil {
				return err
			}
			a.printf("(snapshot de hardware #%d gravado no banco)\n", id)
		}
		return a.writeJSON(w, inv)
	}
	return fmt.Errorf("use: hrail hardware list | inspect")
}

func (a *App) printHardware(inv discovery.Inventory) {
	a.printf("Origem dos dados: %s\n", inv.Origin)
	a.printf("Kernel: %s\n", orDash(inv.Kernel))
	a.printf("CPU:    %s (%d CPUs lógicas)\n", orDash(inv.CPU.Model), inv.CPU.Logical)
	if v, ok := inv.CPU.Features["avx2"]; ok {
		a.printf("        AVX2: %v | AVX: %v | SSE4.2: %v\n", v, inv.CPU.Features["avx"], inv.CPU.Features["sse4_2"])
	} else {
		a.printf("        AVX2: desconhecido (flags indisponíveis)\n")
	}
	a.printf("RAM:    %d MiB total\n", inv.Memory.TotalKiB/1024)
	a.printf("\nArmazenamento:\n")
	if len(inv.Storage) == 0 {
		a.printf("  (nenhum dispositivo de bloco legível)\n")
	}
	for _, s := range inv.Storage {
		a.printf("  %-10s %8d GiB  %s\n", s.Name, s.SizeBytes>>30, s.Model)
	}
	a.printf("\nDispositivos PCI: %d\n", len(inv.PCI))
	w := a.tab()
	for _, p := range inv.PCI {
		if p.IsDisplayLike || p.Driver != "" {
			fmt.Fprintf(w, "  %s\t%s:%s\trev %s\tclasse %s\tdriver %s\tlink %s x%s\n", p.Address, p.VendorID, p.DeviceID, orDash(p.Revision), p.Class, orDash(p.Driver), orDash(p.CurLinkSpeed), orDash(p.CurLinkWidth))
		}
	}
	w.Flush()
	a.printf("\nGPUs: %d\n", len(inv.GPUs))
	for _, g := range inv.GPUs {
		a.printf("  %s  %s:%s rev %s\n", g.PCIAddress, g.VendorID, g.DeviceID, orDash(g.Revision))
		a.printf("    nome: %s [%s]\n", orDash(g.Name), orDash(g.NameSource))
		a.printf("    arquitetura: %s [%s]  gfx: %s\n", orDash(g.ArchFamily), orDash(g.ArchFamilySource), orDash(g.GFXID))
		a.printf("    driver do kernel: %s %s\n", orDash(g.KernelDriver), g.KernelDriverVersion)
		if g.VRAMTotalBytes != nil {
			a.printf("    VRAM: %d MiB\n", *g.VRAMTotalBytes>>20)
		}
		if g.KnownVariant != nil {
			a.printf("    ⚠ %s [%s]: %s\n", g.KnownVariant.Name, g.KnownVariant.Level, g.KnownVariant.Note)
		}
		if g.Vulkan != nil {
			a.printf("    Vulkan: API %s, driver %s, Mesa %s, %d extensões\n", orDash(g.Vulkan.APIVersion), orDash(g.Vulkan.DriverName), orDash(g.Vulkan.MesaVersion), len(g.Vulkan.Extensions))
		}
		for _, n := range g.NotDetermined {
			a.printf("    não determinado: %s\n", n)
		}
	}
	if len(inv.Unavailable) > 0 {
		a.printf("\nInformações indisponíveis (não inventadas):\n")
		for _, u := range inv.Unavailable {
			a.printf("  - %s\n", u)
		}
	}
}

func orDash(s string) string {
	if s == "" {
		return "—"
	}
	return s
}

func (a *App) cmdTools(sub string) error {
	reg := a.registry()
	switch sub {
	case "list":
		w := a.tab()
		fmt.Fprintln(w, "ID\tCATEGORIA\tLICENÇA (verificada?)\tFINALIDADE")
		for _, c := range reg.List() {
			fmt.Fprintf(w, "%s\t%s\t%s (%v)\t%s\n", c.Def.ID, c.Def.Category, c.Def.License, c.Def.LicenseVerified, c.Def.Purpose)
		}
		w.Flush()
		a.printf("\nEstado de todas: nao_testado (use 'hrail tools check' para verificar).\n")
		return nil
	case "check":
		cs := reg.CheckAll(a.ctx)
		w := a.tab()
		fmt.Fprintln(w, "ID\tESTADO\tVERSÃO\tCAMINHO/DETALHE")
		count := map[tools.Status]int{}
		for _, c := range cs {
			count[c.Status]++
			fmt.Fprintf(w, "%s\t%s\t%s\t%s\n", c.Def.ID, c.Status, orDash(c.Version), orDash(firstNonEmpty(c.Path, c.Detail)))
		}
		w.Flush()
		a.printf("\nResumo: %d disponível, %d ausente, %d incompatível, %d não testado.\n",
			count[tools.Disponivel], count[tools.Ausente], count[tools.Incompativel], count[tools.NaoTestado])
		a.printf("Ferramentas ausentes são opcionais e não impedem o uso do laboratório.\n")
		if db, err := a.openDB(); err == nil {
			if err := tools.Save(db, cs); err != nil {
				a.errorf("gravando estado das ferramentas: %v", err)
			}
		}
		return nil
	}
	return fmt.Errorf("use: hrail tools list | check")
}

func firstNonEmpty(ss ...string) string {
	for _, s := range ss {
		if s != "" {
			return s
		}
	}
	return ""
}

func (a *App) cmdResearch(sub string, opts []string) error {
	switch sub {
	case "verificar":
		return a.cmdVerificar(opts)
	case "historico":
		return a.cmdHistorico(opts)
	case "commits":
		return a.cmdCommits(opts)
	case "evidencia":
		return a.cmdEvidencia(opts)
	}
	srcs, err := research.ParseCatalog(catalog.SourcesJSON)
	switch sub {
	case "sources":
		if srcs == nil {
			return err
		}
		fs := flag.NewFlagSet("research sources", flag.ContinueOnError)
		fs.SetOutput(io.Discard)
		tipo := fs.String("tipo", "", "")
		asJSON := fs.Bool("json", false, "")
		if e := fs.Parse(opts); e != nil {
			return e
		}
		srcs = a.overlayVerifications(srcs)
		list := research.Filter(srcs, *tipo)
		if *asJSON {
			return a.writeJSON(a.Out, list)
		}
		for _, s := range list {
			lc := "não consultado"
			if s.LastCommitConsulted != nil {
				lc = *s.LastCommitConsulted
			}
			a.printf("%s — %s\n  URL: %s\n  Tipo: %s | Licença: %s (verificada: %v)\n  Arquitetura: %s\n  Finalidade: %s\n  Manutenção: %s | Último commit consultado: %s\n  Verificação: %s\n  Limitações: %s\n  Aplicações: %s\n\n",
				s.ID, s.Name, s.URL, s.Kind, s.License, s.LicenseVerified, orDash(strings.Join(s.Architectures, "; ")), s.Purpose,
				s.MaintenanceState, lc, s.Verification.Status, strings.Join(s.Limitations, " | "), strings.Join(s.Applications, "; "))
		}
		if err != nil {
			a.printf("ATENÇÃO: %v\n", err)
		}
		return nil
	case "validar":
		if err != nil {
			return err
		}
		db, e := a.openDB()
		if e != nil {
			return e
		}
		if e := research.Save(db, srcs); e != nil {
			return e
		}
		a.printf("Catálogo válido: %d fontes sincronizadas com o banco.\nNota: validação estrutural; existência/autenticidade online NÃO foram verificadas.\n", len(srcs))
		return nil
	}
	return fmt.Errorf("use: hrail research sources | validar | verificar | historico | commits | evidencia")
}

func (a *App) cmdSimulationInfo() error {
	for _, i := range simulation.New(a.registry()).Describe(a.ctx) {
		a.printf("%s: %s\n  estado: %s %s\n  arquiteturas: %s\n  equivalências declaradas: %d\n  executa cargas: %v\n  %s\n\n",
			i.Metadata.ID, i.Metadata.Description, i.Check.Status, firstNonEmpty(i.Check.Path, i.Check.Detail),
			strings.Join(i.Metadata.SupportedArch, "; "), len(i.Metadata.EquivalenceClaims), i.Metadata.ExecutesWorkloads, i.Notice)
	}
	return nil
}

func (a *App) cmdCompiler() error {
	inv := compiler.Collect(a.ctx, a.registry())
	for _, g := range []struct {
		n  string
		cs []tools.Check
	}{{"Mesa", inv.Mesa}, {"Shaders/SPIR-V", inv.Shader}} {
		a.printf("%s:\n", g.n)
		for _, c := range g.cs {
			a.printf("  %-18s %-13s %s\n", c.Def.ID, c.Status, orDash(firstNonEmpty(c.Version, c.Detail)))
		}
	}
	a.printf("\nAnálises offline:\n")
	for _, c := range inv.Offline {
		a.printf("  %-18s possível=%v — %s\n", c.Name, c.Possible, c.Reason)
	}
	return nil
}

func (a *App) cmdAgents() error {
	reg := a.registry()
	ps := []agents.Provider{agents.Ollama{Registry: reg, Cfg: a.cfg.Agents}, agents.LlamaCpp{Registry: reg}}
	for _, v := range agents.CheckAll(a.ctx, ps) {
		a.printf("%-10s disponível=%-5v %s\n", v.Provider, v.Available, v.Detail)
	}
	a.printf("\nPolítica: agentes só sugerem hipóteses; nunca aprovam mudanças privilegiadas nem declaram melhorias sem medições.\n")
	return nil
}

func (a *App) cmdBenchmark(sub string) error {
	if sub != "selftest" {
		return fmt.Errorf("use: hrail benchmark selftest")
	}
	db, err := a.openDB()
	if err != nil {
		return err
	}
	if err := experiments.Save(db, benchmark.SelfTestExperiment(), experiments.EnabledLevels(a.cfg.EnabledLevels)); err != nil && !strings.Contains(err.Error(), "UNIQUE") {
		return err
	}
	inv := a.collector().Collect(a.ctx)
	opt := benchmark.Options{SysRoot: a.SysRoot, Version: Version}
	if len(inv.GPUs) > 0 {
		opt.GPU = inv.GPUs[0].Name
		opt.Drv = inv.GPUs[0].KernelDriver
	}
	res, err := benchmark.SelfTest(a.ctx, opt)
	if err != nil {
		return err
	}
	snap, err := db.SaveHardware(inv.Origin, inv)
	if err != nil {
		return err
	}
	res.HardwareSnapshotID = snap
	if err := benchmark.Save(db, res); err != nil {
		return err
	}
	a.printf("*** TESTE DA INFRAESTRUTURA — não é benchmark de hardware ***\n")
	a.printf("Experimento: %s | origem: %s | %s = %.0f %s\n", res.ExperimentID, res.Origin, res.Metric, res.Value, res.Unit)
	if res.Meta.TempCelsius != nil {
		a.printf("Temperatura (%s): %.1f °C\n", res.Meta.TempSource, *res.Meta.TempCelsius)
	} else {
		a.printf("Temperatura: indisponível neste ambiente\n")
	}
	a.printf("Resultado e snapshot de hardware #%d gravados no banco.\n", snap)
	return nil
}

func (a *App) cmdExperiment(sub string, opts []string) error {
	db, err := a.openDB()
	if err != nil {
		return err
	}
	switch sub {
	case "list":
		fs := flag.NewFlagSet("experiment list", flag.ContinueOnError)
		fs.SetOutput(io.Discard)
		asJSON := fs.Bool("json", false, "")
		if e := fs.Parse(opts); e != nil {
			return e
		}
		es, err := experiments.List(db)
		if err != nil {
			return err
		}
		if *asJSON {
			return a.writeJSON(a.Out, es)
		}
		if len(es) == 0 {
			a.printf("Nenhum experimento registrado. Use 'hrail init' ou 'hrail benchmark selftest'.\n")
			return nil
		}
		w := a.tab()
		fmt.Fprintln(w, "ID\tNÍVEL\tORIGEM\tEVIDÊNCIA\tOBS")
		for _, e := range es {
			obs := ""
			if e.InfrastructureTest {
				obs = "TESTE DE INFRAESTRUTURA"
			}
			fmt.Fprintf(w, "%s\t%s\t%s\t%s\t%s\n", e.ID, e.Level, e.Origin, e.State(), obs)
		}
		w.Flush()
		return nil
	case "registrar":
		fs := flag.NewFlagSet("experiment registrar", flag.ContinueOnError)
		fs.SetOutput(io.Discard)
		arq := fs.String("arquivo", "", "")
		if e := fs.Parse(opts); e != nil {
			return e
		}
		if *arq == "" {
			return errors.New("informe --arquivo experimento.json")
		}
		p, err := security.ConfinePath(a.Root, *arq)
		if err != nil {
			return err
		}
		b, err := os.ReadFile(p)
		if err != nil {
			return err
		}
		var e experiments.Experiment
		if err := json.Unmarshal(b, &e); err != nil {
			return fmt.Errorf("JSON inválido: %w", err)
		}
		cl, err := experiments.Classify(e, experiments.EnabledLevels(a.cfg.EnabledLevels))
		if err != nil {
			return err
		}
		if err := experiments.Save(db, e, experiments.EnabledLevels(a.cfg.EnabledLevels)); err != nil {
			return err
		}
		a.printf("Experimento %s registrado (nível %s: %s; evidência: %s).\n", e.ID, cl.Level, cl.LevelDesc, cl.EvidenceState)
		for _, n := range cl.Notes {
			a.printf("  nota: %s\n", n)
		}
		return nil
	}
	return fmt.Errorf("use: hrail experiment list | registrar")
}

func (a *App) cmdBanco(sub string, opts []string) error {
	if sub != "exportar" {
		return fmt.Errorf("use: hrail banco exportar --formato json|csv [--tabela T] --saida ARQ")
	}
	fs := flag.NewFlagSet("banco exportar", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	formato := fs.String("formato", "json", "")
	tabela := fs.String("tabela", "", "")
	saida := fs.String("saida", "", "")
	if err := fs.Parse(opts); err != nil {
		return err
	}
	db, err := a.openDB()
	if err != nil {
		return err
	}
	var w io.Writer = a.Out
	if *saida != "" {
		p, err := security.ConfinePath(a.Root, *saida)
		if err != nil {
			return err
		}
		os.MkdirAll(filepath.Dir(p), 0o755)
		f, err := os.Create(p)
		if err != nil {
			return err
		}
		defer f.Close()
		w = f
		defer a.printf("Exportado para %s\n", p)
	}
	switch *formato {
	case "json":
		return db.ExportJSON(w)
	case "csv":
		if *tabela == "" {
			return fmt.Errorf("CSV exige --tabela (%s)", strings.Join(storage.ExportTables, ", "))
		}
		return db.ExportCSV(*tabela, w)
	}
	return fmt.Errorf("formato %q inválido", *formato)
}

func (a *App) cmdReport(sub string) error {
	if sub != "generate" {
		return fmt.Errorf("use: hrail report generate")
	}
	db, err := a.openDB()
	if err != nil {
		return err
	}
	reg := a.registry()
	srcs, err := research.ParseCatalog(catalog.SourcesJSON)
	if err != nil {
		return err
	}
	es, err := experiments.List(db)
	if err != nil {
		return err
	}
	rs, err := benchmark.ListResults(db, "")
	if err != nil {
		return err
	}
	inv := a.collector().Collect(a.ctx)
	checks := reg.CheckAll(a.ctx)
	d := report.Data{
		GeneratedAt: time.Now().UTC().Format(time.RFC3339), Version: Version, Phase: "0 — Fundação e diagnóstico",
		Hardware: inv, Tools: checks, Sources: srcs, Experiments: es, Results: rs,
		Commands: a.runner.Records(), Limitations: report.Limitations,
	}
	dir, err := security.ConfinePath(a.Root, a.cfg.ReportsDir)
	if err != nil {
		return err
	}
	if err := os.MkdirAll(dir, 0o755); err != nil {
		return err
	}
	stamp := time.Now().UTC().Format("20060102_150405")
	md := filepath.Join(dir, "relatorio_"+stamp+".md")
	js := filepath.Join(dir, "relatorio_"+stamp+".json")
	if err := os.WriteFile(md, []byte(report.Markdown(d)), 0o644); err != nil {
		return err
	}
	jb, _ := json.MarshalIndent(d, "", "  ")
	if err := os.WriteFile(js, append(jb, '\n'), 0o644); err != nil {
		return err
	}
	_ = tools.Save(db, checks)
	a.printf("Relatório gerado:\n  %s\n  %s\n", md, js)
	return nil
}
