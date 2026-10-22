package tests

import (
	"bytes"
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"hrail/internal/discovery"
)

var bin string

func TestMain(m *testing.M) {
	dir, _ := os.MkdirTemp("", "hrail-e2e")
	bin = filepath.Join(dir, "hrail")
	out, err := exec.Command("go", "build", "-o", bin, "hrail/cmd/hrail").CombinedOutput()
	if err != nil {
		os.Stderr.WriteString("falha ao compilar a CLI: " + string(out))
		os.Exit(1)
	}
	code := m.Run()
	os.RemoveAll(dir)
	os.Exit(code)
}

// projeto cria uma raiz temporária com o config do repositório e uma árvore de hardware fictícia.
func projeto(t *testing.T) (root, sys string) {
	t.Helper()
	root, sys = t.TempDir(), t.TempDir()
	cfg, err := os.ReadFile("../configs/hrail.json")
	if err != nil {
		t.Fatal(err)
	}
	os.MkdirAll(filepath.Join(root, "configs"), 0o755)
	os.WriteFile(filepath.Join(root, "configs", "hrail.json"), cfg, 0o644)
	if err := discovery.WriteFixture(sys); err != nil {
		t.Fatal(err)
	}
	return
}

func hrail(t *testing.T, root, sys string, args ...string) (string, string, int) {
	t.Helper()
	cmd := exec.Command(bin, append([]string{"--raiz", root}, args...)...)
	cmd.Env = []string{"PATH=" + t.TempDir(), "HOME=" + t.TempDir(), "HRAIL_SYSROOT=" + sys}
	var so, se bytes.Buffer
	cmd.Stdout, cmd.Stderr = &so, &se
	err := cmd.Run()
	code := 0
	if ee, ok := err.(*exec.ExitError); ok {
		code = ee.ExitCode()
	} else if err != nil {
		t.Fatal(err)
	}
	return so.String(), se.String(), code
}

func TestFluxoCompletoComFerramentasAusentes(t *testing.T) {
	root, sys := projeto(t)

	out, errs, code := hrail(t, root, sys, "doctor")
	if code != 0 || !strings.Contains(out, "vulkaninfo: ausente (opcional)") {
		t.Fatalf("doctor code=%d\n%s\n%s", code, out, errs)
	}
	if _, err := os.Stat(filepath.Join(root, "data", "hrail.db")); err == nil {
		t.Fatal("doctor não deve criar o banco")
	}

	if out, errs, code = hrail(t, root, sys, "init"); code != 0 {
		t.Fatalf("init: %s %s", out, errs)
	}
	out, _, code = hrail(t, root, sys, "hardware", "list")
	if code != 0 || !strings.Contains(out, "fixture") || !strings.Contains(out, "RX 580 2048SP") || !strings.Contains(out, "requer_verificacao") {
		t.Fatalf("hardware list:\n%s", out)
	}

	out, _, code = hrail(t, root, sys, "hardware", "inspect")
	var inv discovery.Inventory
	if code != 0 || json.Unmarshal([]byte(out), &inv) != nil || inv.Origin != "fixture" || len(inv.GPUs) != 1 {
		t.Fatalf("inspect não gerou JSON válido de fixture:\n%s", out)
	}

	out, _, code = hrail(t, root, sys, "tools", "check")
	if code != 0 || !strings.Contains(out, "ausente") || !strings.Contains(out, "opcionais") {
		t.Fatalf("tools check:\n%s", out)
	}
	out, _, _ = hrail(t, root, sys, "tools", "list")
	if !strings.Contains(out, "nao_testado") {
		t.Fatalf("tools list:\n%s", out)
	}
	out, _, code = hrail(t, root, sys, "research", "sources")
	if code != 0 || !strings.Contains(out, "sarchlab/mgpusim") || !strings.Contains(out, "nao_verificado") {
		t.Fatalf("research sources:\n%s", out)
	}
	out, _, code = hrail(t, root, sys, "benchmark", "selftest")
	if code != 0 || !strings.Contains(out, "TESTE DA INFRAESTRUTURA") {
		t.Fatalf("selftest:\n%s", out)
	}
	out, _, _ = hrail(t, root, sys, "experiment", "list")
	if !strings.Contains(out, "INFRA-SELFTEST-CPU") || !strings.Contains(out, "TESTE DE INFRAESTRUTURA") {
		t.Fatalf("experiment list:\n%s", out)
	}
	for _, c := range []string{"simulation", "compiler", "agents"} {
		sub := "check"
		if c != "agents" {
			sub = "info"
		}
		if out, errs, code := hrail(t, root, sys, c, sub); code != 0 {
			t.Fatalf("%s: %s %s", c, out, errs)
		}
	}

	out, _, code = hrail(t, root, sys, "report", "generate")
	if code != 0 {
		t.Fatalf("report: %s", out)
	}
	mds, _ := filepath.Glob(filepath.Join(root, "reports", "relatorio_*.md"))
	jss, _ := filepath.Glob(filepath.Join(root, "reports", "relatorio_*.json"))
	if len(mds) != 1 || len(jss) != 1 {
		t.Fatalf("relatórios: %v %v", mds, jss)
	}
	b, _ := os.ReadFile(jss[0])
	var js map[string]any
	if json.Unmarshal(b, &js) != nil {
		t.Fatal("JSON do relatório inválido")
	}
	md, _ := os.ReadFile(mds[0])
	for _, want := range []string{"## Limitações", "TESTE DE INFRAESTRUTURA", "### measured", "RX 580 2048SP"} {
		if !strings.Contains(string(md), want) {
			t.Errorf("relatório sem %q", want)
		}
	}

	// exportação do banco
	if _, _, code = hrail(t, root, sys, "banco", "exportar", "--formato", "json", "--saida", "data/export.json"); code != 0 {
		t.Fatal("export json")
	}
	if _, _, code = hrail(t, root, sys, "banco", "exportar", "--formato", "csv", "--tabela", "results", "--saida", "data/results.csv"); code != 0 {
		t.Fatal("export csv")
	}
	csv, _ := os.ReadFile(filepath.Join(root, "data", "results.csv"))
	if !strings.Contains(string(csv), "sha256_chain_rate") {
		t.Errorf("csv: %s", csv)
	}
	// comandos externos registrados (a ferramenta ausente não gera execução; verificamos a tabela)
	if _, _, code = hrail(t, root, sys, "banco", "exportar", "--saida", "../fora.json"); code == 0 {
		t.Fatal("saída fora do projeto deve ser recusada")
	}
}

func TestRegistrarExperimentoEBloqueioDeNiveis(t *testing.T) {
	root, sys := projeto(t)
	ok := `{"id":"EXP-A1","description":"revisar histórico de commits (offline)","hypothesis_source":"manual","applicable_hardware":["gpu"],
	"operational_risk":"baixo","reversibility":"total","confidence":"baixa","level":"A","kind":"analise","origin":"estimated"}`
	os.WriteFile(filepath.Join(root, "a.json"), []byte(ok), 0o644)
	out, errs, code := hrail(t, root, sys, "experiment", "registrar", "--arquivo", "a.json")
	if code != 0 || !strings.Contains(out, "sem_evidencia") {
		t.Fatalf("%s %s", out, errs)
	}
	bad := strings.Replace(strings.Replace(ok, `"EXP-A1"`, `"EXP-C1"`, 1), `"level":"A"`, `"level":"C"`, 1)
	os.WriteFile(filepath.Join(root, "c.json"), []byte(bad), 0o644)
	_, errs, code = hrail(t, root, sys, "experiment", "registrar", "--arquivo", "c.json")
	if code == 0 || !strings.Contains(errs, "desativado") {
		t.Fatalf("nível C deve ser recusado: code=%d %s", code, errs)
	}
}

func TestConfigComNivelProibidoEhRecusada(t *testing.T) {
	root, sys := projeto(t)
	os.WriteFile(filepath.Join(root, "configs", "hrail.json"), []byte(`{"enabled_levels":["A","B","C"]}`), 0o644)
	_, errs, code := hrail(t, root, sys, "doctor")
	if code == 0 || !strings.Contains(errs, "Fase 0") {
		t.Fatalf("code=%d %s", code, errs)
	}
}

func TestComandoDesconhecidoEAjuda(t *testing.T) {
	root, sys := projeto(t)
	if _, _, code := hrail(t, root, sys, "voar"); code != 2 {
		t.Fatalf("código=%d", code)
	}
	out, _, code := hrail(t, root, sys)
	if code != 0 || !strings.Contains(out, "hardware inspect") {
		t.Fatal("ajuda")
	}
}
