// Package tools implementa o tool-registry: catálogo, descoberta e verificação.
package tools

import (
	"context"
	"encoding/json"
	"fmt"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"

	"hrail/internal/security"
)

// Status é o estado de uma ferramenta.
type Status string

const (
	Disponivel   Status = "disponivel"
	Ausente      Status = "ausente"
	Incompativel Status = "incompativel"
	NaoTestado   Status = "nao_testado"
)

// Def é a definição estática de uma ferramenta (catalog/tools.json).
type Def struct {
	ID              string   `json:"id"`
	Name            string   `json:"name"`
	Category        string   `json:"category"`
	Kind            string   `json:"kind,omitempty"`
	Executables     []string `json:"executables"`
	ProbeFiles      []string `json:"probe_files,omitempty"`
	VersionArgs     []string `json:"version_args,omitempty"`
	VersionRegex    string   `json:"version_regex,omitempty"`
	MinVersion      string   `json:"min_version,omitempty"`
	License         string   `json:"license"`
	LicenseVerified bool     `json:"license_verified"`
	Purpose         string   `json:"purpose"`
	Required        bool     `json:"required"`
}

// Check é o resultado de verificar uma ferramenta.
type Check struct {
	Def       Def    `json:"def"`
	Status    Status `json:"status"`
	Path      string `json:"path,omitempty"`
	Version   string `json:"version,omitempty"`
	Detail    string `json:"detail,omitempty"`
	CheckedAt string `json:"checked_at,omitempty"`
}

type catalogFile struct {
	SchemaVersion int   `json:"schema_version"`
	Tools         []Def `json:"tools"`
}

// ParseCatalog valida e carrega o catálogo.
func ParseCatalog(b []byte) ([]Def, error) {
	var f catalogFile
	if err := json.Unmarshal(b, &f); err != nil {
		return nil, fmt.Errorf("catálogo de ferramentas inválido: %w", err)
	}
	seen := map[string]bool{}
	for _, d := range f.Tools {
		if d.ID == "" || d.Name == "" || d.Category == "" {
			return nil, fmt.Errorf("ferramenta com id/nome/categoria vazios: %+v", d)
		}
		if seen[d.ID] {
			return nil, fmt.Errorf("id de ferramenta duplicado: %s", d.ID)
		}
		seen[d.ID] = true
		if d.VersionRegex != "" {
			if _, err := regexp.Compile(d.VersionRegex); err != nil {
				return nil, fmt.Errorf("%s: version_regex inválido: %w", d.ID, err)
			}
		}
	}
	return f.Tools, nil
}

// Registry mantém as definições e verifica a disponibilidade.
type Registry struct {
	Defs   []Def
	Runner *security.Runner
}

// New cria o registro. O Runner deve ter lista permitida construída por AllowList.
func New(defs []Def, r *security.Runner) *Registry { return &Registry{Defs: defs, Runner: r} }

// AllowList devolve os executáveis do catálogo (única superfície executável).
func AllowList(defs []Def) []string {
	var a []string
	for _, d := range defs {
		a = append(a, d.Executables...)
	}
	return a
}

// List devolve as ferramentas sem executar nada (estado nao_testado).
func (r *Registry) List() []Check {
	out := make([]Check, 0, len(r.Defs))
	for _, d := range r.Defs {
		out = append(out, Check{Def: d, Status: NaoTestado})
	}
	return out
}

// CheckAll verifica todas as ferramentas.
func (r *Registry) CheckAll(ctx context.Context) []Check {
	out := make([]Check, 0, len(r.Defs))
	for _, d := range r.Defs {
		out = append(out, r.CheckOne(ctx, d))
	}
	return out
}

// CheckOne verifica uma ferramenta. Nunca falha: erros viram Detail.
func (r *Registry) CheckOne(ctx context.Context, d Def) Check {
	c := Check{Def: d, Status: NaoTestado, CheckedAt: time.Now().UTC().Format(time.RFC3339)}
	if d.Kind == "in-tree" {
		c.Detail = "componente interno do Mesa, sem binário independente; requer código-fonte"
		return c
	}
	for _, g := range d.ProbeFiles {
		if m, _ := filepath.Glob(g); len(m) > 0 {
			c.Status, c.Path = Disponivel, m[0]
			c.Detail = "detectado pela existência do arquivo (versão não consultada)"
			return c
		}
	}
	for _, exe := range d.Executables {
		p, err := r.Runner.LookPath(exe)
		if err != nil {
			continue
		}
		c.Path = p
		c.Status = Disponivel
		if len(d.VersionArgs) > 0 {
			res, err := r.Runner.Run(ctx, exe, d.VersionArgs...)
			switch {
			case err != nil:
				c.Status, c.Detail = NaoTestado, "falha ao consultar versão: "+err.Error()
			case res.ExitCode != 0:
				c.Detail = fmt.Sprintf("consulta de versão retornou código %d", res.ExitCode)
			default:
				c.Version = ExtractVersion(d.VersionRegex, res.Stdout+"\n"+res.Stderr)
				if c.Version == "" {
					c.Detail = "versão não reconhecida na saída"
				}
			}
		}
		if d.MinVersion != "" && c.Version != "" && c.Status == Disponivel {
			if CompareVersions(c.Version, d.MinVersion) < 0 {
				c.Status = Incompativel
				c.Detail = fmt.Sprintf("versão %s menor que a mínima %s", c.Version, d.MinVersion)
			}
		}
		return c
	}
	if len(d.Executables) > 0 || len(d.ProbeFiles) > 0 {
		c.Status = Ausente
		c.Detail = "não encontrado no PATH"
		if len(d.Executables) == 0 {
			c.Detail = "arquivo de manifesto não encontrado"
		}
	}
	return c
}

// ExtractVersion aplica o regex e devolve o primeiro grupo.
func ExtractVersion(re, out string) string {
	if re == "" {
		return ""
	}
	m := regexp.MustCompile(re).FindStringSubmatch(out)
	if len(m) < 2 {
		return ""
	}
	return strings.TrimSpace(m[1])
}

// CompareVersions compara versões numéricas pontuadas (prefixo "v" ignorado).
func CompareVersions(a, b string) int {
	pa, pb := nums(a), nums(b)
	for i := 0; i < len(pa) || i < len(pb); i++ {
		var x, y int
		if i < len(pa) {
			x = pa[i]
		}
		if i < len(pb) {
			y = pb[i]
		}
		if x != y {
			if x < y {
				return -1
			}
			return 1
		}
	}
	return 0
}

func nums(s string) []int {
	var out []int
	for _, p := range strings.Split(strings.TrimPrefix(s, "v"), ".") {
		n, err := strconv.Atoi(strings.TrimFunc(p, func(r rune) bool { return r < '0' || r > '9' }))
		if err != nil {
			break
		}
		out = append(out, n)
	}
	return out
}

// Adapter é a interface comum para adaptadores externos (adapters/*).
type Adapter interface {
	ID() string
	// Metadata descreve o adaptador sem executar nada.
	Metadata() AdapterMetadata
	// Detect verifica disponibilidade (somente leitura, com timeout).
	Detect(ctx context.Context, r *Registry) Check
}

// AdapterMetadata são metadados estáticos de um adaptador.
type AdapterMetadata struct {
	ID                 string   `json:"id"`
	Description        string   `json:"description"`
	ToolIDs            []string `json:"tool_ids"`
	SourceIDs          []string `json:"source_ids"`
	SupportedArch      []string `json:"supported_arch"`
	EquivalenceClaims  []string `json:"equivalence_claims"` // vazio por política: sem evidência, sem afirmação
	ExecutesWorkloads  bool     `json:"executes_workloads"`
	Phase0Capabilities []string `json:"phase0_capabilities"`
}

// FindDef busca uma definição por id.
func (r *Registry) FindDef(id string) (Def, bool) {
	for _, d := range r.Defs {
		if d.ID == id {
			return d, true
		}
	}
	return Def{}, false
}

// DetectByID verifica uma ferramenta do catálogo pelo id.
func (r *Registry) DetectByID(ctx context.Context, id string) Check {
	d, ok := r.FindDef(id)
	if !ok {
		return Check{Def: Def{ID: id}, Status: NaoTestado, Detail: "ferramenta não cadastrada"}
	}
	return r.CheckOne(ctx, d)
}
