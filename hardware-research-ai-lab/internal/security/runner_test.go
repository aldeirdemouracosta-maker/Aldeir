package security

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"
)

func TestRunnerSucessoERegistro(t *testing.T) {
	r := NewRunner(5 * time.Second)
	res, err := r.Run(context.Background(), "echo", "olá")
	if err != nil || res.ExitCode != 0 || !strings.Contains(res.Stdout, "olá") {
		t.Fatalf("res=%+v err=%v", res, err)
	}
	recs := r.Records()
	if len(recs) != 1 || recs[0].Command != "echo" || recs[0].ExitCode != 0 {
		t.Fatalf("registro inesperado: %+v", recs)
	}
}

func TestRunnerCodigoDeSaidaNaoZero(t *testing.T) {
	r := NewRunner(5 * time.Second)
	res, err := r.Run(context.Background(), "sh", "-c", "exit 7")
	if err != nil || res.ExitCode != 7 {
		t.Fatalf("esperava exit 7 sem erro: %+v %v", res, err)
	}
	if r.Records()[0].ExitCode != 7 {
		t.Fatal("código de saída não registrado")
	}
}

func TestRunnerTimeoutMataGrupoDeProcessos(t *testing.T) {
	r := NewRunner(300 * time.Millisecond)
	start := time.Now()
	res, err := r.Run(context.Background(), "sh", "-c", "sleep 30 & sleep 30")
	if err == nil || !res.TimedOut {
		t.Fatalf("esperava timeout: res=%+v err=%v", res, err)
	}
	if time.Since(start) > 5*time.Second {
		t.Fatal("timeout não interrompeu o processo a tempo")
	}
	if !r.Records()[0].TimedOut {
		t.Fatal("timeout não registrado")
	}
}

func TestRunnerExecutavelInexistente(t *testing.T) {
	r := NewRunner(time.Second)
	res, err := r.Run(context.Background(), "hrail-nao-existe-xyz")
	if err == nil || res.ExitCode != -1 {
		t.Fatalf("esperava erro: %+v %v", res, err)
	}
	if len(r.Records()) != 1 || r.Records()[0].Error == "" {
		t.Fatal("falha deve ser registrada")
	}
}

func TestRunnerListaPermitidaEBloqueioDeSudo(t *testing.T) {
	r := NewRunner(time.Second, "echo")
	if _, err := r.Run(context.Background(), "ls"); !errors.Is(err, ErrNotAllowed) {
		t.Fatalf("ls deveria ser negado: %v", err)
	}
	open := NewRunner(time.Second)
	if _, err := open.Run(context.Background(), "sudo", "true"); !errors.Is(err, ErrNotAllowed) {
		t.Fatalf("sudo deveria ser sempre negado: %v", err)
	}
}

func TestRunnerLimitaSaida(t *testing.T) {
	r := NewRunner(10 * time.Second)
	res, err := r.Run(context.Background(), "sh", "-c", "head -c 3000000 /dev/zero | tr '\\0' a")
	if err != nil || len(res.Stdout) != MaxOutputBytes {
		t.Fatalf("len=%d err=%v", len(res.Stdout), err)
	}
}

func TestConfinePath(t *testing.T) {
	if _, err := ConfinePath("/proj", "data/x.db"); err != nil {
		t.Fatal(err)
	}
	for _, bad := range []string{"../fora", "/etc/passwd", "a/../../fora"} {
		if _, err := ConfinePath("/proj", bad); err == nil {
			t.Errorf("%q deveria ser recusado", bad)
		}
	}
}
