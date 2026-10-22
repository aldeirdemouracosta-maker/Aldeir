package research

import (
	"path/filepath"
	"strings"
	"testing"

	"hrail/catalog"
	"hrail/internal/storage"
)

func valid() Source {
	return Source{ID: "x", Name: "X", URL: "https://github.com/a/b", HostKind: "github", Kind: "simulacao", License: "MIT",
		Purpose: "p", MaintenanceState: "desconhecido", Trust: "referencia_publica",
		Verification: Verification{Status: NaoVerificado}}
}

func TestCatalogoEmbutido(t *testing.T) {
	ss, err := ParseCatalog(catalog.SourcesJSON)
	if err != nil {
		t.Fatal(err)
	}
	want := map[string]bool{
		"https://github.com/sarchlab/mgpusim": false, "https://github.com/gem5/gem5": false, "https://www.gem5.org/": false,
		"https://gitlab.freedesktop.org/mesa/mesa": false, "https://docs.mesa3d.org/drivers/radv.html": false,
		"https://github.com/KhronosGroup/Vulkan-Samples": false, "https://github.com/mihawk-99/PS5_Vulkan": false,
		"https://github.com/ggml-org/llama.cpp": false,
	}
	for _, s := range ss {
		if _, ok := want[s.URL]; ok {
			want[s.URL] = true
		}
		if s.LastCommitConsulted != nil || s.Verification.Status != NaoVerificado {
			t.Errorf("%s: não pode alegar verificação sem rede", s.ID)
		}
	}
	for u, ok := range want {
		if !ok {
			t.Errorf("fonte obrigatória ausente: %s", u)
		}
	}
}

func TestValidacao(t *testing.T) {
	if p := Validate(valid()); len(p) != 0 {
		t.Fatalf("válida rejeitada: %v", p)
	}
	mut := map[string]func(*Source){
		"http":             func(s *Source) { s.URL = "http://github.com/a/b" },
		"host errado":      func(s *Source) { s.URL = "https://evil.example/a/b" },
		"sem licença":      func(s *Source) { s.License = "" },
		"exec":             func(s *Source) { s.AllowExecution = true },
		"kind desconh.":    func(s *Source) { s.HostKind = "ftp" },
		"commit sem verif": func(s *Source) { c := "abc"; s.LastCommitConsulted = &c },
		"status inválido":  func(s *Source) { s.Verification.Status = "talvez" },
		"verificado vazio": func(s *Source) { s.Verification.Status = Verificado },
	}
	for name, f := range mut {
		s := valid()
		f(&s)
		if len(Validate(s)) == 0 {
			t.Errorf("%s: deveria ser inválida", name)
		}
	}
}

func TestDuplicatas(t *testing.T) {
	a, b := valid(), valid()
	p := ValidateAll([]Source{a, b})
	if len(p) < 2 || !strings.Contains(strings.Join(p, "|"), "duplicad") {
		t.Fatalf("%v", p)
	}
}

func TestPersistenciaEFiltro(t *testing.T) {
	db, err := storage.Open(filepath.Join(t.TempDir(), "r.db"))
	if err != nil {
		t.Fatal(err)
	}
	defer db.Close()
	ss, _ := ParseCatalog(catalog.SourcesJSON)
	if err := Save(db, ss); err != nil {
		t.Fatal(err)
	}
	if err := Save(db, ss); err != nil { // upsert idempotente
		t.Fatal(err)
	}
	got, err := Load(db)
	if err != nil || len(got) != len(ss) {
		t.Fatalf("n=%d err=%v", len(got), err)
	}
	if len(Filter(ss, "simulacao")) != 2 {
		t.Errorf("filtro simulacao")
	}
	if _, ok := Find(ss, "mesa"); !ok {
		t.Error("find mesa")
	}
}
