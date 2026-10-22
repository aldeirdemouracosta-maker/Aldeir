// Package gitscan implementa o analisador de histórico Git (Fase 1): commits,
// reversões, referências a issues e palavras-chave, sempre em modo SOMENTE LEITURA.
//
// Segurança: apenas `git log` em repositórios locais; hooks, fsmonitor e transporte
// "ext" desativados; nenhum conteúdo do repositório é executado; autores NÃO são coletados.
package gitscan

import (
	"context"
	"fmt"
	"regexp"
	"sort"
	"strings"

	"hrail/internal/security"
)

// GitSafeArgs são prefixos obrigatórios em toda chamada ao git.
var GitSafeArgs = []string{
	"--no-pager",
	"-c", "core.fsmonitor=false",
	"-c", "core.hooksPath=/dev/null",
	"-c", "protocol.ext.allow=never",
}

// Commit é um commit analisado (sem nome/e-mail de autor).
type Commit struct {
	Hash         string   `json:"hash"`
	Date         string   `json:"date"`
	Subject      string   `json:"subject"`
	IsRevert     bool     `json:"is_revert"`
	RevertedHash string   `json:"reverted_hash,omitempty"`
	Keywords     []string `json:"keywords"`
	IssueRefs    []string `json:"issue_refs"`
}

// Options controla a varredura.
type Options struct {
	Since       string   // AAAA-MM-DD
	MaxCommits  int      // padrão 500, máximo 5000
	Keywords    []string // busca sem diferenciar maiúsculas em assunto+corpo
	Paths       []string // restringe a caminhos (relativos)
	OnlyMatches bool     // devolve só commits com palavra-chave ou reversão
}

// Scanner executa git via Runner (com allow-list e timeout).
type Scanner struct{ Runner *security.Runner }

var (
	reSince    = regexp.MustCompile(`^\d{4}-\d{2}-\d{2}$`)
	reRevertBy = regexp.MustCompile(`(?i)this reverts commit ([0-9a-f]{7,40})`)
	reHash     = regexp.MustCompile(`^[0-9a-f]{7,40}$`)
	reIssue    = regexp.MustCompile(`(?:^|[\s(\[])([#!][0-9]{1,7})\b`)
	reCloses   = regexp.MustCompile(`(?i)\b(?:closes|fixes|resolves)\s+(\S+)`)
)

// ValidateHash informa se s parece um hash de commit.
func ValidateHash(s string) bool { return reHash.MatchString(strings.ToLower(s)) }

func (o *Options) normalize() error {
	if o.MaxCommits <= 0 {
		o.MaxCommits = 500
	}
	if o.MaxCommits > 5000 {
		return fmt.Errorf("max de commits acima do limite (5000)")
	}
	if o.Since != "" && !reSince.MatchString(o.Since) {
		return fmt.Errorf("data %q inválida (use AAAA-MM-DD)", o.Since)
	}
	if len(o.Keywords) > 20 {
		return fmt.Errorf("no máximo 20 palavras-chave")
	}
	for i, k := range o.Keywords {
		k = strings.ToLower(strings.TrimSpace(k))
		if k == "" || len(k) > 64 {
			return fmt.Errorf("palavra-chave inválida: %q", o.Keywords[i])
		}
		o.Keywords[i] = k
	}
	for _, p := range o.Paths {
		if p == "" || strings.HasPrefix(p, "-") || strings.Contains(p, "..") {
			return fmt.Errorf("caminho inválido: %q", p)
		}
	}
	return nil
}

// Scan analisa o histórico de repoDir (HEAD).
func (s Scanner) Scan(ctx context.Context, repoDir string, o Options) ([]Commit, error) {
	if err := o.normalize(); err != nil {
		return nil, err
	}
	args := append([]string{}, GitSafeArgs...)
	args = append(args, "-C", repoDir, "log", fmt.Sprintf("--max-count=%d", o.MaxCommits),
		"--format=%x1e%H%x1f%cI%x1f%s%x1f%b")
	if o.Since != "" {
		args = append(args, "--since="+o.Since)
	}
	if len(o.Paths) > 0 {
		args = append(args, "--")
		args = append(args, o.Paths...)
	}
	res, err := s.Runner.Run(ctx, "git", args...)
	if err != nil {
		return nil, err
	}
	if res.ExitCode != 0 {
		return nil, fmt.Errorf("git log falhou (código %d): %s", res.ExitCode, firstLine(res.Stderr))
	}
	if len(res.Stdout) >= security.MaxOutputBytes {
		return nil, fmt.Errorf("saída do git truncada no limite; reduza --max ou restrinja caminhos")
	}
	return Parse(res.Stdout, o), nil
}

func firstLine(s string) string {
	s = strings.TrimSpace(s)
	if i := strings.IndexByte(s, '\n'); i >= 0 {
		return s[:i]
	}
	return s
}

// Parse interpreta a saída de `git log` no formato usado por Scan.
func Parse(out string, o Options) []Commit {
	var cs []Commit
	for _, rec := range strings.Split(out, "\x1e") {
		f := strings.SplitN(rec, "\x1f", 4)
		if len(f) < 3 || strings.TrimSpace(f[0]) == "" {
			continue
		}
		body := ""
		if len(f) == 4 {
			body = f[3]
		}
		c := Commit{Hash: strings.TrimSpace(f[0]), Date: f[1], Subject: f[2], Keywords: []string{}, IssueRefs: []string{}}
		text := strings.ToLower(c.Subject + "\n" + body)
		for _, k := range o.Keywords {
			if strings.Contains(text, k) {
				c.Keywords = append(c.Keywords, k)
			}
		}
		if m := reRevertBy.FindStringSubmatch(body); m != nil {
			c.IsRevert, c.RevertedHash = true, strings.ToLower(m[1])
		} else if strings.HasPrefix(c.Subject, "Revert \"") {
			c.IsRevert = true
		}
		seen := map[string]bool{}
		add := func(r string) {
			if !seen[r] {
				seen[r] = true
				c.IssueRefs = append(c.IssueRefs, r)
			}
		}
		for _, m := range reIssue.FindAllStringSubmatch(c.Subject+"\n"+body, -1) {
			add(m[1])
		}
		for _, m := range reCloses.FindAllStringSubmatch(body, -1) {
			add(strings.TrimRight(m[1], ".,;"))
		}
		sort.Strings(c.IssueRefs)
		if o.OnlyMatches && !c.IsRevert && len(c.Keywords) == 0 {
			continue
		}
		cs = append(cs, c)
	}
	return cs
}
