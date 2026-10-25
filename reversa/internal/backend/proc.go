package backend

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os/exec"
	"time"
)

// Erros tipados: quem chama decide o que fazer com cada um (errors.Is).
var (
	ErrTimeout = errors.New("tempo esgotado")
	ErrExec    = errors.New("falha ao executar ferramenta")
)

const maxOutput = 16 << 10

// limitedBuffer guarda até max bytes e conta o que foi descartado, sem crescer sem limite.
type limitedBuffer struct {
	buf     bytes.Buffer
	max     int
	dropped int
}

func (l *limitedBuffer) Write(p []byte) (int, error) {
	if room := l.max - l.buf.Len(); room > 0 {
		n := min(room, len(p))
		l.buf.Write(p[:n])
		l.dropped += len(p) - n
	} else {
		l.dropped += len(p)
	}
	return len(p), nil // sempre consome tudo para o processo filho não travar no pipe
}

func (l *limitedBuffer) String() string {
	if l.dropped > 0 {
		return l.buf.String() + fmt.Sprintf("\n...[cortado: %d bytes omitidos]", l.dropped)
	}
	return l.buf.String()
}

// run executa um comando externo em grupo de processos próprio, com prazo e saída limitada.
// Ao estourar o prazo, o grupo inteiro é encerrado (inclusive netos), como a supervisão do REA faz.
func run(ctx context.Context, timeout time.Duration, name string, args ...string) (string, error) {
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	out, errb := &limitedBuffer{max: maxOutput}, &limitedBuffer{max: 4 << 10}
	cmd := exec.CommandContext(ctx, name, args...)
	cmd.Stdout, cmd.Stderr = out, errb
	cmd.WaitDelay = 2 * time.Second
	ownGroup(cmd)
	err := cmd.Run()
	if err != nil {
		if errors.Is(ctx.Err(), context.DeadlineExceeded) {
			return out.String(), fmt.Errorf("%s: %w após %s", name, ErrTimeout, timeout)
		}
		return out.String(), fmt.Errorf("%s: %w: %v: %s", name, ErrExec, err, errb.String())
	}
	return out.String(), nil
}
