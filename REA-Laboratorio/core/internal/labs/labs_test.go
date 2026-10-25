package labs

import (
	"errors"
	"testing"

	"rea-lab/internal/manifest"
	"rea-lab/modules"
)

func estados(t *testing.T, tem map[string]bool) map[string]Estado {
	mods, err := manifest.LoadAll(modules.FS)
	if err != nil {
		t.Fatal(err)
	}
	look := func(n string) (string, error) {
		if tem[n] {
			return "/bin/" + n, nil
		}
		return "", errors.New("ausente")
	}
	m := map[string]Estado{}
	for _, e := range Avaliar(mods, look) {
		m[e.ID] = e
	}
	return m
}

func TestImplementadosSaoDisponiveisPorFumacaReal(t *testing.T) {
	m := estados(t, nil)
	for _, id := range []string{"lab.formatos", "lab.zip"} {
		if m[id].Estado != "disponivel" {
			t.Errorf("%s: %+v", id, m[id])
		}
	}
}

func TestNaoImplementadoNuncaEhDisponivelMesmoComFerramentas(t *testing.T) {
	m := estados(t, map[string]bool{"readelf": true, "objdump": true, "file": true, "strings": true})
	if e := m["lab.apps"]; e.Estado != "planejado" || len(e.Encontradas) != 4 {
		t.Fatalf("%+v", e)
	}
}

func TestSmokeQuebradoEhReportado(t *testing.T) {
	antigo := Smoke["lab.zip"]
	Smoke["lab.zip"] = func() error { return errors.New("falha simulada") }
	defer func() { Smoke["lab.zip"] = antigo }()
	if e := estados(t, nil)["lab.zip"]; e.Estado != "quebrado" {
		t.Fatalf("%+v", e)
	}
}

func TestTodosOs15Avaliados(t *testing.T) {
	if n := len(estados(t, nil)); n != 15 {
		t.Fatalf("%d", n)
	}
}
