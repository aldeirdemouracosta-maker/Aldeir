package compiler

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"

	"hrail/catalog"
	"hrail/internal/security"
	"hrail/internal/tools"
)

func TestInventarioSemFerramentas(t *testing.T) {
	t.Setenv("PATH", t.TempDir())
	defs, _ := tools.ParseCatalog(catalog.ToolsJSON)
	inv := Collect(context.Background(), tools.New(defs, security.NewRunner(time.Second, tools.AllowList(defs)...)))
	if len(inv.Mesa) != 3 || len(inv.Shader) < 4 {
		t.Fatalf("mesa=%d shader=%d", len(inv.Mesa), len(inv.Shader))
	}
	for _, c := range inv.Offline {
		if c.Possible {
			t.Errorf("%s não deveria ser possível sem ferramentas", c.Name)
		}
	}
}

func TestGlslangDetectado(t *testing.T) {
	dir := t.TempDir()
	t.Setenv("PATH", dir)
	os.WriteFile(filepath.Join(dir, "glslangValidator"), []byte("#!/bin/sh\necho 'Glslang Version: 11:15.0.0'\n"), 0o755)
	defs, _ := tools.ParseCatalog(catalog.ToolsJSON)
	inv := Collect(context.Background(), tools.New(defs, security.NewRunner(time.Second, tools.AllowList(defs)...)))
	if !inv.Offline[0].Possible {
		t.Errorf("GLSL→SPIR-V deveria ser possível: %+v", inv.Offline[0])
	}
}
