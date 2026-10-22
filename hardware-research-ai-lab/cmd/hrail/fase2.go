package main

import (
	"errors"
	"strings"
	"time"

	"hrail/catalog"
	"hrail/internal/benchmark"
	"hrail/internal/experiments"
	"hrail/internal/simulation"
)

func (a *App) cmdSimulation(sub string, opts []string) error {
	switch sub {
	case "", "info":
		return a.cmdSimulationInfo()
	case "preparar", "revisar", "aprovar", "compilar", "rodar", "resultados":
		return a.cmdMGPUSim(sub, opts)
	}
	return errors.New("use: hrail simulation info | preparar | revisar | aprovar | compilar | rodar | resultados")
}

func (a *App) mgpusimManager() (*simulation.Manager, error) {
	defs, err := simulation.ParseSimulators(catalog.SimulatorsJSON)
	if err != nil {
		return nil, err
	}
	var def *simulation.SimDef
	for i := range defs {
		if defs[i].ID == "mgpusim" {
			def = &defs[i]
		}
	}
	if def == nil {
		return nil, errors.New("mgpusim ausente de catalog/simulators.json")
	}
	db, err := a.openDB()
	if err != nil {
		return nil, err
	}
	if a.runner.Allow != nil {
		a.runner.Allow["unshare"] = true // usado só para isolar a rede do simulador
	}
	return &simulation.Manager{Root: a.Root, Def: *def, Runner: a.runner, DB: db}, nil
}

func (a *App) cmdMGPUSim(sub string, opts []string) error {
	fs := newFlags("simulation " + sub)
	amostra := fs.String("amostra", "fir", "")
	commit := fs.String("commit", "", "")
	por := fs.String("por", "", "")
	autorizo := fs.Bool("autorizo-codigo-terceiros", false, "")
	length := fs.Int("length", 0, "")
	taps := fs.Int("taps", 0, "")
	rep := fs.Int("repeticoes", 1, "")
	to := fs.Duration("timeout", 2*time.Minute, "")
	semIso := fs.Bool("permitir-sem-isolamento", false, "")
	if err := fs.Parse(opts); err != nil {
		return err
	}
	if sub == "resultados" {
		return a.mgpusimResultados()
	}
	m, err := a.mgpusimManager()
	if err != nil {
		return err
	}
	switch sub {
	case "preparar":
		msg, err := m.Prepare(a.ctx)
		if err != nil {
			return err
		}
		a.printf("%s\nCommit fixado: %s\n", msg, m.Def.PinnedCommit)
		return nil
	case "revisar":
		if _, err := m.Prepare(a.ctx); err != nil {
			return err
		}
		rv, err := m.Review(a.ctx, *amostra)
		if err != nil {
			return err
		}
		a.printf("Revisão AUTOMATIZADA de %s/%s @ %s\n  toolchain: %s | pacotes de terceiros: %d | módulos: %d\n  impressão digital: %s\n", rv.Simulator, rv.Sample, rv.Commit[:12], rv.Toolchain, rv.Packages, len(rv.Modules), rv.Fingerprint)
		if len(rv.Replaces) > 0 {
			a.printf("  ATENÇÃO: diretivas replace em go.mod: %s\n", strings.Join(rv.Replaces, "; "))
		}
		a.printf("  pacotes com imports sensíveis (os/exec, net, net/http, plugin, unsafe, syscall, cgo):\n")
		for _, r := range rv.Risky {
			a.printf("    - %s %v%s\n", r.Package, r.Imports, map[bool]string{true: " [CGO]", false: ""}[r.CGO])
		}
		a.printf("  achados da revisão manual:\n")
		for _, n := range rv.ManualNotes {
			a.printf("    * %s\n", n)
		}
		for _, l := range rv.Limitations {
			a.printf("  limite: %s\n", l)
		}
		a.printf("\nPara autorizar compilar/rodar ESTA versão: hrail simulation aprovar --amostra %s --commit %s --por \"seu nome\"\n", *amostra, rv.Commit)
		return nil
	case "aprovar":
		rv, err := m.LoadReview(*amostra)
		if err != nil {
			return err
		}
		if err := m.Approve(*amostra, *commit, *por); err != nil {
			return err
		}
		a.printf("Aprovado por %q: %s/%s @ %s (impressão digital %s...). Qualquer mudança de commit/go.mod/go.sum exige nova revisão.\n", *por, rv.Simulator, rv.Sample, rv.Commit[:12], rv.Fingerprint[:12])
		return nil
	case "compilar":
		if !*autorizo {
			return errors.New("compilar baixa dependências Go e prepara código de terceiros: confirme com --autorizo-codigo-terceiros")
		}
		b, err := m.Build(a.ctx, *amostra)
		if err != nil {
			return err
		}
		a.printf("Compilado com %s em %dms\n  binário: %s\n  sha256: %s\n", b.Toolchain, b.DurationMS, b.BinaryPath, b.SHA256)
		return nil
	case "rodar":
		if !*autorizo {
			return errors.New("rodar executa código de terceiros (em sandbox): confirme com --autorizo-codigo-terceiros")
		}
		vals := map[string]int{}
		if *length > 0 {
			vals["length"] = *length
		}
		if *taps > 0 {
			vals["taps"] = *taps
		}
		recs, err := m.Run(a.ctx, *amostra, simulation.RunParams{Values: vals, Timeout: *to, Repetitions: *rep, AllowNoIsolation: *semIso},
			experiments.EnabledLevels(a.cfg.EnabledLevels))
		for _, r := range recs {
			a.printf("\nExecução #%d (%s) — %dms, código %d%s\n  sandbox: rede isolada=%v, ambiente limpo=%v, timeout=%ds\n  args: %s\n  verificado pelo próprio simulador (-verify): %v\n",
				r.RunID, r.Sample, r.DurationMS, r.ExitCode, map[bool]string{true: " TIMEOUT", false: ""}[r.TimedOut], r.Sandbox.NetworkIsolated,
				r.Sandbox.CleanEnv, r.Sandbox.TimeoutSeconds, strings.Join(r.Args, " "), r.Verified)
			for _, k := range sortedKeys(r.Metrics) {
				a.printf("  %-24s %.6g\n", k, r.Metrics[k])
			}
			if r.Note != "" {
				a.printf("  nota: %s\n", r.Note)
			}
		}
		if len(recs) > 1 {
			a.printf("\nReprodutibilidade (kernel_time presente e idêntico em %d execuções): %v\n", len(recs), simulation.Deterministic(recs))
		}
		if len(recs) > 0 {
			a.printf("\nOrigem dos resultados: SIMULADO (modelo %s/%s). NÃO é medição da RX 580.\n", m.Def.Model.Arch, m.Def.Model.GPU)
		}
		return err
	}
	return nil
}

func sortedKeys(m map[string]float64) []string {
	var k []string
	for x := range m {
		k = append(k, x)
	}
	for i := range k {
		for j := i + 1; j < len(k); j++ {
			if k[j] < k[i] {
				k[i], k[j] = k[j], k[i]
			}
		}
	}
	return k
}

func (a *App) mgpusimResultados() error {
	db, err := a.openDB()
	if err != nil {
		return err
	}
	rs, err := benchmark.ListResults(db, "")
	if err != nil {
		return err
	}
	n := 0
	for _, r := range rs {
		if r.Origin == benchmark.Simulated {
			a.printf("%s  #%d  %-24s %-22.6g %s  [%s]\n", r.RecordedAt, r.ID, r.Metric, r.Value, r.Unit, r.ExperimentID)
			n++
		}
	}
	if n == 0 {
		a.printf("Nenhum resultado simulado gravado.\n")
	}
	return nil
}
