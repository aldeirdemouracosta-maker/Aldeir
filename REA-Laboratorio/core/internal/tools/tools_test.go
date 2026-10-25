package tools

import (
	"context"
	"errors"
	"os"
	"os/exec"
	"strings"
	"testing"

	"rea-lab/internal/guardian"
)

func TestDetectarComLookPathSimulado(t *testing.T) {
	look := func(n string) (string, error) {
		if n == "file" {
			return "/usr/bin/file", nil
		}
		return "", errors.New("não")
	}
	var file, binwalk *Deteccao
	for _, d := range Detectar(context.Background(), look, guardian.Policy{}, false) {
		d := d
		switch d.Nome {
		case "file":
			file = &d
		case "binwalk":
			binwalk = &d
		}
	}
	if file == nil || !file.Presente || !file.Adaptador {
		t.Errorf("file: %+v", file)
	}
	if binwalk == nil || binwalk.Presente || binwalk.Adaptador {
		t.Errorf("binwalk: %+v", binwalk)
	}
}

func TestCatalogoNaoContemBinariosProibidos(t *testing.T) {
	for _, f := range Catalogo {
		if err := (guardian.Policy{}).CheckExec(f.Nome); err != nil {
			t.Errorf("catálogo contém %s, bloqueado pelo Guardian", f.Nome)
		}
	}
}

func TestExecutarFileRealELF(t *testing.T) {
	bin, err := exec.LookPath("file")
	if err != nil {
		t.Skip("file ausente")
	}
	self, _ := os.Executable() // binário de teste: ELF real
	f, _ := Procurar("file")
	_, r := Executar(context.Background(), guardian.Policy{}, f, bin, self)
	if r.Erro != "" || !strings.Contains(r.Saida, "ELF") {
		t.Fatalf("%+v", r)
	}
}

func TestExecutarRespeitaGuardian(t *testing.T) {
	f := Ferramenta{Nome: "dd", Args: func(a string) []string { return []string{a} }}
	_, r := Executar(context.Background(), guardian.Policy{}, f, "/bin/dd", "/x")
	if !strings.Contains(r.Erro, "guardian") {
		t.Fatalf("dd deveria ser bloqueado: %+v", r)
	}
}

func TestLimiteDeSaida(t *testing.T) {
	w := &limitWriter{max: 10}
	w.Write([]byte(strings.Repeat("a", 100)))
	if w.buf.Len() != 10 || !w.cut {
		t.Fatalf("%d %v", w.buf.Len(), w.cut)
	}
}
