package research

import (
	"context"
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"time"

	"hrail/internal/gitscan"
	"hrail/internal/security"
	"hrail/internal/storage"
)

// Result é o resultado de verificar uma fonte ONLINE (somente leitura).
type Result struct {
	SourceID        string `json:"source_id"`
	Status          string `json:"status"` // verificado | parcial | inacessivel
	CheckedAt       string `json:"checked_at"`
	HeadCommit      string `json:"head_commit,omitempty"`
	HeadDate        string `json:"head_date,omitempty"`
	LicenseDetected string `json:"license_detected,omitempty"`
	LicenseMatches  *bool  `json:"license_matches,omitempty"`
	HTTPStatus      int    `json:"http_status,omitempty"`
	Note            string `json:"note"`
}

// Verifier confirma existência e estado de fontes. Nenhum código do repositório é
// executado: usa-se `ls-remote` e clone raso parcial SEM checkout (sem hooks/filtros).
type Verifier struct {
	Runner     *security.Runner
	CloneDir   string
	Depth      int
	NetTimeout time.Duration
	HTTP       *http.Client
	// RemoteURL permite redirecionar a URL consultada (testes com repositórios locais).
	RemoteURL func(Source) string
}

func (v Verifier) url(s Source) string {
	if v.RemoteURL != nil {
		return v.RemoteURL(s)
	}
	return s.URL
}

func (v Verifier) git(ctx context.Context, args ...string) (security.Result, error) {
	to := v.NetTimeout
	if to <= 0 {
		to = 90 * time.Second
	}
	return v.Runner.RunWith(ctx, to, "git", append(append([]string{}, gitscan.GitSafeArgs...), args...)...)
}

// Verify consulta a fonte. Para repositórios, clone=true também obtém data do último commit e licença.
func (v Verifier) Verify(ctx context.Context, s Source, clone bool) Result {
	r := Result{SourceID: s.ID, Status: "inacessivel", CheckedAt: time.Now().UTC().Format(time.RFC3339)}
	if s.HostKind == "web" {
		return v.verifyWeb(ctx, s, r)
	}
	res, err := v.git(ctx, "ls-remote", v.url(s), "HEAD")
	if err != nil || res.ExitCode != 0 {
		r.Note = "inacessível: " + oneLine(res.Stderr, err)
		return r
	}
	f := strings.Fields(res.Stdout)
	if len(f) < 2 || !gitscan.ValidateHash(f[0]) {
		r.Note = "ls-remote sem HEAD reconhecível (repositório vazio ou URL não é repositório Git)"
		return r
	}
	r.HeadCommit, r.Status = strings.ToLower(f[0]), Parcial
	r.Note = "existe e responde; histórico e licença não consultados (use --clonar)"
	if !clone {
		return r
	}
	dir := filepath.Join(v.CloneDir, s.ID)
	depth := v.Depth
	if depth <= 0 {
		depth = 200
	}
	if _, err := os.Stat(filepath.Join(dir, ".git")); err == nil {
		res, err = v.git(ctx, "-C", dir, "fetch", "-q", "--depth", fmt.Sprint(depth), "--filter=blob:none", "origin", "HEAD")
	} else {
		if err := os.MkdirAll(v.CloneDir, 0o755); err != nil {
			r.Note = "não foi possível criar o diretório de clones: " + err.Error()
			return r
		}
		res, err = v.git(ctx, "clone", "-q", "--depth", fmt.Sprint(depth), "--filter=blob:none", "--no-checkout", "--single-branch", v.url(s), dir)
	}
	if err != nil || res.ExitCode != 0 {
		r.Note = "clone raso falhou: " + oneLine(res.Stderr, err)
		return r
	}
	lg, err := v.Runner.Run(ctx, "git", append(append([]string{}, gitscan.GitSafeArgs...), "-C", dir, "log", "-1", "--format=%H%x1f%cI", "FETCH_HEAD")...)
	if err != nil || lg.ExitCode != 0 {
		lg, err = v.Runner.Run(ctx, "git", append(append([]string{}, gitscan.GitSafeArgs...), "-C", dir, "log", "-1", "--format=%H%x1f%cI", "HEAD")...)
	}
	if err != nil || lg.ExitCode != 0 {
		r.Note = "clone ok, mas `git log` falhou: " + oneLine(lg.Stderr, err)
		return r
	}
	p := strings.Split(strings.TrimSpace(lg.Stdout), "\x1f")
	if len(p) != 2 {
		r.Note = "saída inesperada do git log"
		return r
	}
	r.HeadCommit, r.HeadDate, r.Status = strings.ToLower(p[0]), p[1], Verificado
	r.Note = fmt.Sprintf("clone raso (profundidade %d, sem checkout) em %s", depth, dir)
	if txt, name := v.licenseText(ctx, dir); txt != "" {
		r.LicenseDetected = DetectLicense(txt)
		if r.LicenseDetected != "" {
			m := LicenseMatches(s.License, r.LicenseDetected)
			if m != nil {
				r.LicenseMatches = m
			}
			if m != nil && !*m {
				r.Note += fmt.Sprintf("; ATENÇÃO: licença detectada em %s (%s) difere da declarada no catálogo (%s)", name, r.LicenseDetected, s.License)
			}
		} else {
			r.Note += "; arquivo " + name + " encontrado, licença não reconhecida automaticamente (revisão humana)"
		}
	} else {
		r.Note += "; arquivo de licença não encontrado no topo do repositório"
	}
	r.Note += "; dono/organização oficial NÃO é confirmado automaticamente"
	return r
}

func (v Verifier) licenseText(ctx context.Context, dir string) (string, string) {
	ls, err := v.Runner.Run(ctx, "git", append(append([]string{}, gitscan.GitSafeArgs...), "-C", dir, "ls-tree", "--name-only", "HEAD")...)
	if err != nil || ls.ExitCode != 0 {
		return "", ""
	}
	for _, n := range strings.Split(ls.Stdout, "\n") {
		u := strings.ToUpper(strings.TrimSpace(n))
		if strings.HasPrefix(u, "LICENSE") || strings.HasPrefix(u, "LICENCE") || strings.HasPrefix(u, "COPYING") {
			// obtém o blob sob demanda (clone parcial) — somente leitura
			sh, err := v.git(ctx, "-C", dir, "show", "HEAD:"+strings.TrimSpace(n))
			if err == nil && sh.ExitCode == 0 {
				return sh.Stdout, strings.TrimSpace(n)
			}
		}
	}
	return "", ""
}

func (v Verifier) verifyWeb(ctx context.Context, s Source, r Result) Result {
	c := v.HTTP
	if c == nil {
		c = &http.Client{Timeout: 20 * time.Second}
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodHead, v.url(s), nil)
	if err != nil {
		r.Note = err.Error()
		return r
	}
	req.Header.Set("User-Agent", "hrail-verificador/fase1")
	resp, err := c.Do(req)
	if err != nil {
		r.Note = "inacessível: " + oneLine("", err)
		return r
	}
	resp.Body.Close()
	r.HTTPStatus = resp.StatusCode
	if resp.StatusCode >= 200 && resp.StatusCode < 400 {
		r.Status, r.Note = Verificado, fmt.Sprintf("HTTP %d; existência confirmada (conteúdo e termos de uso não avaliados)", resp.StatusCode)
	} else {
		r.Note = fmt.Sprintf("HTTP %d", resp.StatusCode)
	}
	return r
}

func oneLine(stderr string, err error) string {
	s := strings.TrimSpace(stderr)
	if s == "" && err != nil {
		s = err.Error()
	}
	if i := strings.IndexByte(s, '\n'); i >= 0 {
		s = s[:i]
	}
	if len(s) > 200 {
		s = s[:200]
	}
	return s
}

// DetectLicense reconhece, de forma conservadora, licenças comuns. Vazio = não reconhecida.
func DetectLicense(text string) string {
	t := strings.ToLower(text)
	has := func(ss ...string) bool {
		for _, s := range ss {
			if !strings.Contains(t, s) {
				return false
			}
		}
		return true
	}
	switch {
	case has("apache license", "version 2.0"):
		return "Apache-2.0"
	case has("gnu general public license", "version 3"):
		return "GPL-3.0"
	case has("gnu general public license", "version 2"):
		return "GPL-2.0"
	case has("mozilla public license", "2.0"):
		return "MPL-2.0"
	case has("redistribution and use in source and binary forms", "neither the name"):
		return "BSD-3-Clause"
	case has("redistribution and use in source and binary forms"):
		return "BSD-2-Clause"
	case has("permission is hereby granted, free of charge") && has("the software is provided \"as is\""):
		return "MIT"
	}
	return ""
}

// LicenseMatches compara a licença declarada no catálogo com a detectada.
// nil = não comparável (nada declarado ou desconhecida).
func LicenseMatches(declared, detected string) *bool {
	d := strings.ToLower(declared)
	if detected == "" || strings.TrimSpace(d) == "" || strings.HasPrefix(d, "desconhecida") || strings.HasPrefix(d, "não aplic") {
		return nil
	}
	m := strings.Contains(d, strings.ToLower(detected))
	return &m
}

// SaveVerification grava (upsert) o resultado.
func SaveVerification(db *storage.DB, r Result) error {
	var m any
	if r.LicenseMatches != nil {
		if *r.LicenseMatches {
			m = 1
		} else {
			m = 0
		}
	}
	_, err := db.SQL().Exec(`INSERT INTO source_verifications(source_id,status,checked_at,head_commit,head_date,license_detected,license_matches,http_status,note)
		VALUES(?,?,?,NULLIF(?,''),NULLIF(?,''),NULLIF(?,''),?,NULLIF(?,0),?)
		ON CONFLICT(source_id) DO UPDATE SET status=excluded.status,checked_at=excluded.checked_at,head_commit=excluded.head_commit,
		head_date=excluded.head_date,license_detected=excluded.license_detected,license_matches=excluded.license_matches,
		http_status=excluded.http_status,note=excluded.note`,
		r.SourceID, r.Status, r.CheckedAt, r.HeadCommit, r.HeadDate, r.LicenseDetected, m, r.HTTPStatus, r.Note)
	return err
}

// LoadVerifications lê os resultados gravados, por id de fonte.
func LoadVerifications(db *storage.DB) (map[string]Result, error) {
	rows, err := db.SQL().Query(`SELECT source_id,status,checked_at,COALESCE(head_commit,''),COALESCE(head_date,''),COALESCE(license_detected,''),license_matches,COALESCE(http_status,0),note FROM source_verifications`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := map[string]Result{}
	for rows.Next() {
		var r Result
		var m *int
		if err := rows.Scan(&r.SourceID, &r.Status, &r.CheckedAt, &r.HeadCommit, &r.HeadDate, &r.LicenseDetected, &m, &r.HTTPStatus, &r.Note); err != nil {
			return nil, err
		}
		if m != nil {
			b := *m == 1
			r.LicenseMatches = &b
		}
		out[r.SourceID] = r
	}
	return out, rows.Err()
}

// Overlay aplica resultados de verificação sobre o catálogo estático (sem alterá-lo).
// Fonte inacessível permanece nao_verificado, com a nota da última tentativa.
func Overlay(ss []Source, vs map[string]Result) []Source {
	out := make([]Source, len(ss))
	copy(out, ss)
	for i := range out {
		r, ok := vs[out[i].ID]
		if !ok {
			continue
		}
		at := r.CheckedAt
		v := Verification{Status: NaoVerificado, CheckedAt: nil, Note: "última tentativa em " + at + ": " + r.Note}
		switch r.Status {
		case Verificado, Parcial:
			v.Status, v.CheckedAt, v.Note = r.Status, &at, r.Note
			if r.HeadCommit != "" {
				lc := r.HeadCommit
				if r.HeadDate != "" {
					lc += " (" + r.HeadDate + ")"
				}
				out[i].LastCommitConsulted = &lc
			}
		}
		if r.Status == Verificado && r.HeadDate != "" {
			out[i].MaintenanceState = maintenance(r.HeadDate, r.CheckedAt)
		}
		if r.LicenseMatches != nil && *r.LicenseMatches {
			out[i].LicenseVerified = true
		}
		out[i].Verification = v
	}
	return out
}

// maintenance deriva um rótulo do último commit visível; é uma heurística, não um veredito.
func maintenance(headDate, checkedAt string) string {
	h, err1 := time.Parse(time.RFC3339, headDate)
	c, err2 := time.Parse(time.RFC3339, checkedAt)
	if err1 != nil || err2 != nil {
		return "desconhecido"
	}
	days := int(c.Sub(h).Hours() / 24)
	label := "ativo"
	if days > 180 {
		label = "possivelmente inativo"
	}
	return fmt.Sprintf("%s (último commit há %d dias, em %s; heurística)", label, days, h.Format("2006-01-02"))
}
