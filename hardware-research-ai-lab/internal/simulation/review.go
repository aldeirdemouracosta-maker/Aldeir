package simulation

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"hrail/internal/storage"
)

// RiskyImport registra um pacote que importa algo sensível.
type RiskyImport struct {
	Package string   `json:"package"`
	Imports []string `json:"imports"`
	CGO     bool     `json:"cgo,omitempty"`
}

// Review é o relatório de revisão AUTOMATIZADA por padrões. Não substitui auditoria.
type Review struct {
	Simulator   string        `json:"simulator"`
	Sample      string        `json:"sample"`
	Commit      string        `json:"commit"`
	Fingerprint string        `json:"fingerprint"`
	Toolchain   string        `json:"toolchain"`
	ReviewedAt  string        `json:"reviewed_at"`
	Packages    int           `json:"packages_non_std"`
	Modules     []string      `json:"modules"`
	Risky       []RiskyImport `json:"risky_imports"`
	Replaces    []string      `json:"replace_directives"`
	ManualNotes []string      `json:"manual_review"`
	Reviewer    string        `json:"reviewer"`
	Limitations []string      `json:"limitations"`
	ApprovedBy  string        `json:"approved_by,omitempty"`
	ApprovedAt  string        `json:"approved_at,omitempty"`
}

var riskySet = map[string]bool{"os/exec": true, "net": true, "net/http": true, "plugin": true, "unsafe": true, "syscall": true, "net/rpc": true, "crypto/tls": true}

// ParseDeps interpreta a saída de `go list -deps -f '{{ImportPath}} :: {{Imports}} :: {{len CgoFiles}} :: {{Module}}'`.
func ParseDeps(out string) (pkgs int, risky []RiskyImport, modules []string) {
	mods := map[string]bool{}
	for _, ln := range strings.Split(out, "\n") {
		p := strings.Split(strings.TrimSpace(ln), " :: ")
		if len(p) != 4 || p[0] == "" {
			continue
		}
		pkgs++
		var hit []string
		for _, i := range strings.Fields(p[1]) {
			if riskySet[i] {
				hit = append(hit, i)
			}
		}
		cgo := p[2] != "0"
		if len(hit) > 0 || cgo {
			risky = append(risky, RiskyImport{Package: p[0], Imports: hit, CGO: cgo})
		}
		if m := strings.TrimSpace(p[3]); m != "" {
			mods[m] = true
		}
	}
	for m := range mods {
		modules = append(modules, m)
	}
	sort.Strings(modules)
	return
}

// Review executa `go list` (não compila nem executa o código) e registra a revisão.
func (m *Manager) Review(ctx context.Context, sample string) (Review, error) {
	fp, err := m.Fingerprint(sample)
	if err != nil {
		return Review{}, err
	}
	env, err := m.goEnv()
	if err != nil {
		return Review{}, err
	}
	tc, _ := m.toolchain()
	sd := m.Def.Samples[sample]
	res, err := m.Runner.RunSpec(ctx, specNet(m.src(), env, 10*time.Minute), "go", "list", "-deps", "-f",
		`{{if not .Standard}}{{.ImportPath}} :: {{join .Imports " "}} :: {{len .CgoFiles}} :: {{with .Module}}{{.Path}}@{{.Version}}{{end}}{{end}}`, sd.Package)
	if err != nil || res.ExitCode != 0 {
		return Review{}, fmt.Errorf("go list falhou: %v %s", err, tail(res.Stderr))
	}
	pk, risky, mods := ParseDeps(res.Stdout)
	rv := Review{Simulator: m.Def.ID, Sample: sample, Commit: m.Def.PinnedCommit, Fingerprint: fp, Toolchain: tc,
		ReviewedAt: storage.Now(), Packages: pk, Modules: mods, Risky: risky, ManualNotes: m.Def.ManualReview, Reviewer: m.Def.Reviewer,
		Limitations: []string{"Revisão por padrões de importação e leitura parcial; NÃO é auditoria completa do código.",
			"'go build' não executa código de dependências, mas o BINÁRIO resultante executa tudo que o simulador contém."}}
	gm, _ := os.ReadFile(filepath.Join(m.src(), "go.mod"))
	for _, ln := range strings.Split(string(gm), "\n") {
		if t := strings.TrimSpace(ln); strings.HasPrefix(t, "replace ") || strings.HasPrefix(t, "replace(") {
			rv.Replaces = append(rv.Replaces, t)
		}
	}
	return rv, m.saveReview(rv)
}

func tail(s string) string {
	s = strings.TrimSpace(s)
	if len(s) > 400 {
		s = s[len(s)-400:]
	}
	return s
}

func (m *Manager) saveReview(r Review) error {
	b, _ := json.Marshal(r)
	_, err := m.DB.SQL().Exec(`INSERT INTO third_party_reviews(simulator,sample,commit_hash,fingerprint,reviewed_at,summary_json)
		VALUES(?,?,?,?,?,?) ON CONFLICT(simulator,sample,fingerprint) DO UPDATE SET reviewed_at=excluded.reviewed_at, summary_json=excluded.summary_json`,
		r.Simulator, r.Sample, r.Commit, r.Fingerprint, r.ReviewedAt, string(b))
	return err
}

// LoadReview devolve a revisão da impressão digital atual, com o estado de aprovação.
func (m *Manager) LoadReview(sample string) (Review, error) {
	fp, err := m.Fingerprint(sample)
	if err != nil {
		return Review{}, err
	}
	var s string
	var by, at sql.NullString
	err = m.DB.SQL().QueryRow(`SELECT summary_json,approved_by,approved_at FROM third_party_reviews WHERE simulator=? AND sample=? AND fingerprint=?`,
		m.Def.ID, sample, fp).Scan(&s, &by, &at)
	if err == sql.ErrNoRows {
		return Review{}, fmt.Errorf("nenhuma revisão desta versão; rode 'hrail simulation revisar --amostra %s'", sample)
	}
	if err != nil {
		return Review{}, err
	}
	var r Review
	if err := json.Unmarshal([]byte(s), &r); err != nil {
		return Review{}, err
	}
	r.ApprovedBy, r.ApprovedAt = by.String, at.String
	return r, nil
}

// Approve registra a aprovação HUMANA da revisão atual. O commit informado deve ser o fixado.
func (m *Manager) Approve(sample, commit, by string) error {
	if strings.TrimSpace(by) == "" {
		return fmt.Errorf("informe quem aprova (--por)")
	}
	if commit != m.Def.PinnedCommit {
		return fmt.Errorf("commit informado não é o fixado (%s)", m.Def.PinnedCommit)
	}
	if _, err := m.LoadReview(sample); err != nil {
		return err
	}
	fp, _ := m.Fingerprint(sample)
	_, err := m.DB.SQL().Exec(`UPDATE third_party_reviews SET approved_by=?, approved_at=? WHERE simulator=? AND sample=? AND fingerprint=?`,
		by, storage.Now(), m.Def.ID, sample, fp)
	return err
}

// requireApproval é o portão: só passa se a revisão atual foi aprovada por alguém.
func (m *Manager) requireApproval(sample string) (Review, error) {
	r, err := m.LoadReview(sample)
	if err != nil {
		return r, err
	}
	if r.ApprovedBy == "" {
		return r, ErrNaoAprovado
	}
	return r, nil
}
