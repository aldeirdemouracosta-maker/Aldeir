package simulation

import (
	"context"
	"errors"
	"testing"
	"time"

	"hrail/catalog"
	"hrail/internal/security"
	"hrail/internal/tools"
)

func TestDeteccaoSemExecutarSimulacoes(t *testing.T) {
	t.Setenv("PATH", t.TempDir())
	defs, _ := tools.ParseCatalog(catalog.ToolsJSON)
	reg := tools.New(defs, security.NewRunner(time.Second, tools.AllowList(defs)...))
	infos := New(reg).Describe(context.Background())
	if len(infos) != 2 {
		t.Fatalf("esperava MGPUSim e gem5: %d", len(infos))
	}
	for _, i := range infos {
		if i.Check.Status != tools.Ausente {
			t.Errorf("%s: %s", i.Metadata.ID, i.Check.Status)
		}
		if i.Metadata.ExecutesWorkloads || len(i.Metadata.EquivalenceClaims) != 0 {
			t.Errorf("%s não pode executar cargas nem declarar equivalências", i.Metadata.ID)
		}
	}
	if len(reg.Runner.Records()) != 0 {
		t.Fatal("nenhum comando deveria ser executado com ferramentas ausentes")
	}
}

func TestEquivalenciaExigeEvidencia(t *testing.T) {
	if _, err := ClaimEquivalence("GCN3", "Polaris", nil); !errors.Is(err, ErrSemEvidencia) {
		t.Fatal("GCN3≡Polaris sem evidência deve ser recusado")
	}
	if _, err := ClaimEquivalence("Polaris", "gfx9", []string{}); !errors.Is(err, ErrSemEvidencia) {
		t.Fatal("Polaris≡gfx9 sem evidência deve ser recusado")
	}
	c, err := ClaimEquivalence("GCN3", "Polaris", []string{"https://example.org/estudo"})
	if err != nil || c.Status != "alegada_nao_validada" {
		t.Fatalf("%+v %v", c, err)
	}
}
