package evidence

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestHashConhecido(t *testing.T) {
	p := filepath.Join(t.TempDir(), "a")
	os.WriteFile(p, []byte("abc"), 0o644)
	h, n, err := HashFile(p)
	if err != nil || n != 3 || h != "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad" {
		t.Fatalf("%s %d %v", h, n, err)
	}
}

func TestRelatorioJSONeMarkdown(t *testing.T) {
	r := Novo(Entrada{Caminho: "/x/a", SHA256: strings.Repeat("a", 64), Tamanho: 3, Formato: "ELF"}, "Fulano", "pendrive")
	r.AddPasso(Passo{Ferramenta: "file", Comando: "file /x/a", Quando: time.Now(), Saida: "ELF 64-bit"})
	if r.Passos[0].SaidaSHA256 != HashBytes([]byte("ELF 64-bit")) {
		t.Fatal("hash da saída incorreto")
	}
	jp, mp, err := r.Salvar(filepath.Join(t.TempDir(), "o"))
	if err != nil {
		t.Fatal(err)
	}
	md, _ := os.ReadFile(mp)
	for _, s := range []string{strings.Repeat("a", 64), "Fulano", "pendrive", "file /x/a"} {
		if !strings.Contains(string(md), s) {
			t.Errorf("markdown sem %q", s)
		}
	}
	if _, err := os.Stat(jp); err != nil {
		t.Fatal(err)
	}
}

func TestSaidaHostilNaoQuebraBlocoMarkdown(t *testing.T) {
	r := Novo(Entrada{Caminho: "/x", SHA256: strings.Repeat("b", 64)}, "", "")
	r.AddPasso(Passo{Ferramenta: "strings", Comando: "strings /x", Quando: time.Now(), Saida: "a\n```\n## INJETADO\n````\nb"})
	md := r.Markdown()
	i := strings.Index(md, "## INJETADO")
	antes, depois := md[:i], md[i:]
	if !strings.Contains(antes, "`````") || !strings.Contains(depois, "`````") {
		t.Fatalf("cerca deveria ter 5 crases e envolver o conteúdo:\n%s", md)
	}
}
