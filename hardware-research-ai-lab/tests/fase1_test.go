package tests

import (
	"bytes"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

// hrailGit é como hrail(), mas com git no PATH (a Fase 1 depende dele).
func hrailGit(t *testing.T, root, sys string, args ...string) (string, string, int) {
	t.Helper()
	cmd := exec.Command(bin, append([]string{"--raiz", root}, args...)...)
	cmd.Env = []string{"PATH=/usr/bin:/bin", "HOME=" + t.TempDir(), "HRAIL_SYSROOT=" + sys}
	var so, se bytes.Buffer
	cmd.Stdout, cmd.Stderr = &so, &se
	code := 0
	if err := cmd.Run(); err != nil {
		ee, ok := err.(*exec.ExitError)
		if !ok {
			t.Fatal(err)
		}
		code = ee.ExitCode()
	}
	return so.String(), se.String(), code
}

func gitT(t *testing.T, dir string, args ...string) string {
	t.Helper()
	c := exec.Command("git", append([]string{"-C", dir}, args...)...)
	c.Env = append(os.Environ(), "GIT_AUTHOR_NAME=T", "GIT_AUTHOR_EMAIL=t@example.invalid", "GIT_COMMITTER_NAME=T", "GIT_COMMITTER_EMAIL=t@example.invalid")
	out, err := c.CombinedOutput()
	if err != nil {
		t.Fatalf("git %v: %v %s", args, err, out)
	}
	return strings.TrimSpace(string(out))
}

func TestFase1HistoricoEEvidencia(t *testing.T) {
	root, sys := projeto(t)
	repo := t.TempDir()
	gitT(t, repo, "init", "-q", "-b", "main")
	os.WriteFile(filepath.Join(repo, "a.c"), []byte("1"), 0o644)
	gitT(t, repo, "add", ".")
	gitT(t, repo, "commit", "-q", "-m", "radv: suporte a Polaris gfx803 (#77)")
	hash := gitT(t, repo, "rev-parse", "HEAD")
	os.WriteFile(filepath.Join(repo, "a.c"), []byte("2"), 0o644)
	gitT(t, repo, "commit", "-aq", "-m", "aco: otimização")
	gitT(t, repo, "revert", "--no-edit", "HEAD")

	if out, errs, code := hrailGit(t, root, sys, "init"); code != 0 {
		t.Fatalf("init: %s %s", out, errs)
	}
	// offline: nada é consultado
	out, _, code := hrailGit(t, root, sys, "research", "verificar")
	if code != 0 || !strings.Contains(out, "Modo offline") || !strings.Contains(out, "nao_verificado") {
		t.Fatalf("verificar offline:\n%s", out)
	}
	// histórico sem clone → erro claro
	if _, errs, code := hrailGit(t, root, sys, "research", "historico", "--fonte", "mesa"); code == 0 || !strings.Contains(errs, "não existe") {
		t.Fatalf("esperava erro orientando a clonar: %s", errs)
	}
	out, errs, code := hrailGit(t, root, sys, "research", "historico", "--fonte", "mesa", "--repo", repo, "--palavras", "polaris,gfx803")
	if code != 0 || !strings.Contains(out, "2 achado(s)") || !strings.Contains(out, "1 reversão") {
		t.Fatalf("historico:\n%s\n%s", out, errs)
	}
	out, _, _ = hrailGit(t, root, sys, "research", "commits", "--palavra", "polaris")
	if !strings.Contains(out, hash[:10]) || !strings.Contains(out, "#77") {
		t.Fatalf("commits:\n%s", out)
	}

	exp := `{"id":"EXP-P1","description":"Polaris no RADV","hypothesis_source":"manual","applicable_hardware":["rx580"],
	"operational_risk":"baixo","reversibility":"total","confidence":"baixa","level":"A","kind":"analise","origin":"estimated"}`
	os.WriteFile(filepath.Join(root, "e.json"), []byte(exp), 0o644)
	if _, errs, code := hrailGit(t, root, sys, "experiment", "registrar", "--arquivo", "e.json"); code != 0 {
		t.Fatal(errs)
	}
	// commit não analisado é recusado
	if _, errs, code := hrailGit(t, root, sys, "research", "evidencia", "--experimento", "EXP-P1", "--fonte", "mesa", "--commit", "deadbeef", "--postura", "favoravel", "--resumo", "x"); code == 0 || !strings.Contains(errs, "não consta") {
		t.Fatalf("deveria recusar commit não analisado: %s", errs)
	}
	out, errs, code = hrailGit(t, root, sys, "research", "evidencia", "--experimento", "EXP-P1", "--fonte", "mesa", "--commit", hash[:10], "--postura", "favoravel", "--resumo", "suporte declarado")
	if code != 0 || !strings.Contains(out, "https://gitlab.freedesktop.org/mesa/mesa/-/commit/"+hash) || !strings.Contains(out, "evidencia_favoravel") {
		t.Fatalf("evidencia:\n%s\n%s", out, errs)
	}
	out, _, _ = hrailGit(t, root, sys, "experiment", "list")
	if !strings.Contains(out, "evidencia_favoravel") {
		t.Fatalf("estado não refletido:\n%s", out)
	}
}
