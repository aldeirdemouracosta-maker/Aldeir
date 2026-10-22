package simulation

import (
	"archive/tar"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"

	"hrail/internal/gitscan"
	"hrail/internal/security"
	"hrail/internal/storage"
)

// SimDef é a definição FIXADA de um simulador (catalog/simulators.json).
type SimDef struct {
	ID           string               `json:"id"`
	SourceID     string               `json:"source_id"`
	PinnedCommit string               `json:"pinned_commit"`
	PinnedBy     string               `json:"pinned_by"`
	Model        ModelDef             `json:"model"`
	FixedFlags   []string             `json:"fixed_flags"`
	Samples      map[string]SampleDef `json:"samples"`
	ManualReview []string             `json:"manual_review"`
	Reviewer     string               `json:"reviewer"`
}

type ModelDef struct {
	Arch string `json:"arch"`
	GPU  string `json:"gpu"`
	Note string `json:"note"`
}

type SampleDef struct {
	Package string             `json:"package"`
	Flags   map[string]FlagDef `json:"flags"`
}

type FlagDef struct {
	Default int `json:"default"`
	Max     int `json:"max"`
}

var (
	reCommit   = regexp.MustCompile(`^[0-9a-f]{40}$`)
	reFlagName = regexp.MustCompile(`^[a-z][a-z-]*$`)
	reToolchn  = regexp.MustCompile(`^go1\.[0-9]+(\.[0-9]+)?$`)
	forbidden  = []string{"trace", "buffer-level", "debug-isa", "akitartm", "monitor", "daisen", "analyzer", "metric-file-name"}
)

// ParseSimulators valida o catálogo de simuladores.
func ParseSimulators(b []byte) ([]SimDef, error) {
	var f struct {
		Simulators []SimDef `json:"simulators"`
	}
	if err := json.Unmarshal(b, &f); err != nil {
		return nil, fmt.Errorf("catálogo de simuladores inválido: %w", err)
	}
	for _, s := range f.Simulators {
		if s.ID == "" || !reCommit.MatchString(s.PinnedCommit) {
			return nil, fmt.Errorf("%s: pinned_commit deve ser um hash completo de 40 caracteres", s.ID)
		}
		rtm := false
		for _, fl := range s.FixedFlags {
			rtm = rtm || fl == "-disable-rtm"
			for _, bad := range forbidden {
				if strings.Contains(fl, bad) {
					return nil, fmt.Errorf("%s: flag fixa proibida %q", s.ID, fl)
				}
			}
		}
		if !rtm {
			return nil, fmt.Errorf("%s: -disable-rtm é obrigatório nas flags fixas (portal HTTP ligado por padrão)", s.ID)
		}
		for name, sm := range s.Samples {
			if !strings.HasPrefix(sm.Package, "./amd/samples/") || strings.Contains(sm.Package, "..") {
				return nil, fmt.Errorf("%s/%s: pacote fora de ./amd/samples/", s.ID, name)
			}
			for fn, fd := range sm.Flags {
				if !reFlagName.MatchString(fn) || fd.Max <= 0 || fd.Default <= 0 || fd.Default > fd.Max {
					return nil, fmt.Errorf("%s/%s: flag %q inválida", s.ID, name, fn)
				}
				for _, bad := range forbidden {
					if strings.Contains(fn, bad) {
						return nil, fmt.Errorf("%s/%s: flag %q proibida", s.ID, name, fn)
					}
				}
			}
		}
	}
	return f.Simulators, nil
}

// Erros de portão de segurança.
var (
	ErrNaoAprovado = errors.New("código de terceiros sem aprovação humana para esta revisão (rode 'hrail simulation revisar' e 'hrail simulation aprovar')")
	ErrSemBuild    = errors.New("binário não compilado/verificado (rode 'hrail simulation compilar')")
)

// Manager coordena preparo, revisão, compilação e execução de um simulador de terceiros.
type Manager struct {
	Root   string
	Def    SimDef
	Runner *security.Runner
	DB     *storage.DB
}

func (m *Manager) base() string   { return filepath.Join(m.Root, "data", "_sim", m.Def.ID) }
func (m *Manager) src() string    { return filepath.Join(m.base(), "src") }
func (m *Manager) bin() string    { return filepath.Join(m.base(), "bin") }
func (m *Manager) clone() string  { return filepath.Join(m.Root, "data", "clones", m.Def.SourceID) }
func (m *Manager) marker() string { return filepath.Join(m.src(), ".hrail-source") }

func gitArgs(a ...string) []string { return append(append([]string{}, gitscan.GitSafeArgs...), a...) }

// Prepare extrai o código do commit FIXADO (git archive, sem .git, sem hooks) para data/_sim.
func (m *Manager) Prepare(ctx context.Context) (string, error) {
	if b, err := os.ReadFile(m.marker()); err == nil && strings.TrimSpace(string(b)) == m.Def.PinnedCommit {
		return "já preparado em " + m.src(), nil
	}
	if _, err := os.Stat(filepath.Join(m.clone(), ".git")); err != nil {
		return "", fmt.Errorf("clone de %q ausente; rode 'hrail research verificar --online --clonar --id %s'", m.Def.SourceID, m.Def.SourceID)
	}
	res, err := m.Runner.Run(ctx, "git", gitArgs("-C", m.clone(), "cat-file", "-e", m.Def.PinnedCommit+"^{commit}")...)
	if err != nil || res.ExitCode != 0 {
		return "", fmt.Errorf("commit fixado %s não existe no clone local; reclone com maior --profundidade", m.Def.PinnedCommit[:12])
	}
	if err := os.RemoveAll(m.src()); err != nil {
		return "", err
	}
	if err := os.MkdirAll(m.src(), 0o755); err != nil {
		return "", err
	}
	tmp := filepath.Join(m.base(), "src.tar")
	defer os.Remove(tmp)
	res, err = m.Runner.RunWith(ctx, 10*time.Minute, "git", gitArgs("-C", m.clone(), "archive", "--format=tar", "-o", tmp, m.Def.PinnedCommit)...)
	if err != nil || res.ExitCode != 0 {
		return "", fmt.Errorf("git archive falhou: %v %s", err, strings.TrimSpace(res.Stderr))
	}
	n, skipped, err := extractTar(tmp, m.src())
	if err != nil {
		return "", err
	}
	if err := os.WriteFile(m.marker(), []byte(m.Def.PinnedCommit+"\n"), 0o644); err != nil {
		return "", err
	}
	return fmt.Sprintf("%d arquivos extraídos (%d itens não regulares ignorados) em %s", n, skipped, m.src()), nil
}

// extractTar extrai apenas diretórios e arquivos regulares, recusando caminhos que escapem do destino.
func extractTar(tarPath, dest string) (files, skipped int, err error) {
	f, err := os.Open(tarPath)
	if err != nil {
		return 0, 0, err
	}
	defer f.Close()
	tr := tar.NewReader(f)
	for {
		h, err := tr.Next()
		if err == io.EOF {
			return files, skipped, nil
		}
		if err != nil {
			return files, skipped, err
		}
		p, err := security.ConfinePath(dest, h.Name)
		if err != nil {
			return files, skipped, fmt.Errorf("entrada suspeita no arquivo: %w", err)
		}
		switch h.Typeflag {
		case tar.TypeDir:
			if err := os.MkdirAll(p, 0o755); err != nil {
				return files, skipped, err
			}
		case tar.TypeReg:
			if err := os.MkdirAll(filepath.Dir(p), 0o755); err != nil {
				return files, skipped, err
			}
			mode := os.FileMode(0o644)
			if h.Mode&0o111 != 0 {
				mode = 0o755
			}
			out, err := os.OpenFile(p, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, mode)
			if err != nil {
				return files, skipped, err
			}
			if _, err := io.Copy(out, tr); err != nil {
				out.Close()
				return files, skipped, err
			}
			out.Close()
			files++
		default: // symlinks, hardlinks, dispositivos: ignorados
			skipped++
		}
	}
}

func (m *Manager) toolchain() (string, error) {
	b, err := os.ReadFile(filepath.Join(m.src(), "go.mod"))
	if err != nil {
		return "", err
	}
	for _, ln := range strings.Split(string(b), "\n") {
		f := strings.Fields(ln)
		if len(f) == 2 && f[0] == "go" {
			tc := "go" + f[1]
			if !reToolchn.MatchString(tc) {
				return "", fmt.Errorf("versão de Go %q inesperada", f[1])
			}
			return tc, nil
		}
	}
	return "", errors.New("go.mod sem diretiva 'go'")
}

func (m *Manager) goEnv() ([]string, error) {
	tc, err := m.toolchain()
	if err != nil {
		return nil, err
	}
	gp := filepath.Join(m.base(), "gopath")
	return []string{"GOPATH=" + gp, "GOMODCACHE=" + filepath.Join(gp, "pkg", "mod"), "GOCACHE=" + filepath.Join(m.base(), "gocache"),
		"GOFLAGS=-mod=readonly", "GOTOOLCHAIN=" + tc, "CGO_ENABLED=0"}, nil
}

// Fingerprint identifica exatamente o que foi revisado/aprovado.
func (m *Manager) Fingerprint(sample string) (string, error) {
	sd, ok := m.Def.Samples[sample]
	if !ok {
		return "", fmt.Errorf("amostra %q não permitida (permitidas: %s)", sample, strings.Join(m.sampleNames(), ", "))
	}
	h := sha256.New()
	fmt.Fprintf(h, "%s\n%s\n%s\n%s\n", m.Def.PinnedCommit, sd.Package, strings.Join(m.Def.FixedFlags, " "), m.Def.Model.GPU)
	for _, f := range []string{"go.mod", "go.sum"} {
		b, err := os.ReadFile(filepath.Join(m.src(), f))
		if err != nil {
			return "", fmt.Errorf("código-fonte não preparado (%v)", err)
		}
		h.Write(b)
	}
	return hex.EncodeToString(h.Sum(nil)), nil
}

func (m *Manager) sampleNames() []string {
	var n []string
	for k := range m.Def.Samples {
		n = append(n, k)
	}
	sort.Strings(n)
	return n
}
