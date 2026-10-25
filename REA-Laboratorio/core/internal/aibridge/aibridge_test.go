package aibridge

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"rea-lab/internal/guardian"
)

var ctx = context.Background()

func TestProbeOllama(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/tags" {
			http.NotFound(w, r)
			return
		}
		w.Write([]byte(`{"models":[{"name":"gpt-oss:20b"},{"name":"llama3:8b"}]}`))
	}))
	defer s.Close()
	st := Probe(ctx, s.Client(), guardian.Policy{}, Engine{"Ollama", "ollama", s.URL}, false)
	if !st.Presente || len(st.Modelos) != 2 || st.Remoto {
		t.Fatalf("%+v", st)
	}
}

func TestProbeOpenAICompat(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte(`{"data":[{"id":"qwen"}]}`))
	}))
	defer s.Close()
	st := Probe(ctx, s.Client(), guardian.Policy{}, Engine{"x", "openai", s.URL}, false)
	if !st.Presente || st.Modelos[0] != "qwen" {
		t.Fatalf("%+v", st)
	}
}

func TestProbeSemServidor(t *testing.T) {
	st := Probe(ctx, &http.Client{}, guardian.Policy{}, Engine{"x", "ollama", "http://127.0.0.1:1"}, false)
	if st.Presente || st.Detalhe == "" {
		t.Fatalf("%+v", st)
	}
}

func TestRespostaInesperadaNaoEhPresente(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.Write([]byte("<html>")) }))
	defer s.Close()
	if Probe(ctx, s.Client(), guardian.Policy{}, Engine{"x", "openai", s.URL}, false).Presente {
		t.Fatal("HTML não é a API")
	}
}

func TestRemotoSemAutorizacaoNaoEnviaNada(t *testing.T) {
	chamado := false
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { chamado = true }))
	defer s.Close()
	// Simula destino remoto: o Guardian avalia o host da URL; usamos IP não-loopback fictício.
	e := Engine{"remoto", "openai", "http://192.0.2.10:1234"}
	if st := Probe(ctx, s.Client(), guardian.Policy{}, e, false); st.Presente || !st.Remoto {
		t.Fatalf("%+v", st)
	}
	_, err := Complete(ctx, s.Client(), guardian.Policy{}, e, false, "", "m", nil)
	var ae *Erro
	if !errors.As(err, &ae) || ae.Tipo != "politica" {
		t.Fatalf("%v", err)
	}
	if chamado {
		t.Fatal("nenhuma requisição deveria sair")
	}
}

func TestCompleteClassificaErros(t *testing.T) {
	casos := map[int]string{429: "limite", 503: "temporario", 401: "autenticacao", 403: "autenticacao", 418: "desconhecido"}
	for code, esperado := range casos {
		code := code
		s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { w.WriteHeader(code) }))
		_, err := Complete(ctx, s.Client(), guardian.Policy{}, Engine{"x", "openai", s.URL}, false, "", "m", nil)
		var ae *Erro
		if !errors.As(err, &ae) || ae.Tipo != esperado {
			t.Errorf("%d: %v", code, err)
		}
		s.Close()
	}
}

func TestCompletePoliticaPorCorpo(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(403)
		w.Write([]byte("content_policy"))
	}))
	defer s.Close()
	_, err := Complete(ctx, s.Client(), guardian.Policy{}, Engine{"x", "openai", s.URL}, false, "", "m", nil)
	if ae, ok := err.(*Erro); !ok || ae.Tipo != "politica" {
		t.Fatalf("%v", err)
	}
}

func TestCompleteSucessoOpenAIeOllamaEChaveNoCabecalho(t *testing.T) {
	var auth string
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		auth = r.Header.Get("Authorization")
		if strings.HasSuffix(r.URL.Path, "/api/chat") {
			w.Write([]byte(`{"message":{"role":"assistant","content":"olá do ollama"}}`))
			return
		}
		w.Write([]byte(`{"choices":[{"message":{"role":"assistant","content":"olá do openai"}}]}`))
	}))
	defer s.Close()
	m := []Msg{{"user", "oi"}}
	got, err := Complete(ctx, s.Client(), guardian.Policy{}, Engine{"x", "openai", s.URL}, false, "sk-TESTE", "m", m)
	if err != nil || got != "olá do openai" || auth != "Bearer sk-TESTE" {
		t.Fatalf("%q %v %q", got, err, auth)
	}
	got, err = Complete(ctx, s.Client(), guardian.Policy{}, Engine{"o", "ollama", s.URL}, false, "", "m", m)
	if err != nil || got != "olá do ollama" {
		t.Fatalf("%q %v", got, err)
	}
}

func TestFalhaDeRede(t *testing.T) {
	_, err := Complete(ctx, &http.Client{}, guardian.Policy{}, Engine{"x", "openai", "http://127.0.0.1:1"}, false, "", "m", nil)
	if ae, ok := err.(*Erro); !ok || ae.Tipo != "rede" {
		t.Fatalf("%v", err)
	}
}

func TestAceleradoresSoCpuQuandoNadaEncontrado(t *testing.T) {
	a := Aceleradores(func(string) (string, error) { return "", errors.New("x") })
	if len(a) != 1 || a[0] != "cpu" {
		t.Fatalf("%v", a)
	}
	a = Aceleradores(func(n string) (string, error) {
		if n == "vulkaninfo" {
			return "/x", nil
		}
		return "", errors.New("x")
	})
	if len(a) != 2 || !strings.HasPrefix(a[1], "vulkan") {
		t.Fatalf("%v", a)
	}
}
