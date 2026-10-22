package benchmark

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"

	"hrail/internal/experiments"
	"hrail/internal/storage"
)

func TestSelfTestIdentificadoComoInfraestrutura(t *testing.T) {
	r, err := SelfTest(context.Background(), Options{Iterations: 5000, SysRoot: t.TempDir(), Version: "t"})
	if err != nil {
		t.Fatal(err)
	}
	if !r.InfrastructureTest || r.ExperimentID != SelfTestID || r.Value <= 0 || r.Meta.TempCelsius != nil {
		t.Errorf("%+v", r)
	}
	r2, _ := SelfTest(context.Background(), Options{Iterations: 5000, SysRoot: t.TempDir()})
	if r.Params["final_digest_prefix"] != r2.Params["final_digest_prefix"] {
		t.Error("carga deve ser determinística (reprodutível)")
	}
}

func TestTemperatura(t *testing.T) {
	root := t.TempDir()
	p := filepath.Join(root, "sys/class/hwmon/hwmon0")
	os.MkdirAll(p, 0o755)
	os.WriteFile(filepath.Join(p, "temp1_input"), []byte("51500\n"), 0o644)
	c, src := ReadTemperature(root)
	if c == nil || *c != 51.5 || src == "" {
		t.Fatalf("%v %s", c, src)
	}
	if c, _ := ReadTemperature(t.TempDir()); c != nil {
		t.Fatal("sem sensor deve ser nil")
	}
}

func TestCancelamento(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if _, err := SelfTest(ctx, Options{Iterations: 10_000_000}); err == nil {
		t.Fatal("deveria respeitar cancelamento")
	}
}

func TestPersistenciaSeparaOrigens(t *testing.T) {
	db, _ := storage.Open(filepath.Join(t.TempDir(), "b.db"))
	defer db.Close()
	if err := experiments.Save(db, SelfTestExperiment(), []experiments.Level{"A", "B"}); err != nil {
		t.Fatal(err)
	}
	r, _ := SelfTest(context.Background(), Options{Iterations: 1000})
	if err := Save(db, r); err != nil {
		t.Fatal(err)
	}
	r.Origin = Simulated
	if err := Save(db, r); err != nil {
		t.Fatal(err)
	}
	r.Origin = "magica"
	if err := Save(db, r); err == nil {
		t.Fatal("origem inválida")
	}
	r.Origin, r.ExperimentID = Measured, "NAO-EXISTE"
	if err := Save(db, r); err == nil {
		t.Fatal("chave estrangeira deve rejeitar experimento inexistente")
	}
	all, err := ListResults(db, "")
	if err != nil || len(all) != 2 || all[0].Origin == all[1].Origin {
		t.Fatalf("%+v %v", all, err)
	}
}

func mk(origin string, n int) []Result {
	var out []Result
	for i := 0; i < n; i++ {
		out = append(out, Result{ExperimentID: "X", Origin: origin, Metric: "m", Unit: "u", Value: float64(i)})
	}
	return out
}

func TestMelhoriaExigeMedicao(t *testing.T) {
	if err := ClaimImprovement(mk(Measured, 3), mk(Measured, 3)); err != nil {
		t.Fatalf("medições adequadas: %v", err)
	}
	for name, c := range map[string][2][]Result{
		"poucas amostras": {mk(Measured, 3), mk(Measured, 2)},
		"simulado":        {mk(Measured, 3), mk(Simulated, 3)},
		"estimado":        {mk(Estimated, 3), mk(Measured, 3)},
		"fixture":         {mk(Fixture, 3), mk(Fixture, 3)},
	} {
		if err := ClaimImprovement(c[0], c[1]); !errors.Is(err, ErrSemMedicao) {
			t.Errorf("%s: deveria recusar (%v)", name, err)
		}
	}
	infra := mk(Measured, 3)
	for i := range infra {
		infra[i].InfrastructureTest = true
	}
	if err := ClaimImprovement(infra, infra); !errors.Is(err, ErrSemMedicao) {
		t.Error("teste de infraestrutura não compara hardware")
	}
}
