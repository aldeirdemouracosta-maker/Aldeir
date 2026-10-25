package manifest

import (
	"testing"
	"testing/fstest"

	"rea-lab/modules"
)

func TestManifestosEmbutidos(t *testing.T) {
	mods, err := LoadAll(modules.FS)
	if err != nil {
		t.Fatal(err)
	}
	if len(mods) != 15 {
		t.Fatalf("esperava 15 laboratórios, obtive %d", len(mods))
	}
	for _, m := range mods {
		if m.Permissoes.ExecutaAmostras || m.Permissoes.GravaFirmware {
			t.Errorf("%s com permissão proibida", m.ID)
		}
	}
}

func TestRejeitaPermissoesProibidas(t *testing.T) {
	for _, campo := range []string{"executa_amostras", "grava_firmware"} {
		fs := fstest.MapFS{"x.json": {Data: []byte(`{"id":"lab.x","nome":"X","versao":"1","permissoes":{"` + campo + `":true}}`)}}
		if _, err := LoadAll(fs); err == nil {
			t.Errorf("%s=true deveria ser rejeitado", campo)
		}
	}
}
