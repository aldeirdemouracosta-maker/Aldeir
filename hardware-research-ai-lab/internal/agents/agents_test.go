package agents

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"hrail/catalog"
	"hrail/internal/config"
	"hrail/internal/security"
	"hrail/internal/tools"
)

func reg(t *testing.T) *tools.Registry {
	t.Setenv("PATH", t.TempDir())
	defs, _ := tools.ParseCatalog(catalog.ToolsJSON)
	return tools.New(defs, security.NewRunner(time.Second, tools.AllowList(defs)...))
}

func TestProvedoresAusentes(t *testing.T) {
	r := reg(t)
	for _, p := range []Provider{Ollama{Registry: r, Cfg: config.Default().Agents}, LlamaCpp{Registry: r}} {
		a := p.Check(context.Background())
		if a.Available || a.Detail == "" {
			t.Errorf("%s: %+v", p.Name(), a)
		}
	}
}

func TestEndpointSoLoopback(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) { w.Write([]byte(`{"version":"x"}`)) }))
	defer srv.Close()
	cfg := config.Agents{Enabled: true, OllamaURL: srv.URL} // 127.0.0.1
	if a := (Ollama{Registry: reg(t), Cfg: cfg}).Check(context.Background()); !a.Available {
		t.Errorf("loopback deveria responder: %+v", a)
	}
	cfg.OllamaURL = "http://example.org:11434"
	if a := (Ollama{Registry: reg(t), Cfg: cfg}).Check(context.Background()); a.Available {
		t.Errorf("host externo não pode ser consultado: %+v", a)
	}
}

func TestIAnaoAprovaNemAlegaMelhoria(t *testing.T) {
	if err := Approve(Proposal{Description: "x"}); !errors.Is(err, ErrIAnaoAprova) {
		t.Fatal("Approve deve sempre falhar")
	}
	d := Review(Proposal{Description: "trocar módulo", Privileged: true})
	if d.Accepted || !d.NeedsHuman {
		t.Errorf("privilegiada: %+v", d)
	}
	d = Review(Proposal{Description: "30% mais rápido", ClaimsImprove: true})
	if d.Accepted {
		t.Errorf("melhoria sem medição: %+v", d)
	}
	d = Review(Proposal{Description: "30% mais rápido", ClaimsImprove: true, MeasuredResultIDs: []int64{1, 2, 3}})
	if !d.Accepted {
		t.Errorf("com medições referenciadas vira hipótese registrada: %+v", d)
	}
}
