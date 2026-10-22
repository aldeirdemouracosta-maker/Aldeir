// Package security concentra as barreiras da Fase 0: execução de processos
// externos com timeout, registro de comandos e confinamento de caminhos.
package security

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"
)

// MaxOutputBytes limita a saída capturada de qualquer processo externo.
const MaxOutputBytes = 1 << 20

// ErrNotAllowed indica que o executável não está na lista permitida.
var ErrNotAllowed = errors.New("executável não permitido pela política de segurança")

// CommandRecord é o registro auditável de um comando executado.
// A saída do processo NÃO é registrada (pode conter dados pessoais).
type CommandRecord struct {
	Time     time.Time `json:"time"`
	Command  string    `json:"command"`
	Args     []string  `json:"args"`
	ExitCode int       `json:"exit_code"`
	Duration string    `json:"duration"`
	TimedOut bool      `json:"timed_out"`
	Error    string    `json:"error,omitempty"`
}

// Result é o resultado de uma execução.
type Result struct {
	Stdout   string
	Stderr   string
	ExitCode int
	TimedOut bool
	Record   CommandRecord
}

// Runner executa comandos externos sem shell, com timeout e auditoria.
type Runner struct {
	Timeout time.Duration
	// Allow restringe os executáveis (nome base). Vazio = sem restrição (apenas testes).
	Allow map[string]bool

	mu      sync.Mutex
	records []CommandRecord
	// OnRecord, se definido, recebe cada registro (ex.: persistência em SQLite).
	OnRecord func(CommandRecord)
}

// NewRunner cria um Runner com timeout padrão e lista permitida.
func NewRunner(timeout time.Duration, allow ...string) *Runner {
	r := &Runner{Timeout: timeout}
	if len(allow) > 0 {
		r.Allow = map[string]bool{}
		for _, a := range allow {
			r.Allow[a] = true
		}
	}
	return r
}

// Records devolve uma cópia dos comandos executados.
func (r *Runner) Records() []CommandRecord {
	r.mu.Lock()
	defer r.mu.Unlock()
	return append([]CommandRecord(nil), r.records...)
}

// LookPath resolve um executável respeitando a lista permitida.
func (r *Runner) LookPath(name string) (string, error) {
	if len(r.Allow) > 0 && !r.Allow[filepath.Base(name)] {
		return "", fmt.Errorf("%w: %s", ErrNotAllowed, name)
	}
	return exec.LookPath(name)
}

// Run executa name com args. Nunca usa shell nem sudo. Código de saída
// diferente de zero NÃO é erro de Go: fica em Result.ExitCode.
// Erro é retornado apenas se o processo não pôde ser iniciado.
func (r *Runner) Run(ctx context.Context, name string, args ...string) (Result, error) {
	rec := CommandRecord{Time: time.Now().UTC(), Command: name, Args: args, ExitCode: -1}
	finish := func(res Result, err error) (Result, error) {
		if err != nil {
			rec.Error = err.Error()
		}
		rec.ExitCode, rec.TimedOut = res.ExitCode, res.TimedOut
		res.Record = rec
		r.mu.Lock()
		r.records = append(r.records, rec)
		cb := r.OnRecord
		r.mu.Unlock()
		if cb != nil {
			cb(rec)
		}
		return res, err
	}
	start := time.Now()
	setDur := func() { rec.Duration = time.Since(start).Round(time.Millisecond).String() }

	if filepath.Base(name) == "sudo" || filepath.Base(name) == "su" {
		setDur()
		return finish(Result{ExitCode: -1}, fmt.Errorf("%w: elevação de privilégio é proibida", ErrNotAllowed))
	}
	path, err := r.LookPath(name)
	if err != nil {
		setDur()
		return finish(Result{ExitCode: -1}, err)
	}
	timeout := r.Timeout
	if timeout <= 0 {
		timeout = 10 * time.Second
	}
	cctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	cmd := exec.CommandContext(cctx, path, args...)
	cmd.Env = append(os.Environ(), "LC_ALL=C", "LANG=C")
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
	cmd.Cancel = func() error { return syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL) }
	cmd.WaitDelay = 500 * time.Millisecond
	var so, se limitedBuffer
	cmd.Stdout, cmd.Stderr = &so, &se

	runErr := cmd.Run()
	setDur()
	res := Result{Stdout: so.String(), Stderr: se.String()}
	switch {
	case cctx.Err() == context.DeadlineExceeded:
		res.TimedOut, res.ExitCode = true, -1
		return finish(res, fmt.Errorf("timeout de %s excedido: %s", timeout, name))
	case runErr == nil:
		res.ExitCode = 0
	default:
		var ee *exec.ExitError
		if errors.As(runErr, &ee) {
			res.ExitCode = ee.ExitCode()
			return finish(res, nil)
		}
		res.ExitCode = -1
		return finish(res, runErr)
	}
	return finish(res, nil)
}

type limitedBuffer struct{ b bytes.Buffer }

func (l *limitedBuffer) Write(p []byte) (int, error) {
	if room := MaxOutputBytes - l.b.Len(); room > 0 {
		if len(p) > room {
			l.b.Write(p[:room])
		} else {
			l.b.Write(p)
		}
	}
	return len(p), nil // descarta o excedente sem bloquear o processo
}
func (l *limitedBuffer) String() string { return l.b.String() }

// ConfinePath garante que p (relativo ou absoluto) resida dentro de root.
func ConfinePath(root, p string) (string, error) {
	if !filepath.IsAbs(p) {
		p = filepath.Join(root, p)
	}
	absRoot, err := filepath.Abs(root)
	if err != nil {
		return "", err
	}
	abs, err := filepath.Abs(p)
	if err != nil {
		return "", err
	}
	rel, err := filepath.Rel(absRoot, abs)
	if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return "", fmt.Errorf("caminho fora do projeto: %s", p)
	}
	return abs, nil
}
