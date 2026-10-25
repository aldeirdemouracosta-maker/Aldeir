//go:build unix

package backend

import (
	"context"
	"errors"
	"fmt"
	"os"
	"strconv"
	"strings"
	"syscall"
	"testing"
	"time"
)

func TestTimeoutMataOGrupoInteiro(t *testing.T) {
	start := time.Now()
	// o shell cria um neto que imprime o próprio pid e dorme
	out, err := run(context.Background(), 500*time.Millisecond, "sh", "-c", "sleep 60 & echo $!; wait")
	if !errors.Is(err, ErrTimeout) {
		t.Fatalf("esperava ErrTimeout, veio %v", err)
	}
	if time.Since(start) > 5*time.Second {
		t.Fatalf("demorou %s para encerrar", time.Since(start))
	}
	pid, perr := strconv.Atoi(strings.TrimSpace(out))
	if perr != nil {
		t.Fatalf("pid do neto ausente na saída %q", out)
	}
	time.Sleep(200 * time.Millisecond)
	if alive(pid) {
		t.Fatalf("neto %d continua vivo", pid)
	}
}

// alive trata zumbi como morto: o processo já foi encerrado, só falta o init recolhê-lo.
func alive(pid int) bool {
	if raw, err := os.ReadFile(fmt.Sprintf("/proc/%d/stat", pid)); err == nil {
		s := string(raw)
		if i := strings.LastIndex(s, ") "); i >= 0 && i+2 < len(s) {
			return s[i+2] != 'Z'
		}
	}
	return syscall.Kill(pid, 0) == nil
}

func TestSaidaLimitada(t *testing.T) {
	out, err := run(context.Background(), 10*time.Second, "sh", "-c", "head -c 100000 /dev/zero | tr '\\0' x")
	if err != nil {
		t.Fatal(err)
	}
	if len(out) > maxOutput+100 || !strings.Contains(out, "cortado") {
		t.Fatalf("saída não limitada: %d bytes", len(out))
	}
}

func TestErroDeExecucaoTipado(t *testing.T) {
	_, err := run(context.Background(), time.Second, "sh", "-c", "exit 3")
	if !errors.Is(err, ErrExec) {
		t.Fatalf("esperava ErrExec, veio %v", err)
	}
}
