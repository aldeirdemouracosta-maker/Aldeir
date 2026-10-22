package simulation

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	_ "modernc.org/sqlite"

	"hrail/internal/benchmark"
	"hrail/internal/experiments"
	"hrail/internal/security"
	"hrail/internal/storage"
)

func specNet(dir string, env []string, to time.Duration) security.Spec {
	return security.Spec{Timeout: to, Dir: dir, Env: env}
}

// Build compila a amostra (precisa de aprovação). O download de módulos ocorre aqui, verificado por go.sum.
func (m *Manager) Build(ctx context.Context, sample string) (BuildRecord, error) {
	if _, err := m.requireApproval(sample); err != nil {
		return BuildRecord{}, err
	}
	fp, _ := m.Fingerprint(sample)
	env, err := m.goEnv()
	if err != nil {
		return BuildRecord{}, err
	}
	tc, _ := m.toolchain()
	if err := os.MkdirAll(m.bin(), 0o755); err != nil {
		return BuildRecord{}, err
	}
	out := filepath.Join(m.bin(), sample)
	start := time.Now()
	res, err := m.Runner.RunSpec(ctx, specNet(m.src(), env, 15*time.Minute), "go", "build", "-trimpath", "-o", out, m.Def.Samples[sample].Package)
	if err != nil || res.ExitCode != 0 {
		return BuildRecord{}, fmt.Errorf("go build falhou: %v %s", err, tail(res.Stderr))
	}
	sum, err := fileSHA(out)
	if err != nil {
		return BuildRecord{}, err
	}
	b := BuildRecord{Simulator: m.Def.ID, Sample: sample, Commit: m.Def.PinnedCommit, Fingerprint: fp, Toolchain: tc,
		BinaryPath: out, SHA256: sum, BuiltAt: storage.Now(), DurationMS: time.Since(start).Milliseconds()}
	_, err = m.DB.SQL().Exec(`INSERT INTO simulation_builds(simulator,sample,commit_hash,fingerprint,toolchain,binary_path,binary_sha256,built_at,duration_ms) VALUES(?,?,?,?,?,?,?,?,?)`,
		b.Simulator, b.Sample, b.Commit, b.Fingerprint, b.Toolchain, b.BinaryPath, b.SHA256, b.BuiltAt, b.DurationMS)
	return b, err
}

// BuildRecord descreve um binário compilado.
type BuildRecord struct {
	Simulator   string `json:"simulator"`
	Sample      string `json:"sample"`
	Commit      string `json:"commit"`
	Fingerprint string `json:"fingerprint"`
	Toolchain   string `json:"toolchain"`
	BinaryPath  string `json:"binary_path"`
	SHA256      string `json:"binary_sha256"`
	BuiltAt     string `json:"built_at"`
	DurationMS  int64  `json:"duration_ms"`
}

func fileSHA(p string) (string, error) {
	f, err := os.Open(p)
	if err != nil {
		return "", err
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return "", err
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

func (m *Manager) latestBuild(sample, fp string) (BuildRecord, error) {
	var b BuildRecord
	err := m.DB.SQL().QueryRow(`SELECT simulator,sample,commit_hash,fingerprint,toolchain,binary_path,binary_sha256,built_at,duration_ms
		FROM simulation_builds WHERE simulator=? AND sample=? AND fingerprint=? ORDER BY id DESC LIMIT 1`, m.Def.ID, sample, fp).
		Scan(&b.Simulator, &b.Sample, &b.Commit, &b.Fingerprint, &b.Toolchain, &b.BinaryPath, &b.SHA256, &b.BuiltAt, &b.DurationMS)
	if err == sql.ErrNoRows {
		return b, ErrSemBuild
	}
	return b, err
}

// RunParams controla uma execução.
type RunParams struct {
	Values           map[string]int // ex.: length, taps (0/ausente = padrão)
	Timeout          time.Duration
	Repetitions      int
	AllowNoIsolation bool
}

// Sandbox descreve as barreiras aplicadas.
type Sandbox struct {
	NetworkIsolated bool   `json:"network_isolated"`
	CleanEnv        bool   `json:"clean_env"`
	Cwd             string `json:"cwd"`
	TimeoutSeconds  int    `json:"timeout_seconds"`
	Wrapper         string `json:"wrapper,omitempty"`
}

// RunRecord é o resultado de uma execução simulada.
type RunRecord struct {
	RunID        int64              `json:"run_id"`
	Sample       string             `json:"sample"`
	Args         []string           `json:"args"`
	Sandbox      Sandbox            `json:"sandbox"`
	ExitCode     int                `json:"exit_code"`
	TimedOut     bool               `json:"timed_out"`
	Verified     bool               `json:"verified_by_simulator"`
	DurationMS   int64              `json:"duration_ms"`
	Metrics      map[string]float64 `json:"metrics"`
	ExperimentID string             `json:"experiment_id"`
	Note         string             `json:"note,omitempty"`
}

// BuildArgs monta os argumentos a partir de valores validados. Nunca aceita flags livres.
func (m *Manager) BuildArgs(sample string, vals map[string]int) ([]string, error) {
	sd, ok := m.Def.Samples[sample]
	if !ok {
		return nil, fmt.Errorf("amostra %q não permitida", sample)
	}
	for k := range vals {
		if _, ok := sd.Flags[k]; !ok {
			return nil, fmt.Errorf("parâmetro %q não permitido para %s", k, sample)
		}
	}
	args := append([]string{}, m.Def.FixedFlags...)
	names := make([]string, 0, len(sd.Flags))
	for k := range sd.Flags {
		names = append(names, k)
	}
	sort.Strings(names)
	for _, k := range names {
		fd := sd.Flags[k]
		v := fd.Default
		if x, ok := vals[k]; ok && x != 0 {
			v = x
		}
		if v < 1 || v > fd.Max {
			return nil, fmt.Errorf("%s=%d fora do limite permitido (1..%d)", k, v, fd.Max)
		}
		args = append(args, "-"+k, fmt.Sprint(v))
	}
	return args, nil
}

func (m *Manager) isolated(ctx context.Context) bool {
	res, err := m.Runner.Run(ctx, "unshare", "-n", "--", "/bin/true")
	return err == nil && res.ExitCode == 0
}

// SimExperimentID é o experimento que agrupa as execuções de uma amostra.
func SimExperimentID(def SimDef, sample string) string {
	return "SIM-" + strings.ToUpper(def.ID) + "-" + strings.ToUpper(sample)
}

func (m *Manager) ensureExperiment(sample string, enabled []experiments.Level) (string, error) {
	id := SimExperimentID(m.Def, sample)
	if _, err := experiments.Get(m.DB, id); err == nil {
		return id, nil
	}
	e := experiments.Experiment{
		ID: id, Description: fmt.Sprintf("Execução da amostra %q do %s (%s/%s, commit %s) para validar a integração. NÃO representa a RX 580.",
			sample, m.Def.ID, m.Def.Model.Arch, m.Def.Model.GPU, m.Def.PinnedCommit[:12]),
		HypothesisSource: "integração Fase 2", ApplicableHardware: []string{"modelo " + m.Def.Model.GPU + " (simulado)"},
		Prerequisites: []string{"revisão e aprovação humana", "binário compilado e verificado"}, PotentialImpact: "nenhum (validação de integração)",
		OperationalRisk: "baixo", Reversibility: "total", Confidence: "baixa", Level: experiments.LevelB,
		Kind: "simulation_integration", Origin: benchmark.Simulated, InfrastructureTest: true,
	}
	return id, experiments.Save(m.DB, e, enabled)
}

// Run executa a amostra no sandbox, extrai métricas e grava resultados com origin=simulated.
func (m *Manager) Run(ctx context.Context, sample string, p RunParams, enabled []experiments.Level) ([]RunRecord, error) {
	if _, err := m.requireApproval(sample); err != nil {
		return nil, err
	}
	fp, _ := m.Fingerprint(sample)
	b, err := m.latestBuild(sample, fp)
	if err != nil {
		return nil, err
	}
	sum, err := fileSHA(b.BinaryPath)
	if err != nil || sum != b.SHA256 {
		return nil, fmt.Errorf("binário ausente ou alterado desde a compilação (sha256 difere); recompile")
	}
	args, err := m.BuildArgs(sample, p.Values)
	if err != nil {
		return nil, err
	}
	if p.Timeout <= 0 {
		p.Timeout = 2 * time.Minute
	}
	if p.Timeout > 10*time.Minute {
		return nil, fmt.Errorf("timeout acima do limite de 10 minutos")
	}
	if p.Repetitions <= 0 {
		p.Repetitions = 1
	}
	if p.Repetitions > 5 {
		return nil, fmt.Errorf("no máximo 5 repetições")
	}
	iso := m.isolated(ctx)
	if !iso && !p.AllowNoIsolation {
		return nil, fmt.Errorf("isolamento de rede (unshare -n) indisponível; use --permitir-sem-isolamento para prosseguir ciente do risco")
	}
	expID, err := m.ensureExperiment(sample, enabled)
	if err != nil {
		return nil, err
	}
	var out []RunRecord
	for i := 0; i < p.Repetitions; i++ {
		rec, err := m.runOnce(ctx, sample, b, args, iso, p, expID)
		if err != nil {
			return out, err
		}
		out = append(out, rec)
	}
	return out, nil
}

func (m *Manager) runOnce(ctx context.Context, sample string, b BuildRecord, args []string, iso bool, p RunParams, expID string) (RunRecord, error) {
	runDir := filepath.Join(m.base(), "run", fmt.Sprintf("%s-%d", sample, time.Now().UnixNano()))
	if err := os.MkdirAll(runDir, 0o755); err != nil {
		return RunRecord{}, err
	}
	sb := Sandbox{NetworkIsolated: iso, CleanEnv: true, Cwd: runDir, TimeoutSeconds: int(p.Timeout.Seconds())}
	name, full := b.BinaryPath, args
	if iso {
		sb.Wrapper = "unshare -n"
		name, full = "unshare", append([]string{"-n", "--", b.BinaryPath}, args...)
	} else {
		if m.Runner.AllowPaths == nil {
			m.Runner.AllowPaths = map[string]bool{}
		}
		m.Runner.AllowPaths[b.BinaryPath] = true
	}
	start := time.Now()
	res, err := m.Runner.RunSpec(ctx, security.Spec{Timeout: p.Timeout, Dir: runDir, CleanEnv: true,
		Env: []string{"PATH=/usr/bin:/bin", "HOME=" + runDir}}, name, full...)
	rec := RunRecord{Sample: sample, Args: args, Sandbox: sb, ExitCode: res.ExitCode, TimedOut: res.TimedOut,
		DurationMS: time.Since(start).Milliseconds(), ExperimentID: expID, Metrics: map[string]float64{}}
	if err != nil && !res.TimedOut {
		rec.Note = err.Error()
	}
	rec.Verified = strings.Contains(res.Stderr+res.Stdout, "Passed!")
	if res.ExitCode == 0 && !res.TimedOut {
		met, merr := ExtractMetrics(runDir)
		if merr != nil {
			rec.Note = "métricas não extraídas: " + merr.Error()
		}
		rec.Metrics = met
	} else if rec.Note == "" {
		rec.Note = fmt.Sprintf("execução sem sucesso (código %d, timeout=%v): %s", res.ExitCode, res.TimedOut, tail(res.Stderr))
	}
	ab, _ := json.Marshal(args)
	sj, _ := json.Marshal(sb)
	r, err := m.DB.SQL().Exec(`INSERT INTO simulation_runs(simulator,sample,commit_hash,binary_sha256,args_json,sandbox_json,started_at,duration_ms,exit_code,timed_out,verified,experiment_id,note)
		VALUES(?,?,?,?,?,?,?,?,?,?,?,?,NULLIF(?,''))`, m.Def.ID, sample, m.Def.PinnedCommit, b.SHA256, string(ab), string(sj),
		start.UTC().Format(time.RFC3339), rec.DurationMS, rec.ExitCode, b2i(rec.TimedOut), b2i(rec.Verified), expID, rec.Note)
	if err != nil {
		return rec, err
	}
	rec.RunID, _ = r.LastInsertId()
	if len(rec.Metrics) > 0 {
		keys := make([]string, 0, len(rec.Metrics))
		for k := range rec.Metrics {
			keys = append(keys, k)
		}
		sort.Strings(keys)
		for _, k := range keys {
			res := benchmark.Result{ExperimentID: expID, Origin: benchmark.Simulated, Metric: k, Value: rec.Metrics[k], Unit: metricUnit(k),
				Params: map[string]any{"sample": sample, "args": args, "commit": m.Def.PinnedCommit, "binary_sha256": b.SHA256,
					"model": m.Def.Model.Arch + "/" + m.Def.Model.GPU, "run_id": rec.RunID, "verified_by_simulator": rec.Verified},
				InfrastructureTest: true, Note: "Resultado SIMULADO (modelo " + m.Def.Model.GPU + "); não é medição da RX 580."}
			if err := benchmark.Save(m.DB, res); err != nil {
				return rec, err
			}
		}
	}
	return rec, nil
}

func b2i(b bool) int {
	if b {
		return 1
	}
	return 0
}

func metricUnit(k string) string {
	switch k {
	case "kernel_time":
		return "s (simulado)"
	case "cu_cpi_mean_active", "simd_cpi_mean_active":
		return "ciclos/instrução"
	default:
		return "contagem"
	}
}

// ExtractMetrics lê o SQLite gerado pelo simulador (somente leitura) e agrega métricas.
func ExtractMetrics(dir string) (map[string]float64, error) {
	files, _ := filepath.Glob(filepath.Join(dir, "akita_sim_*.sqlite3"))
	if len(files) != 1 {
		return nil, fmt.Errorf("esperava 1 arquivo de métricas, encontrei %d", len(files))
	}
	db, err := sql.Open("sqlite", "file:"+files[0]+"?mode=ro&immutable=1")
	if err != nil {
		return nil, err
	}
	defer db.Close()
	rows, err := db.Query(`SELECT Location, What, Value FROM mgpusim_metrics`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var kt, cuInst, simdInst, cuCPI, simdCPI float64
	var active, cpiN, simdN int
	haveKT := false
	for rows.Next() {
		var loc, what string
		var nv sql.NullFloat64
		if err := rows.Scan(&loc, &what, &nv); err != nil {
			return nil, err
		}
		// NULL/Inf/NaN (ex.: CPI de CU ociosa) não são medidas: ignorados, nunca zerados.
		if !nv.Valid || math.IsInf(nv.Float64, 0) || math.IsNaN(nv.Float64) {
			continue
		}
		v := nv.Float64
		switch what {
		case "kernel_time":
			if loc == "Driver" {
				kt += v
				haveKT = true
			}
		case "cu_inst_count":
			cuInst += v
			if v > 0 {
				active++
			}
		case "simd_inst_count":
			simdInst += v
		case "cu_CPI":
			if v > 0 {
				cuCPI += v
				cpiN++
			}
		case "simd_CPI":
			if v > 0 {
				simdCPI += v
				simdN++
			}
		}
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	if !haveKT {
		return nil, fmt.Errorf("tabela sem kernel_time do Driver")
	}
	m := map[string]float64{"kernel_time": kt, "cu_inst_count_total": cuInst, "simd_inst_count_total": simdInst, "active_cus": float64(active)}
	if cpiN > 0 {
		m["cu_cpi_mean_active"] = cuCPI / float64(cpiN)
	}
	if simdN > 0 {
		m["simd_cpi_mean_active"] = simdCPI / float64(simdN)
	}
	return m, nil
}

// Deterministic informa se TODAS as execuções têm kernel_time e ele é idêntico.
// Sem métricas não há como afirmar reprodutibilidade: devolve false.
func Deterministic(recs []RunRecord) bool {
	if len(recs) < 2 {
		return false
	}
	first, ok := recs[0].Metrics["kernel_time"]
	if !ok {
		return false
	}
	for _, r := range recs[1:] {
		v, ok := r.Metrics["kernel_time"]
		if !ok || v != first {
			return false
		}
	}
	return true
}
