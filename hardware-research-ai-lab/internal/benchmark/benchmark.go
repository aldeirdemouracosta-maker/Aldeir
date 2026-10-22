// Package benchmark implementa o benchmark-engine: experimentos reproduzíveis
// com origem explícita (medido, simulado, estimado ou fixture).
package benchmark

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"

	"hrail/internal/experiments"
	"hrail/internal/storage"
)

// Origens de um resultado. Resultados de origens diferentes NUNCA são misturados.
const (
	Measured  = "measured"
	Simulated = "simulated"
	Estimated = "estimated"
	Fixture   = "fixture"
)

// SelfTestID identifica o teste de infraestrutura.
const SelfTestID = "INFRA-SELFTEST-CPU"

// Result é uma medida registrada.
type Result struct {
	ExperimentID       string         `json:"experiment_id"`
	Origin             string         `json:"origin"`
	Metric             string         `json:"metric"`
	Value              float64        `json:"value"`
	Unit               string         `json:"unit"`
	Params             map[string]any `json:"params"`
	Meta               Meta           `json:"meta"`
	InfrastructureTest bool           `json:"infrastructure_test"`
	Note               string         `json:"note,omitempty"`
	HardwareSnapshotID int64          `json:"hardware_snapshot_id,omitempty"`
}

// Meta reúne metadados do ambiente da medição.
type Meta struct {
	Time         string   `json:"time"`
	GoVersion    string   `json:"go_version"`
	GOOS         string   `json:"goos"`
	GOARCH       string   `json:"goarch"`
	LogicalCPUs  int      `json:"logical_cpus"`
	GPU          string   `json:"gpu,omitempty"`
	Driver       string   `json:"driver,omitempty"`
	TempCelsius  *float64 `json:"temp_celsius,omitempty"` // nil = indisponível
	TempSource   string   `json:"temp_source,omitempty"`
	HRAILVersion string   `json:"hrail_version"`
}

// Options controla o autoteste.
type Options struct {
	Iterations int
	Seed       string
	SysRoot    string // "/" em produção
	GPU, Drv   string
	Version    string
}

// SelfTest roda uma cadeia SHA-256 determinística. É um teste da INFRAESTRUTURA do
// laboratório: não mede a capacidade de nenhum componente de forma comparável.
func SelfTest(ctx context.Context, o Options) (Result, error) {
	if o.Iterations <= 0 {
		o.Iterations = 200_000
	}
	if o.Seed == "" {
		o.Seed = "hrail-fase0"
	}
	if o.SysRoot == "" {
		o.SysRoot = "/"
	}
	sum := sha256.Sum256([]byte(o.Seed))
	start := time.Now()
	for i := 0; i < o.Iterations; i++ {
		if i&0x3fff == 0 {
			if err := ctx.Err(); err != nil {
				return Result{}, err
			}
		}
		sum = sha256.Sum256(sum[:])
	}
	el := time.Since(start)
	t, src := ReadTemperature(o.SysRoot)
	return Result{
		ExperimentID: SelfTestID, Origin: Measured, Metric: "sha256_chain_rate", Unit: "hashes/s",
		Value: float64(o.Iterations) / el.Seconds(),
		Params: map[string]any{"iterations": o.Iterations, "seed": o.Seed, "workload": "sha256-chain",
			"final_digest_prefix": fmt.Sprintf("%x", sum[:4]), "elapsed_ms": el.Milliseconds()},
		Meta: Meta{Time: start.UTC().Format(time.RFC3339), GoVersion: runtime.Version(), GOOS: runtime.GOOS, GOARCH: runtime.GOARCH,
			LogicalCPUs: runtime.NumCPU(), GPU: o.GPU, Driver: o.Drv, TempCelsius: t, TempSource: src, HRAILVersion: o.Version},
		InfrastructureTest: true,
		Note:               "TESTE DA INFRAESTRUTURA do HRAIL (pipeline de medição/registro). Não é benchmark de hardware e não deve ser usado para comparar componentes.",
	}, nil
}

// ReadTemperature lê a primeira temperatura disponível (hwmon amdgpu, depois thermal_zone).
func ReadTemperature(root string) (*float64, string) {
	pats := []string{"sys/class/hwmon/hwmon*/temp1_input", "sys/class/thermal/thermal_zone*/temp"}
	for _, p := range pats {
		m, _ := filepath.Glob(filepath.Join(root, p))
		for _, f := range m {
			b, err := os.ReadFile(f)
			if err != nil {
				continue
			}
			n, err := strconv.ParseFloat(strings.TrimSpace(string(b)), 64)
			if err != nil {
				continue
			}
			c := n / 1000
			return &c, strings.TrimPrefix(f, root)
		}
	}
	return nil, ""
}

// Experiment devolve o registro de experimento correspondente ao autoteste.
func SelfTestExperiment() experiments.Experiment {
	return experiments.Experiment{
		ID:               SelfTestID,
		Description:      "Autoteste da infraestrutura: cadeia SHA-256 em CPU para validar o pipeline medição → SQLite → relatório.",
		HypothesisSource: "interna (validação de pipeline)", ApplicableHardware: []string{"cpu"},
		Prerequisites: []string{"nenhum"}, PotentialImpact: "nenhum (não é otimização)",
		OperationalRisk: "baixo", Reversibility: "total", Confidence: "alta",
		Favorable: []experiments.Evidence{{Summary: "Carga determinística em espaço de usuário, sem acesso a hardware além de leitura de temperatura."}},
		Level:     experiments.LevelB, Kind: "infra_selftest", Origin: Measured, InfrastructureTest: true,
	}
}

// Save grava um resultado. O experimento deve existir.
func Save(db *storage.DB, r Result) error {
	if err := r.Validate(); err != nil {
		return err
	}
	p, _ := json.Marshal(map[string]any{"params": r.Params, "meta": r.Meta, "note": r.Note, "infrastructure_test": r.InfrastructureTest})
	var hw any
	if r.HardwareSnapshotID > 0 {
		hw = r.HardwareSnapshotID
	}
	_, err := db.SQL().Exec(`INSERT INTO results(experiment_id,origin,metric,value,unit,params_json,hardware_snapshot_id,recorded_at)
		VALUES(?,?,?,?,?,?,?,?)`, r.ExperimentID, r.Origin, r.Metric, r.Value, r.Unit, string(p), hw, storage.Now())
	return err
}

// Validate garante campos mínimos e origem conhecida.
func (r Result) Validate() error {
	switch r.Origin {
	case Measured, Simulated, Estimated, Fixture:
	default:
		return fmt.Errorf("origem %q inválida", r.Origin)
	}
	if r.ExperimentID == "" || r.Metric == "" || r.Unit == "" {
		return errors.New("resultado exige experiment_id, metric e unit")
	}
	return nil
}

// Stored é um resultado lido do banco.
type Stored struct {
	ID           int64   `json:"id"`
	ExperimentID string  `json:"experiment_id"`
	Origin       string  `json:"origin"`
	Metric       string  `json:"metric"`
	Value        float64 `json:"value"`
	Unit         string  `json:"unit"`
	RecordedAt   string  `json:"recorded_at"`
}

// ListResults devolve os resultados (filtro opcional por experimento).
func ListResults(db *storage.DB, experimentID string) ([]Stored, error) {
	rows, err := db.SQL().Query(`SELECT id,experiment_id,origin,metric,value,unit,recorded_at FROM results
		WHERE (?='' OR experiment_id=?) ORDER BY id`, experimentID, experimentID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Stored
	for rows.Next() {
		var s Stored
		if err := rows.Scan(&s.ID, &s.ExperimentID, &s.Origin, &s.Metric, &s.Value, &s.Unit, &s.RecordedAt); err != nil {
			return nil, err
		}
		out = append(out, s)
	}
	return out, rows.Err()
}

// ErrSemMedicao é devolvido quando uma melhoria é alegada sem medições adequadas.
var ErrSemMedicao = errors.New("melhoria não pode ser declarada sem medições reais")

// ClaimImprovement só autoriza declarar melhoria se baseline e candidato forem
// medidos (origin=measured), da mesma métrica/unidade, com >=3 amostras cada e
// fora de testes de infraestrutura. Resultados simulados/estimados nunca bastam.
func ClaimImprovement(baseline, candidate []Result) error {
	if len(baseline) < 3 || len(candidate) < 3 {
		return fmt.Errorf("%w: são necessárias >=3 amostras por grupo (baseline=%d, candidato=%d)", ErrSemMedicao, len(baseline), len(candidate))
	}
	ref := baseline[0]
	for _, g := range [][]Result{baseline, candidate} {
		for _, r := range g {
			if r.Origin != Measured {
				return fmt.Errorf("%w: origem %q não é 'measured'", ErrSemMedicao, r.Origin)
			}
			if r.InfrastructureTest {
				return fmt.Errorf("%w: testes de infraestrutura não comparam hardware", ErrSemMedicao)
			}
			if r.Metric != ref.Metric || r.Unit != ref.Unit {
				return fmt.Errorf("%w: métricas/unidades diferentes", ErrSemMedicao)
			}
		}
	}
	return nil
}
