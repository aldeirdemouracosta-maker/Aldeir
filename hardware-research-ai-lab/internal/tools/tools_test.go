package tools

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"

	"hrail/catalog"
	"hrail/internal/security"
)

func fakeBin(t *testing.T, name, script string) {
	t.Helper()
	dir := os.Getenv("PATH_FAKE")
	p := filepath.Join(dir, name)
	if err := os.WriteFile(p, []byte("#!/bin/sh\n"+script+"\n"), 0o755); err != nil {
		t.Fatal(err)
	}
}

func setupPath(t *testing.T) {
	t.Helper()
	dir := t.TempDir()
	t.Setenv("PATH_FAKE", dir)
	t.Setenv("PATH", dir+":/usr/bin:/bin")
}

func reg(defs []Def) *Registry {
	return New(defs, security.NewRunner(3*time.Second, AllowList(defs)...))
}

func TestCatalogoEmbutidoValido(t *testing.T) {
	defs, err := ParseCatalog(catalog.ToolsJSON)
	if err != nil || len(defs) < 15 {
		t.Fatalf("n=%d err=%v", len(defs), err)
	}
	ids := map[string]bool{}
	for _, d := range defs {
		ids[d.ID] = true
	}
	for _, want := range []string{"vulkaninfo", "glslangValidator", "ollama", "llama-cli", "gem5", "mgpusim", "nir", "aco", "radv-icd", "spirv-val"} {
		if !ids[want] {
			t.Errorf("ferramenta %s ausente do catálogo", want)
		}
	}
}

func TestCatalogoInvalido(t *testing.T) {
	for _, js := range []string{
		`{`,
		`{"tools":[{"id":"a","name":"A","category":"x"},{"id":"a","name":"B","category":"x"}]}`,
		`{"tools":[{"id":"","name":"A","category":"x"}]}`,
		`{"tools":[{"id":"a","name":"A","category":"x","version_regex":"("}]}`,
	} {
		if _, err := ParseCatalog([]byte(js)); err == nil {
			t.Errorf("deveria falhar: %s", js)
		}
	}
}

func TestListNaoExecutaNada(t *testing.T) {
	defs, _ := ParseCatalog(catalog.ToolsJSON)
	r := reg(defs)
	for _, c := range r.List() {
		if c.Status != NaoTestado {
			t.Fatalf("%s deveria ser nao_testado", c.Def.ID)
		}
	}
	if len(r.Runner.Records()) != 0 {
		t.Fatal("List não deve executar comandos")
	}
}

func TestEstadosDisponivelAusenteIncompativel(t *testing.T) {
	setupPath(t)
	fakeBin(t, "okTool", `echo "tool version 2.5.1"`)
	fakeBin(t, "oldTool", `echo "tool version 1.0.0"`)
	defs := []Def{
		{ID: "ok", Name: "ok", Category: "x", Executables: []string{"okTool"}, VersionArgs: []string{"--v"}, VersionRegex: `version ([0-9.]+)`, MinVersion: "2.0"},
		{ID: "old", Name: "old", Category: "x", Executables: []string{"oldTool"}, VersionArgs: []string{"--v"}, VersionRegex: `version ([0-9.]+)`, MinVersion: "2.0"},
		{ID: "gone", Name: "gone", Category: "x", Executables: []string{"naoExiste"}},
		{ID: "intree", Name: "n", Category: "mesa", Kind: "in-tree"},
	}
	got := map[string]Check{}
	for _, c := range reg(defs).CheckAll(context.Background()) {
		got[c.Def.ID] = c
	}
	if got["ok"].Status != Disponivel || got["ok"].Version != "2.5.1" {
		t.Errorf("ok: %+v", got["ok"])
	}
	if got["old"].Status != Incompativel {
		t.Errorf("old: %+v", got["old"])
	}
	if got["gone"].Status != Ausente {
		t.Errorf("gone: %+v", got["gone"])
	}
	if got["intree"].Status != NaoTestado {
		t.Errorf("intree: %+v", got["intree"])
	}
}

func TestFerramentaComFalhaNaoQuebraDiagnostico(t *testing.T) {
	setupPath(t)
	fakeBin(t, "falha", `exit 3`)
	fakeBin(t, "lenta", `sleep 30`)
	defs := []Def{
		{ID: "f", Name: "f", Category: "x", Executables: []string{"falha"}, VersionArgs: []string{"-v"}, VersionRegex: `(\d+)`},
		{ID: "l", Name: "l", Category: "x", Executables: []string{"lenta"}, VersionArgs: []string{"-v"}, VersionRegex: `(\d+)`},
	}
	r := New(defs, security.NewRunner(300*time.Millisecond, AllowList(defs)...))
	cs := r.CheckAll(context.Background())
	if cs[0].Status != Disponivel || cs[0].Detail == "" {
		t.Errorf("exit 3: %+v", cs[0])
	}
	if cs[1].Status != NaoTestado || cs[1].Detail == "" {
		t.Errorf("timeout deve virar nao_testado com detalhe: %+v", cs[1])
	}
}

func TestProbeFiles(t *testing.T) {
	dir := t.TempDir()
	os.WriteFile(filepath.Join(dir, "radeon_icd.x86_64.json"), []byte("{}"), 0o644)
	d := Def{ID: "r", Name: "r", Category: "mesa", ProbeFiles: []string{filepath.Join(dir, "radeon_icd*.json")}}
	if c := reg([]Def{d}).CheckOne(context.Background(), d); c.Status != Disponivel {
		t.Fatalf("%+v", c)
	}
	d.ProbeFiles = []string{filepath.Join(dir, "nada*.json")}
	if c := reg([]Def{d}).CheckOne(context.Background(), d); c.Status != Ausente {
		t.Fatalf("%+v", c)
	}
}

func TestVersoes(t *testing.T) {
	cases := []struct {
		a, b string
		want int
	}{{"1.2.3", "1.2.3", 0}, {"1.10", "1.9", 1}, {"v1.0", "1.0.1", -1}, {"2", "1.99.99", 1}}
	for _, c := range cases {
		if got := CompareVersions(c.a, c.b); got != c.want {
			t.Errorf("%s vs %s = %d", c.a, c.b, got)
		}
	}
	if ExtractVersion(`go([0-9.]+)`, "go version go1.24.7 linux") != "1.24.7" {
		t.Error("extract")
	}
}
