// Package agents implementa o ai-research-agent (Fase 0): arquitetura, configuração
// e verificação de disponibilidade. Nenhum modelo é chamado para gerar conteúdo.
package agents

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/url"
	"time"

	"hrail/internal/config"
	"hrail/internal/tools"
)

// Availability descreve o estado de um provedor.
type Availability struct {
	Provider  string `json:"provider"`
	Available bool   `json:"available"`
	Detail    string `json:"detail"`
}

// Provider é a interface para provedores de IA (Ollama, llama.cpp, futuros).
type Provider interface {
	Name() string
	Check(ctx context.Context) Availability
}

// Ollama verifica o binário e, se configurado e local, o endpoint HTTP.
type Ollama struct {
	Registry *tools.Registry
	Cfg      config.Agents
}

func (Ollama) Name() string { return "ollama" }

func (o Ollama) Check(ctx context.Context) Availability {
	a := Availability{Provider: "ollama"}
	c := o.Registry.DetectByID(ctx, "ollama")
	if c.Status != tools.Disponivel {
		a.Detail = "binário ollama ausente no PATH"
	} else {
		a.Available, a.Detail = true, "binário em "+c.Path+" (versão: "+orUnknown(c.Version)+")"
	}
	if o.Cfg.Enabled {
		if err := probeLocal(ctx, o.Cfg.OllamaURL+"/api/version"); err != nil {
			a.Detail += "; endpoint: " + err.Error()
		} else {
			a.Available, a.Detail = true, a.Detail+"; endpoint respondeu"
		}
	} else {
		a.Detail += "; endpoint não consultado (agents.enabled=false)"
	}
	return a
}

// LlamaCpp verifica llama-cli / llama-server.
type LlamaCpp struct{ Registry *tools.Registry }

func (LlamaCpp) Name() string { return "llama.cpp" }

func (l LlamaCpp) Check(ctx context.Context) Availability {
	a := Availability{Provider: "llama.cpp", Detail: "llama-cli e llama-server ausentes no PATH"}
	for _, id := range []string{"llama-cli", "llama-server"} {
		if c := l.Registry.DetectByID(ctx, id); c.Status == tools.Disponivel {
			a.Available, a.Detail = true, id+" em "+c.Path+" (versão: "+orUnknown(c.Version)+")"
			break
		}
	}
	return a
}

func orUnknown(s string) string {
	if s == "" {
		return "desconhecida"
	}
	return s
}

// probeLocal só consulta endpoints em loopback (nada sai da máquina).
func probeLocal(ctx context.Context, raw string) error {
	u, err := url.Parse(raw)
	if err != nil {
		return err
	}
	if ip := net.ParseIP(u.Hostname()); !(u.Hostname() == "localhost" || (ip != nil && ip.IsLoopback())) {
		return fmt.Errorf("endpoint %q não é loopback; consulta recusada", u.Host)
	}
	cctx, cancel := context.WithTimeout(ctx, 2*time.Second)
	defer cancel()
	req, _ := http.NewRequestWithContext(cctx, http.MethodGet, raw, nil)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return errors.New("sem resposta")
	}
	resp.Body.Close()
	if resp.StatusCode != 200 {
		return fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	return nil
}

// CheckAll verifica todos os provedores.
func CheckAll(ctx context.Context, ps []Provider) []Availability {
	var out []Availability
	for _, p := range ps {
		out = append(out, p.Check(ctx))
	}
	return out
}

// ---- Política: a IA nunca aprova mudanças privilegiadas nem declara melhorias ----

// ErrIAnaoAprova é devolvido quando um agente tenta aprovar algo.
var ErrIAnaoAprova = errors.New("agentes de IA não podem aprovar mudanças privilegiadas; aprovação humana é obrigatória")

// Proposal é uma sugestão produzida por um agente.
type Proposal struct {
	Description   string `json:"description"`
	Privileged    bool   `json:"privileged"`
	ClaimsImprove bool   `json:"claims_improvement"`
	// MeasuredResultIDs referencia resultados 'measured' que sustentam a alegação.
	MeasuredResultIDs []int64 `json:"measured_result_ids"`
}

// Decision é o parecer da política.
type Decision struct {
	Accepted   bool   `json:"accepted"`
	NeedsHuman bool   `json:"needs_human_approval"`
	Reason     string `json:"reason"`
}

// Review aplica a política. Propostas de IA são sempre apenas sugestões.
func Review(p Proposal) Decision {
	if p.Privileged {
		return Decision{Accepted: false, NeedsHuman: true, Reason: ErrIAnaoAprova.Error()}
	}
	if p.ClaimsImprove && len(p.MeasuredResultIDs) == 0 {
		return Decision{Accepted: false, NeedsHuman: true, Reason: "alegação de melhoria sem medições referenciadas"}
	}
	return Decision{Accepted: true, NeedsHuman: false, Reason: "sugestão registrada como hipótese (não é aprovação de mudança)"}
}

// Approve existe para tornar a regra explícita: sempre falha.
func Approve(Proposal) error { return ErrIAnaoAprova }
