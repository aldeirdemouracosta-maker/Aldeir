package simulation

import (
	"archive/tar"
	"context"
	"database/sql"
	"errors"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"hrail/catalog"
	"hrail/internal/benchmark"
	"hrail/internal/experiments"
	"hrail/internal/security"
	"hrail/internal/storage"
)

var ab = []experiments.Level{"A", "B"}

func testDef() SimDef {
	return SimDef{ID: "simx", SourceID: "simx", PinnedCommit: strings.Repeat("a", 40),
		Model:      ModelDef{Arch: "gcn3", GPU: "r9nano"},
		FixedFlags: []string{"-timing", "-disable-rtm", "-verify"},
		Samples:    map[string]SampleDef{"fir": {Package: "./amd/samples/fir", Flags: map[string]FlagDef{"length": {1024, 65536}, "taps": {16, 256}}}}}
}

func newMgr(t *testing.T) *Manager {
	t.Helper()
	root := t.TempDir()
	db, err := storage.Open(filepath.Join(root, "data", "t.db"))
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { db.Close() })
	m := &Manager{Root: root, Def: testDef(), Runner: security.NewRunner(30*time.Second, "git", "go", "unshare"), DB: db}
	os.MkdirAll(m.src(), 0o755)
	os.WriteFile(filepath.Join(m.src(), "go.mod"), []byte("module x\n\ngo 1.27.0\n"), 0o644)
	os.WriteFile(filepath.Join(m.src(), "go.sum"), []byte("h1\n"), 0o644)
	return m
}

func TestCatalogoDeSimuladoresEmbutido(t *testing.T) {
	defs, err := ParseSimulators(catalog.SimulatorsJSON)
	if err != nil || len(defs) != 1 {
		t.Fatalf("%v %d", err, len(defs))
	}
	d := defs[0]
	if d.ID != "mgpusim" || len(d.PinnedCommit) != 40 || d.Model.GPU != "r9nano" || !strings.Contains(d.Model.Note, "NÃO é Polaris") {
		t.Errorf("%+v", d)
	}
	if _, ok := d.Samples["fir"]; !ok || len(d.ManualReview) < 3 {
		t.Error("amostra fir e revisão manual devem estar registradas")
	}
}

func TestCatalogoRecusaConfiguracoesPerigosas(t *testing.T) {
	ok := `{"simulators":[{"id":"s","pinned_commit":"` + strings.Repeat("b", 40) + `","fixed_flags":["-disable-rtm"],"samples":{"f":{"package":"./amd/samples/f","flags":{"length":{"default":1,"max":9}}}}}]}`
	if _, err := ParseSimulators([]byte(ok)); err != nil {
		t.Fatal(err)
	}
	bad := map[string]string{
		"commit curto":  strings.Replace(ok, strings.Repeat("b", 40), "abc", 1),
		"sem rtm":       strings.Replace(ok, `"-disable-rtm"`, `"-timing"`, 1),
		"flag trace":    strings.Replace(ok, `"-disable-rtm"`, `"-disable-rtm","-trace-vis"`, 1),
		"pacote fora":   strings.Replace(ok, "./amd/samples/f", "./cmd/evil", 1),
		"flag proibida": strings.Replace(ok, `"length"`, `"trace-mem"`, 1),
		"default>max":   strings.Replace(ok, `"default":1`, `"default":99`, 1),
	}
	for n, js := range bad {
		if _, err := ParseSimulators([]byte(js)); err == nil {
			t.Errorf("%s: deveria falhar", n)
		}
	}
}

func TestBuildArgsSoAceitaParametrosValidados(t *testing.T) {
	m := &Manager{Def: testDef()}
	a, err := m.BuildArgs("fir", nil)
	if err != nil || strings.Join(a, " ") != "-timing -disable-rtm -verify -length 1024 -taps 16" {
		t.Fatalf("%v %v", a, err)
	}
	a, _ = m.BuildArgs("fir", map[string]int{"length": 2048})
	if !strings.Contains(strings.Join(a, " "), "-length 2048") {
		t.Errorf("%v", a)
	}
	for _, c := range []map[string]int{{"length": 99999999}, {"taps": 257}, {"trace-vis": 1}, {"length": -5}} {
		if _, err := m.BuildArgs("fir", c); err == nil {
			t.Errorf("%v deveria ser recusado", c)
		}
	}
	if _, err := m.BuildArgs("outra", nil); err == nil {
		t.Error("amostra fora do catálogo")
	}
}

func TestExtracaoDeTarRecusaTraversalEIgnoraLinks(t *testing.T) {
	mk := func(entries func(*tar.Writer)) string {
		p := filepath.Join(t.TempDir(), "a.tar")
		f, _ := os.Create(p)
		tw := tar.NewWriter(f)
		entries(tw)
		tw.Close()
		f.Close()
		return p
	}
	dest := t.TempDir()
	good := mk(func(tw *tar.Writer) {
		tw.WriteHeader(&tar.Header{Name: "d/", Typeflag: tar.TypeDir, Mode: 0o755})
		tw.WriteHeader(&tar.Header{Name: "d/a.txt", Typeflag: tar.TypeReg, Mode: 0o644, Size: 2})
		tw.Write([]byte("ok"))
		tw.WriteHeader(&tar.Header{Name: "d/link", Typeflag: tar.TypeSymlink, Linkname: "/etc/passwd"})
	})
	n, sk, err := extractTar(good, dest)
	if err != nil || n != 1 || sk != 1 {
		t.Fatalf("%d %d %v", n, sk, err)
	}
	if _, err := os.Lstat(filepath.Join(dest, "d", "link")); err == nil {
		t.Error("symlink não deve ser criado")
	}
	evil := mk(func(tw *tar.Writer) {
		tw.WriteHeader(&tar.Header{Name: "../fora.txt", Typeflag: tar.TypeReg, Mode: 0o644, Size: 1})
		tw.Write([]byte("x"))
	})
	if _, _, err := extractTar(evil, dest); err == nil {
		t.Fatal("path traversal deve ser recusado")
	}
	if _, err := os.Stat(filepath.Join(filepath.Dir(dest), "fora.txt")); err == nil {
		t.Fatal("arquivo escapou do destino")
	}
}

func TestPrepareDoCommitFixado(t *testing.T) {
	m := newMgr(t)
	os.RemoveAll(m.src())
	repo := m.clone()
	os.MkdirAll(repo, 0o755)
	g := func(a ...string) string {
		c := exec.Command("git", append([]string{"-C", repo}, a...)...)
		c.Env = append(os.Environ(), "GIT_AUTHOR_NAME=T", "GIT_AUTHOR_EMAIL=t@e.invalid", "GIT_COMMITTER_NAME=T", "GIT_COMMITTER_EMAIL=t@e.invalid")
		o, err := c.CombinedOutput()
		if err != nil {
			t.Fatalf("%v %s", err, o)
		}
		return strings.TrimSpace(string(o))
	}
	g("init", "-q", "-b", "main")
	os.WriteFile(filepath.Join(repo, "go.mod"), []byte("module x\n\ngo 1.27.0\n"), 0o644)
	g("add", ".")
	g("commit", "-q", "-m", "um")
	m.Def.PinnedCommit = g("rev-parse", "HEAD")
	msg, err := m.Prepare(context.Background())
	if err != nil || !strings.Contains(msg, "extraídos") {
		t.Fatalf("%s %v", msg, err)
	}
	if _, err := os.Stat(filepath.Join(m.src(), "go.mod")); err != nil {
		t.Error("go.mod não extraído")
	}
	if _, err := os.Stat(filepath.Join(m.src(), ".git")); err == nil {
		t.Error("não deve levar .git")
	}
	if msg, _ := m.Prepare(context.Background()); !strings.Contains(msg, "já preparado") {
		t.Errorf("idempotência: %s", msg)
	}
	m.Def.PinnedCommit = strings.Repeat("c", 40)
	os.Remove(m.marker())
	if _, err := m.Prepare(context.Background()); err == nil {
		t.Error("commit inexistente deve falhar")
	}
}

func TestParseDeps(t *testing.T) {
	out := "example.com/a :: fmt os/exec net/http :: 0 :: example.com/a@v1.0.0\nexample.com/b :: fmt :: 2 :: example.com/b@v2.0.0\nexample.com/c :: fmt strings :: 0 :: example.com/a@v1.0.0\nlixo\n"
	n, risky, mods := ParseDeps(out)
	if n != 3 || len(risky) != 2 || !risky[1].CGO || len(mods) != 2 || mods[0] != "example.com/a@v1.0.0" {
		t.Fatalf("%d %+v %v", n, risky, mods)
	}
	if len(risky[0].Imports) != 2 {
		t.Errorf("%+v", risky[0])
	}
}

func fakeReview(t *testing.T, m *Manager) Review {
	fp, err := m.Fingerprint("fir")
	if err != nil {
		t.Fatal(err)
	}
	r := Review{Simulator: m.Def.ID, Sample: "fir", Commit: m.Def.PinnedCommit, Fingerprint: fp, ReviewedAt: storage.Now()}
	if err := m.saveReview(r); err != nil {
		t.Fatal(err)
	}
	return r
}

func TestPortoesDeAprovacao(t *testing.T) {
	m := newMgr(t)
	ctx := context.Background()
	if _, err := m.Build(ctx, "fir"); err == nil || errors.Is(err, ErrNaoAprovado) {
		t.Errorf("sem revisão: erro esperado de revisão ausente, obteve %v", err)
	}
	fakeReview(t, m)
	if _, err := m.Build(ctx, "fir"); !errors.Is(err, ErrNaoAprovado) {
		t.Errorf("revisada mas não aprovada: %v", err)
	}
	if _, err := m.Run(ctx, "fir", RunParams{}, ab); !errors.Is(err, ErrNaoAprovado) {
		t.Errorf("run sem aprovação: %v", err)
	}
	if err := m.Approve("fir", m.Def.PinnedCommit, " "); err == nil {
		t.Error("aprovação exige nome")
	}
	if err := m.Approve("fir", strings.Repeat("d", 40), "alguém"); err == nil {
		t.Error("commit diferente do fixado não pode ser aprovado")
	}
	if err := m.Approve("fir", m.Def.PinnedCommit, "alguém"); err != nil {
		t.Fatal(err)
	}
	if _, err := m.Run(ctx, "fir", RunParams{}, ab); !errors.Is(err, ErrSemBuild) {
		t.Errorf("aprovado mas sem build: %v", err)
	}
	// mudar go.sum invalida a aprovação
	os.WriteFile(filepath.Join(m.src(), "go.sum"), []byte("h1\nh1 novo\n"), 0o644)
	if _, err := m.Build(ctx, "fir"); err == nil || !strings.Contains(err.Error(), "nenhuma revisão desta versão") {
		t.Errorf("mudança de go.sum deve exigir nova revisão: %v", err)
	}
}

// binário falso: Python que cria um SQLite de métricas no formato do simulador.
const fakeSim = `#!/usr/bin/env python3
import sqlite3, os, sys, time
if "SLEEP" in " ".join(sys.argv): pass
open("env.txt","w").write("\n".join(f"{k}={v}" for k,v in os.environ.items()))
open("args.txt","w").write(" ".join(sys.argv[1:]))
if os.path.exists("sleep.flag") or %s: time.sleep(30)
c = sqlite3.connect("akita_sim_x.sqlite3")
c.execute("create table mgpusim_metrics (Location text, What text, Value real, Unit text)")
rows = [("Driver","kernel_time",1.5e-05,"second"),("GPU[1].SA[0].CU[0]","cu_inst_count",100.0,"count"),("GPU[1].SA[0].CU[0]","cu_CPI",4.0,"c/i"),
        ("GPU[1].SA[1].CU[0]","cu_inst_count",0.0,"count"),("GPU[1].SA[1].CU[0]","cu_CPI",None,"c/i"),("GPU[1].SA[1].CU[1]","cu_CPI",float("inf"),"c/i")]
c.executemany("insert into mgpusim_metrics values (?,?,?,?)", rows); c.commit(); c.close()
sys.stderr.write("Passed!\n")
`

func armed(t *testing.T, sleep bool) *Manager {
	if _, err := exec.LookPath("python3"); err != nil {
		t.Skip("python3 ausente")
	}
	m := newMgr(t)
	fakeReview(t, m)
	if err := m.Approve("fir", m.Def.PinnedCommit, "teste"); err != nil {
		t.Fatal(err)
	}
	os.MkdirAll(m.bin(), 0o755)
	body := strings.Replace(fakeSim, "%s", map[bool]string{true: "True", false: "False"}[sleep], 1)
	bin := filepath.Join(m.bin(), "fir")
	os.WriteFile(bin, []byte(body), 0o755)
	sum, _ := fileSHA(bin)
	fp, _ := m.Fingerprint("fir")
	_, err := m.DB.SQL().Exec(`INSERT INTO simulation_builds(simulator,sample,commit_hash,fingerprint,toolchain,binary_path,binary_sha256,built_at,duration_ms) VALUES(?,?,?,?,?,?,?,?,?)`,
		m.Def.ID, "fir", m.Def.PinnedCommit, fp, "go1.27.0", bin, sum, storage.Now(), 1)
	if err != nil {
		t.Fatal(err)
	}
	return m
}

func TestExecucaoNoSandboxGravaResultadosSimulados(t *testing.T) {
	t.Setenv("SEGREDO_DO_USUARIO", "nao-vaze")
	m := armed(t, false)
	recs, err := m.Run(context.Background(), "fir", RunParams{Repetitions: 2, AllowNoIsolation: true, Timeout: 20 * time.Second, Values: map[string]int{"length": 2048}}, ab)
	if err != nil || len(recs) != 2 {
		t.Fatalf("%v %d", err, len(recs))
	}
	r := recs[0]
	if r.ExitCode != 0 || !r.Verified || r.Metrics["kernel_time"] != 1.5e-05 || r.Metrics["active_cus"] != 1 || r.Metrics["cu_cpi_mean_active"] != 4 {
		t.Fatalf("%+v", r)
	}
	if _, ok := r.Metrics["cu_cpi_mean_active"]; !ok || len(r.Metrics) != 5 {
		t.Errorf("métricas: %v", r.Metrics)
	}
	if !Deterministic(recs) {
		t.Error("duas execuções idênticas são determinísticas")
	}
	env, _ := os.ReadFile(filepath.Join(r.Sandbox.Cwd, "env.txt"))
	if strings.Contains(string(env), "SEGREDO_DO_USUARIO") || !strings.Contains(string(env), "HOME="+r.Sandbox.Cwd) {
		t.Errorf("ambiente deve ser limpo:\n%s", env)
	}
	args, _ := os.ReadFile(filepath.Join(r.Sandbox.Cwd, "args.txt"))
	if string(args) != "-timing -disable-rtm -verify -length 2048 -taps 16" {
		t.Errorf("args: %s", args)
	}
	// persistência: resultados SIMULADOS ligados ao experimento, que não permite alegar melhoria
	res, _ := benchmark.ListResults(m.DB, SimExperimentID(m.Def, "fir"))
	if len(res) != 10 {
		t.Fatalf("resultados=%d", len(res))
	}
	for _, x := range res {
		if x.Origin != benchmark.Simulated {
			t.Errorf("origem %s", x.Origin)
		}
	}
	e, err := experiments.Get(m.DB, SimExperimentID(m.Def, "fir"))
	if err != nil || !e.InfrastructureTest || e.Origin != "simulated" || !strings.Contains(e.Description, "NÃO representa a RX 580") {
		t.Errorf("%+v %v", e, err)
	}
	var runs, ver int
	m.DB.SQL().QueryRow(`SELECT COUNT(*), SUM(verified) FROM simulation_runs`).Scan(&runs, &ver)
	if runs != 2 || ver != 2 {
		t.Errorf("runs=%d verified=%d", runs, ver)
	}
	if err := benchmark.ClaimImprovement(toResults(res[:3]), toResults(res[3:6])); err == nil {
		t.Error("resultado simulado nunca sustenta alegação de melhoria")
	}
}

func toResults(ss []benchmark.Stored) []benchmark.Result {
	var out []benchmark.Result
	for _, s := range ss {
		out = append(out, benchmark.Result{Origin: s.Origin, Metric: s.Metric, Unit: s.Unit})
	}
	return out
}

func TestTimeoutNaoGravaMetricasEMataProcesso(t *testing.T) {
	m := armed(t, true)
	start := time.Now()
	recs, err := m.Run(context.Background(), "fir", RunParams{AllowNoIsolation: true, Timeout: 500 * time.Millisecond}, ab)
	if err != nil || len(recs) != 1 {
		t.Fatalf("%v", err)
	}
	if !recs[0].TimedOut || len(recs[0].Metrics) != 0 || time.Since(start) > 10*time.Second {
		t.Errorf("%+v", recs[0])
	}
	var n int
	m.DB.SQL().QueryRow(`SELECT COUNT(*) FROM results`).Scan(&n)
	if n != 0 {
		t.Errorf("timeout não pode gerar resultados (%d)", n)
	}
}

func TestBinarioAdulteradoEhRecusado(t *testing.T) {
	m := armed(t, false)
	bin := filepath.Join(m.bin(), "fir")
	os.WriteFile(bin, []byte("#!/bin/sh\necho trocado\n"), 0o755)
	if _, err := m.Run(context.Background(), "fir", RunParams{AllowNoIsolation: true}, ab); err == nil || !strings.Contains(err.Error(), "alterado") {
		t.Fatalf("binário modificado deve ser recusado: %v", err)
	}
}

func TestLimitesDeExecucao(t *testing.T) {
	m := armed(t, false)
	ctx := context.Background()
	if _, err := m.Run(ctx, "fir", RunParams{Timeout: time.Hour, AllowNoIsolation: true}, ab); err == nil {
		t.Error("timeout > 10min")
	}
	if _, err := m.Run(ctx, "fir", RunParams{Repetitions: 6, AllowNoIsolation: true}, ab); err == nil {
		t.Error("repetições > 5")
	}
	if _, err := m.Run(ctx, "fir", RunParams{Values: map[string]int{"length": 1 << 30}, AllowNoIsolation: true}, ab); err == nil {
		t.Error("length acima do máximo")
	}
}

func TestReprodutibilidadeNaoPodeSerAfirmadaSemMetricas(t *testing.T) {
	// regressão: antes, 0 == 0 virava "reprodutível: true" quando nenhuma métrica era extraída
	sem := []RunRecord{{Metrics: map[string]float64{}}, {Metrics: map[string]float64{}}}
	if Deterministic(sem) {
		t.Fatal("sem kernel_time não há como afirmar reprodutibilidade")
	}
	a := RunRecord{Metrics: map[string]float64{"kernel_time": 1}}
	b := RunRecord{Metrics: map[string]float64{"kernel_time": 2}}
	if Deterministic([]RunRecord{a, b}) || Deterministic([]RunRecord{a}) || !Deterministic([]RunRecord{a, a}) {
		t.Error("lógica de determinismo")
	}
}

func TestExtractMetricsErros(t *testing.T) {
	if _, err := ExtractMetrics(t.TempDir()); err == nil {
		t.Error("sem arquivo de métricas")
	}
	d := t.TempDir()
	db, _ := sql.Open("sqlite", filepath.Join(d, "akita_sim_y.sqlite3"))
	db.Exec(`create table mgpusim_metrics (Location text, What text, Value real, Unit text)`)
	db.Exec(`insert into mgpusim_metrics values ('GPU','cu_inst_count',5,'count')`)
	db.Close()
	if _, err := ExtractMetrics(d); err == nil || !strings.Contains(err.Error(), "kernel_time") {
		t.Errorf("sem kernel_time do Driver: %v", err)
	}
}
