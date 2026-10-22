package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestPadraoValido(t *testing.T) {
	c := Default()
	if err := c.Validate(); err != nil {
		t.Fatal(err)
	}
	if len(c.EnabledLevels) != 2 || c.Agents.Enabled {
		t.Fatalf("padrão inseguro: %+v", c)
	}
}

func TestNiveisProibidosNaFase0(t *testing.T) {
	for _, l := range []string{"C", "D", "E", "Z"} {
		c := Default()
		c.EnabledLevels = []string{"A", l}
		if c.Validate() == nil {
			t.Errorf("nível %s não deveria ser aceito", l)
		}
	}
}

func TestLoadEFindRoot(t *testing.T) {
	root := t.TempDir()
	os.MkdirAll(filepath.Join(root, "configs", "sub"), 0o755)
	os.WriteFile(filepath.Join(root, "configs", "hrail.json"), []byte(`{"command_timeout":"3s","enabled_levels":["A"],"database_path":"data/x.db","reports_dir":"reports","catalog_dir":"catalog"}`), 0o644)
	got, err := FindRoot(filepath.Join(root, "configs", "sub"))
	if err != nil || got != root {
		t.Fatalf("FindRoot=%q err=%v", got, err)
	}
	c, err := Load(root)
	if err != nil || c.Timeout().Seconds() != 3 || len(c.EnabledLevels) != 1 {
		t.Fatalf("%+v %v", c, err)
	}
}

func TestLoadAusenteUsaPadraoEInvalidoFalha(t *testing.T) {
	root := t.TempDir()
	if _, err := Load(root); err != nil {
		t.Fatalf("ausente deve usar padrão: %v", err)
	}
	os.MkdirAll(filepath.Join(root, "configs"), 0o755)
	os.WriteFile(filepath.Join(root, "configs", "hrail.json"), []byte(`{nope`), 0o644)
	if _, err := Load(root); err == nil {
		t.Fatal("JSON inválido deve falhar")
	}
}
