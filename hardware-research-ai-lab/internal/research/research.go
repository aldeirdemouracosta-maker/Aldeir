// Package research implementa o research-engine (Fase 0): cadastro, consulta e
// validação de fontes. Análise de commits/issues é planejada para a Fase 1.
package research

import (
	"encoding/json"
	"fmt"
	"net/url"
	"sort"
	"strings"

	"hrail/internal/storage"
)

// Verificação de uma fonte.
const (
	NaoVerificado = "nao_verificado"
	Verificado    = "verificado"
)

type Verification struct {
	Status    string  `json:"status"`
	CheckedAt *string `json:"checked_at"`
	Note      string  `json:"note,omitempty"`
}

// Source é uma fonte do catálogo de pesquisa.
type Source struct {
	ID                  string       `json:"id"`
	Name                string       `json:"name"`
	URL                 string       `json:"url"`
	HostKind            string       `json:"host_kind"` // github | gitlab | web
	Kind                string       `json:"kind"`
	License             string       `json:"license"`
	LicenseVerified     bool         `json:"license_verified"`
	Architectures       []string     `json:"architectures"`
	Purpose             string       `json:"purpose"`
	MaintenanceState    string       `json:"maintenance_state"`
	LastCommitConsulted *string      `json:"last_commit_consulted"`
	Limitations         []string     `json:"limitations"`
	Applications        []string     `json:"applications"`
	Trust               string       `json:"trust"`
	AllowExecution      bool         `json:"allow_execution"`
	Verification        Verification `json:"verification"`
}

type file struct {
	SchemaVersion int      `json:"schema_version"`
	Sources       []Source `json:"sources"`
}

// ParseCatalog carrega e valida o catálogo; devolve erro agregando todos os problemas.
func ParseCatalog(b []byte) ([]Source, error) {
	var f file
	if err := json.Unmarshal(b, &f); err != nil {
		return nil, fmt.Errorf("catálogo de fontes inválido: %w", err)
	}
	if probs := ValidateAll(f.Sources); len(probs) > 0 {
		return f.Sources, fmt.Errorf("catálogo de fontes com %d problema(s):\n  - %s", len(probs), strings.Join(probs, "\n  - "))
	}
	return f.Sources, nil
}

// Validate devolve os problemas de uma fonte (vazio = válida).
func Validate(s Source) []string {
	var p []string
	req := map[string]string{"id": s.ID, "name": s.Name, "url": s.URL, "kind": s.Kind, "license": s.License,
		"purpose": s.Purpose, "maintenance_state": s.MaintenanceState, "trust": s.Trust}
	var keys []string
	for k := range req {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	for _, k := range keys {
		if strings.TrimSpace(req[k]) == "" {
			p = append(p, fmt.Sprintf("%s: campo %q vazio", idOr(s), k))
		}
	}
	u, err := url.Parse(s.URL)
	switch {
	case err != nil || u.Host == "":
		p = append(p, fmt.Sprintf("%s: URL inválida %q", idOr(s), s.URL))
	case u.Scheme != "https":
		p = append(p, fmt.Sprintf("%s: URL deve usar https", idOr(s)))
	default:
		host := strings.ToLower(u.Hostname())
		switch s.HostKind {
		case "github":
			if host != "github.com" {
				p = append(p, fmt.Sprintf("%s: host_kind=github mas host=%s", idOr(s), host))
			}
		case "gitlab":
			if host != "gitlab.freedesktop.org" && host != "gitlab.com" {
				p = append(p, fmt.Sprintf("%s: host_kind=gitlab mas host=%s", idOr(s), host))
			}
		case "web":
		default:
			p = append(p, fmt.Sprintf("%s: host_kind %q desconhecido", idOr(s), s.HostKind))
		}
	}
	if s.AllowExecution {
		p = append(p, idOr(s)+": allow_execution=true é proibido na Fase 0 (nenhum código de terceiros é executado)")
	}
	switch s.Verification.Status {
	case NaoVerificado:
		if s.LastCommitConsulted != nil {
			p = append(p, idOr(s)+": last_commit_consulted preenchido sem verificação")
		}
	case Verificado:
		if s.Verification.CheckedAt == nil || s.LastCommitConsulted == nil && s.HostKind != "web" {
			p = append(p, idOr(s)+": fonte 'verificado' exige checked_at e (para repositórios) last_commit_consulted")
		}
	default:
		p = append(p, fmt.Sprintf("%s: verification.status %q inválido", idOr(s), s.Verification.Status))
	}
	if !s.LicenseVerified && s.Verification.Status == Verificado {
		p = append(p, idOr(s)+": fonte verificada com licença não verificada")
	}
	return p
}

func idOr(s Source) string {
	if s.ID == "" {
		return "(sem id)"
	}
	return s.ID
}

// ValidateAll valida o conjunto, incluindo unicidade de id e URL.
func ValidateAll(ss []Source) []string {
	var p []string
	ids, urls := map[string]bool{}, map[string]bool{}
	for _, s := range ss {
		p = append(p, Validate(s)...)
		if ids[s.ID] {
			p = append(p, "id duplicado: "+s.ID)
		}
		if urls[s.URL] {
			p = append(p, "URL duplicada: "+s.URL)
		}
		ids[s.ID], urls[s.URL] = true, true
	}
	return p
}

// Filter devolve as fontes de um tipo (kind); vazio devolve todas.
func Filter(ss []Source, kind string) []Source {
	if kind == "" {
		return ss
	}
	var out []Source
	for _, s := range ss {
		if s.Kind == kind {
			out = append(out, s)
		}
	}
	return out
}

// Find busca por id.
func Find(ss []Source, id string) (Source, bool) {
	for _, s := range ss {
		if s.ID == id {
			return s, true
		}
	}
	return Source{}, false
}

// Save grava (upsert) as fontes no banco.
func Save(db *storage.DB, ss []Source) error {
	for _, s := range ss {
		b, _ := json.Marshal(s)
		lc := ""
		if s.LastCommitConsulted != nil {
			lc = *s.LastCommitConsulted
		}
		_, err := db.SQL().Exec(`INSERT INTO sources(id,name,url,kind,license,verification,last_commit_consulted,payload_json)
			VALUES(?,?,?,?,?,?,NULLIF(?,''),?)
			ON CONFLICT(id) DO UPDATE SET name=excluded.name,url=excluded.url,kind=excluded.kind,
			license=excluded.license,verification=excluded.verification,
			last_commit_consulted=excluded.last_commit_consulted,payload_json=excluded.payload_json`,
			s.ID, s.Name, s.URL, s.Kind, s.License, s.Verification.Status, lc, string(b))
		if err != nil {
			return err
		}
	}
	return nil
}

// Load lê as fontes do banco.
func Load(db *storage.DB) ([]Source, error) {
	rows, err := db.SQL().Query(`SELECT payload_json FROM sources ORDER BY id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Source
	for rows.Next() {
		var s string
		var src Source
		if err := rows.Scan(&s); err != nil {
			return nil, err
		}
		if err := json.Unmarshal([]byte(s), &src); err != nil {
			return nil, err
		}
		out = append(out, src)
	}
	return out, rows.Err()
}
