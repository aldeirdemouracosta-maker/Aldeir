package archive

import (
	"archive/zip"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func mkzip(t *testing.T, files map[string]string) string {
	p := filepath.Join(t.TempDir(), "t.zip")
	f, _ := os.Create(p)
	zw := zip.NewWriter(f)
	for n, c := range files {
		w, _ := zw.Create(n)
		w.Write([]byte(c))
	}
	zw.Close()
	f.Close()
	return p
}

func TestTraversalESuspeitos(t *testing.T) {
	r, err := ListZip(mkzip(t, map[string]string{"ok.txt": "a", "../x": "b", "/abs": "c", `C:\w`: "d"}), DefaultLimits)
	if err != nil {
		t.Fatal(err)
	}
	n := 0
	for _, e := range r.Entradas {
		if len(e.Alertas) > 0 {
			n++
		}
	}
	if n != 3 {
		t.Fatalf("esperava 3 entradas suspeitas, obtive %d", n)
	}
}

func TestBombaPorRazaoETotal(t *testing.T) {
	p := mkzip(t, map[string]string{"zeros": strings.Repeat("\x00", 5<<20)})
	r, _ := ListZip(p, Limits{MaxEntries: 10, MaxUncompressed: 1 << 20, MaxRatio: 50})
	if len(r.Alertas) < 2 {
		t.Fatalf("esperava alerta de razão e de total: %v", r.Alertas)
	}
}

func TestTruncaPorEntradas(t *testing.T) {
	r, _ := ListZip(mkzip(t, map[string]string{"a": "1", "b": "2", "c": "3"}), Limits{MaxEntries: 2, MaxUncompressed: 1 << 30, MaxRatio: 200})
	if !r.Truncado || len(r.Entradas) != 2 {
		t.Fatalf("%+v", r)
	}
}

func TestNaoZip(t *testing.T) {
	p := filepath.Join(t.TempDir(), "n")
	os.WriteFile(p, []byte("nada"), 0o644)
	if _, err := ListZip(p, DefaultLimits); err == nil {
		t.Fatal("deveria falhar")
	}
}
