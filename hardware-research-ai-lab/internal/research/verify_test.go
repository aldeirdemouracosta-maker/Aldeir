package research

import (
	"context"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"hrail/internal/security"
	"hrail/internal/storage"
)

const mitText = `MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND`

func gitIn(t *testing.T, dir string, args ...string) {
	t.Helper()
	c := exec.Command("git", append([]string{"-C", dir}, args...)...)
	c.Env = append(os.Environ(), "GIT_AUTHOR_NAME=T", "GIT_AUTHOR_EMAIL=t@example.invalid", "GIT_COMMITTER_NAME=T", "GIT_COMMITTER_EMAIL=t@example.invalid",
		"GIT_COMMITTER_DATE=2026-02-01T12:00:00Z", "GIT_AUTHOR_DATE=2026-02-01T12:00:00Z")
	if out, err := c.CombinedOutput(); err != nil {
		t.Fatalf("git %v: %v\n%s", args, err, out)
	}
}

func remoto(t *testing.T, license string) (dir, head string) {
	t.Helper()
	dir = t.TempDir()
	gitIn(t, dir, "init", "-q", "-b", "main")
	if license != "" {
		os.WriteFile(filepath.Join(dir, "LICENSE"), []byte(license), 0o644)
	}
	os.WriteFile(filepath.Join(dir, "a.txt"), []byte("x"), 0o644)
	gitIn(t, dir, "add", ".")
	gitIn(t, dir, "commit", "-q", "-m", "um")
	out, _ := exec.Command("git", "-C", dir, "rev-parse", "HEAD").Output()
	return dir, strings.TrimSpace(string(out))
}

func verifier(t *testing.T, remote string) Verifier {
	return Verifier{
		Runner: security.NewRunner(20*time.Second, "git"), CloneDir: filepath.Join(t.TempDir(), "clones"), Depth: 10,
		RemoteURL: func(Source) string { return remote },
	}
}

func src(license string) Source {
	s := valid()
	s.ID, s.License = "fonte", license
	return s
}

func TestVerificarRepositorioComClone(t *testing.T) {
	dir, head := remoto(t, mitText)
	v := verifier(t, "file://"+dir)
	r := v.Verify(context.Background(), src("MIT"), true)
	if r.Status != Verificado || r.HeadCommit != head || !strings.HasPrefix(r.HeadDate, "2026-02-01") {
		t.Fatalf("%+v", r)
	}
	if r.LicenseDetected != "MIT" || r.LicenseMatches == nil || !*r.LicenseMatches {
		t.Errorf("licença: %+v", r)
	}
	if !strings.Contains(r.Note, "NÃO é confirmado automaticamente") {
		t.Error("deve avisar que o dono oficial não é confirmado")
	}
	// segunda execução reaproveita o clone (fetch)
	if r2 := v.Verify(context.Background(), src("MIT"), true); r2.Status != Verificado {
		t.Errorf("fetch: %+v", r2)
	}
	if _, err := os.Stat(filepath.Join(v.CloneDir, "fonte", "a.txt")); err == nil {
		t.Error("clone não pode fazer checkout (nada do repositório vai para o disco como arquivo)")
	}
}

func TestLicencaDivergenteEhSinalizada(t *testing.T) {
	dir, _ := remoto(t, mitText)
	r := verifier(t, "file://"+dir).Verify(context.Background(), src("Apache-2.0"), true)
	if r.LicenseMatches == nil || *r.LicenseMatches || !strings.Contains(r.Note, "ATENÇÃO") {
		t.Fatalf("%+v", r)
	}
	r = verifier(t, "file://"+dir).Verify(context.Background(), src("desconhecida"), true)
	if r.LicenseMatches != nil || r.LicenseDetected != "MIT" {
		t.Errorf("licença declarada desconhecida não é comparável: %+v", r)
	}
}

func TestSemCloneEhParcialEInacessivel(t *testing.T) {
	dir, head := remoto(t, "")
	r := verifier(t, "file://"+dir).Verify(context.Background(), src("MIT"), false)
	if r.Status != Parcial || r.HeadCommit != head || r.HeadDate != "" {
		t.Fatalf("%+v", r)
	}
	r = verifier(t, "file://"+dir).Verify(context.Background(), src("MIT"), true)
	if r.Status != Verificado || !strings.Contains(r.Note, "licença não encontrado") {
		t.Errorf("sem LICENSE: %+v", r)
	}
	r = verifier(t, "file:///nao/existe/xyz").Verify(context.Background(), src("MIT"), true)
	if r.Status != "inacessivel" || r.HeadCommit != "" || r.Note == "" {
		t.Errorf("inexistente: %+v", r)
	}
}

func TestVerificarWeb(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/ok" {
			return
		}
		http.NotFound(w, r)
	}))
	defer srv.Close()
	s := src("não aplicável")
	s.HostKind = "web"
	v := Verifier{RemoteURL: func(Source) string { return srv.URL + "/ok" }}
	if r := v.Verify(context.Background(), s, false); r.Status != Verificado || r.HTTPStatus != 200 {
		t.Errorf("%+v", r)
	}
	v.RemoteURL = func(Source) string { return srv.URL + "/falta" }
	if r := v.Verify(context.Background(), s, false); r.Status != "inacessivel" || r.HTTPStatus != 404 {
		t.Errorf("%+v", r)
	}
	v.RemoteURL = func(Source) string { return "http://127.0.0.1:1/x" }
	if r := v.Verify(context.Background(), s, false); r.Status != "inacessivel" {
		t.Errorf("%+v", r)
	}
}

func TestDetectLicense(t *testing.T) {
	cases := map[string]string{
		mitText: "MIT", "Apache License\nVersion 2.0, January 2004": "Apache-2.0",
		"GNU GENERAL PUBLIC LICENSE Version 3": "GPL-3.0", "GNU GENERAL PUBLIC LICENSE Version 2": "GPL-2.0",
		"Redistribution and use in source and binary forms ... Neither the name of": "BSD-3-Clause",
		"Redistribution and use in source and binary forms ...":                     "BSD-2-Clause",
		"texto proprietário qualquer":                                               "",
	}
	for in, want := range cases {
		if got := DetectLicense(in); got != want {
			t.Errorf("%q → %q (esperado %q)", in[:20], got, want)
		}
	}
	if m := LicenseMatches("BSD-3-Clause (e outras)", "BSD-3-Clause"); m == nil || !*m {
		t.Error("match")
	}
	if LicenseMatches("MIT", "") != nil {
		t.Error("sem detecção não é comparável")
	}
}

func TestPersistenciaESobreposicao(t *testing.T) {
	db, _ := storage.Open(filepath.Join(t.TempDir(), "v.db"))
	defer db.Close()
	yes := true
	ok := Result{SourceID: "a", Status: Verificado, CheckedAt: "2026-10-22T00:00:00Z", HeadCommit: "abc1234", HeadDate: "2026-01-01T00:00:00Z", LicenseMatches: &yes, LicenseDetected: "MIT", Note: "n"}
	bad := Result{SourceID: "b", Status: "inacessivel", CheckedAt: "2026-10-22T00:00:00Z", Note: "403"}
	for _, r := range []Result{ok, bad, ok} {
		if err := SaveVerification(db, r); err != nil {
			t.Fatal(err)
		}
	}
	vs, err := LoadVerifications(db)
	if err != nil || len(vs) != 2 || vs["a"].LicenseMatches == nil || !*vs["a"].LicenseMatches {
		t.Fatalf("%+v %v", vs, err)
	}
	a, b := valid(), valid()
	a.ID, b.ID, b.URL = "a", "b", "https://github.com/c/d"
	got := Overlay([]Source{a, b}, vs)
	if got[0].Verification.Status != Verificado || got[0].LastCommitConsulted == nil || !got[0].LicenseVerified {
		t.Errorf("a: %+v", got[0])
	}
	if got[1].Verification.Status != NaoVerificado || got[1].LastCommitConsulted != nil || !strings.Contains(got[1].Verification.Note, "403") {
		t.Errorf("inacessível deve continuar não verificada: %+v", got[1])
	}
	if !strings.Contains(got[0].MaintenanceState, "possivelmente inativo") {
		t.Errorf("commit de jan/2026 vs verificação em out/2026 deve ser 'possivelmente inativo': %q", got[0].MaintenanceState)
	}
	if p := ValidateAll(got); len(p) != 0 {
		t.Errorf("sobreposição deve resultar em catálogo válido: %v", p)
	}
	if a.Verification.Status != NaoVerificado {
		t.Error("Overlay não pode alterar o original")
	}
}
