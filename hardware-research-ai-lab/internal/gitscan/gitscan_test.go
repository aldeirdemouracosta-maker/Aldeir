package gitscan

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"hrail/internal/security"
	"hrail/internal/storage"
)

func git(t *testing.T, dir string, args ...string) string {
	t.Helper()
	c := exec.Command("git", append([]string{"-C", dir}, args...)...)
	c.Env = append(os.Environ(), "GIT_AUTHOR_NAME=T", "GIT_AUTHOR_EMAIL=t@example.invalid", "GIT_COMMITTER_NAME=T", "GIT_COMMITTER_EMAIL=t@example.invalid",
		"GIT_AUTHOR_DATE=2026-03-02T10:00:00Z", "GIT_COMMITTER_DATE=2026-03-02T10:00:00Z")
	out, err := c.CombinedOutput()
	if err != nil {
		t.Fatalf("git %v: %v\n%s", args, err, out)
	}
	return strings.TrimSpace(string(out))
}

// repo fictício com 4 commits: base, polaris+issue, aco, e uma reversão.
func repoFicticio(t *testing.T) (dir, revertedHash string) {
	t.Helper()
	dir = t.TempDir()
	git(t, dir, "init", "-q", "-b", "main")
	w := func(name, body, msg string) string {
		os.MkdirAll(filepath.Dir(filepath.Join(dir, name)), 0o755)
		os.WriteFile(filepath.Join(dir, name), []byte(body), 0o644)
		git(t, dir, "add", ".")
		git(t, dir, "commit", "-q", "-m", msg)
		return git(t, dir, "rev-parse", "HEAD")
	}
	w("README", "x", "commit inicial")
	w("src/gfx8.c", "a", "radv: corrige Polaris gfx803 (#123)\n\nCloses https://example.invalid/issues/9.")
	bad := w("src/aco.c", "b", "aco: nova otimização de spill\n\nPode afetar GFX8.")
	git(t, dir, "revert", "--no-edit", bad)
	return dir, bad
}

func scanner() Scanner { return Scanner{Runner: security.NewRunner(10*time.Second, "git")} }

func TestScanDetectaReversaoPalavrasEIssues(t *testing.T) {
	dir, bad := repoFicticio(t)
	cs, err := scanner().Scan(context.Background(), dir, Options{Keywords: []string{"polaris", "GFX8", "vega"}})
	if err != nil {
		t.Fatal(err)
	}
	if len(cs) != 4 {
		t.Fatalf("commits=%d", len(cs))
	}
	by := map[string]Commit{}
	for _, c := range cs {
		by[c.Subject] = c
	}
	pol := by["radv: corrige Polaris gfx803 (#123)"]
	// busca por substring: "gfx8" também casa com "gfx803"
	if strings.Join(pol.Keywords, ",") != "polaris,gfx8" {
		t.Errorf("polaris: %+v", pol)
	}
	if strings.Join(pol.IssueRefs, ",") != "#123,https://example.invalid/issues/9" {
		t.Errorf("issues: %v", pol.IssueRefs)
	}
	aco := by["aco: nova otimização de spill"]
	if len(aco.Keywords) != 1 || aco.Keywords[0] != "gfx8" {
		t.Errorf("gfx8 no corpo: %+v", aco)
	}
	var rev Commit
	for _, c := range cs {
		if c.IsRevert {
			rev = c
		}
	}
	if rev.RevertedHash != bad {
		t.Errorf("reversão deve apontar %s, obteve %s", bad, rev.RevertedHash)
	}
	for _, c := range cs {
		if strings.Contains(c.Subject+c.Hash+c.Date, "t@example") {
			t.Error("não deve coletar autores")
		}
	}
}

func TestOnlyMatchesMaxEPaths(t *testing.T) {
	dir, _ := repoFicticio(t)
	cs, _ := scanner().Scan(context.Background(), dir, Options{Keywords: []string{"polaris"}, OnlyMatches: true})
	if len(cs) != 2 { // polaris + reversão
		t.Fatalf("esperava polaris + reversão, obteve %d", len(cs))
	}
	cs, _ = scanner().Scan(context.Background(), dir, Options{MaxCommits: 1})
	if len(cs) != 1 {
		t.Fatalf("max=1 → %d", len(cs))
	}
	cs, _ = scanner().Scan(context.Background(), dir, Options{Paths: []string{"src/gfx8.c"}})
	if len(cs) != 1 {
		t.Fatalf("path → %d", len(cs))
	}
	cs, _ = scanner().Scan(context.Background(), dir, Options{Since: "2030-01-01"})
	if len(cs) != 0 {
		t.Fatalf("since futuro → %d", len(cs))
	}
}

func TestEntradasInvalidasERepoInexistente(t *testing.T) {
	dir, _ := repoFicticio(t)
	for _, o := range []Options{{Since: "ontem"}, {Paths: []string{"--output=x"}}, {Paths: []string{"../x"}}, {Keywords: []string{""}}, {MaxCommits: 99999}} {
		if _, err := scanner().Scan(context.Background(), dir, o); err == nil {
			t.Errorf("deveria recusar %+v", o)
		}
	}
	if _, err := scanner().Scan(context.Background(), t.TempDir(), Options{}); err == nil {
		t.Error("diretório que não é repositório deve falhar")
	}
	if _, err := (Scanner{Runner: security.NewRunner(time.Second, "echo")}).Scan(context.Background(), dir, Options{}); err == nil {
		t.Error("git fora da allow-list deve falhar")
	}
}

func TestHooksNaoExecutam(t *testing.T) {
	dir, _ := repoFicticio(t)
	marker := filepath.Join(t.TempDir(), "executou")
	hook := "#!/bin/sh\ntouch " + marker + "\n"
	os.WriteFile(filepath.Join(dir, ".git", "hooks", "post-checkout"), []byte(hook), 0o755)
	git(t, dir, "config", "core.fsmonitor", "touch "+marker)
	if _, err := scanner().Scan(context.Background(), dir, Options{}); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(marker); err == nil {
		t.Fatal("nada do repositório analisado pode ser executado")
	}
}

func TestPersistencia(t *testing.T) {
	dir, bad := repoFicticio(t)
	cs, _ := scanner().Scan(context.Background(), dir, Options{Keywords: []string{"polaris"}})
	db, _ := storage.Open(filepath.Join(t.TempDir(), "g.db"))
	defer db.Close()
	for i := 0; i < 2; i++ { // upsert idempotente
		if err := Save(db, "mesa", cs); err != nil {
			t.Fatal(err)
		}
	}
	all, srcs, err := List(db, Query{})
	if err != nil || len(all) != 4 || srcs[0] != "mesa" {
		t.Fatalf("%d %v", len(all), err)
	}
	if r, _, _ := List(db, Query{OnlyReverts: true}); len(r) != 1 {
		t.Errorf("reverts=%d", len(r))
	}
	if k, _, _ := List(db, Query{Keyword: "polaris"}); len(k) != 1 {
		t.Errorf("keyword=%d", len(k))
	}
	if h, ok, _ := Exists(db, "mesa", bad[:10]); !ok || h != bad {
		t.Errorf("exists prefixo: %s %v", h, ok)
	}
	if _, ok, _ := Exists(db, "mesa", "deadbeef"); ok {
		t.Error("hash desconhecido")
	}
}
