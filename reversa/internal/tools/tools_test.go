package tools

import (
	"context"
	"encoding/binary"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"reversa/internal/evidence"
)

func sampleExe() []byte {
	b := make([]byte, 0x800)
	copy(b, "PS-X EXE")
	put := func(off int, v uint32) { binary.LittleEndian.PutUint32(b[off:], v) }
	code := []uint32{0x0C004004, 0, 0x0C004004, 0, 0x3C081F80, 0xAD021810, 0x03E00008, 0}
	put(0x10, 0x80010000)
	put(0x18, 0x80010000)
	put(0x1C, uint32(len(code)*4))
	for _, w := range code {
		b = binary.LittleEndian.AppendUint32(b, w)
	}
	return b
}

func newSet(t *testing.T) (*Set, string) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "a.exe"), sampleExe(), 0o644); err != nil {
		t.Fatal(err)
	}
	return &Set{Root: dir, Log: &evidence.Log{}}, dir
}

func call(t *testing.T, s *Set, name string, args map[string]any) (string, error) {
	for _, tl := range s.MCP() {
		if tl.Name == name {
			return tl.Handler(context.Background(), args)
		}
	}
	t.Fatalf("ferramenta %s não existe", name)
	return "", nil
}

func TestFerramentas(t *testing.T) {
	s, _ := newSet(t)
	out, err := call(t, s, "ps1_functions", map[string]any{"path": "a.exe"})
	if err != nil || !strings.Contains(out, "0x80010010 chamadas=2") {
		t.Fatalf("functions: %v\n%s", err, out)
	}
	out, err = call(t, s, "ps1_disasm", map[string]any{"path": "a.exe", "address": "0x80010010", "count": float64(8)})
	if err != nil || !strings.Contains(out, "GPU_GP0") || !strings.Contains(out, "[E2]") {
		t.Fatalf("disasm: %v\n%s", err, out)
	}
	if s.Log.Subject == "" || len(s.Log.All()) != 2 {
		t.Fatalf("evidências: %d subject=%q", len(s.Log.All()), s.Log.Subject)
	}
	if _, err := call(t, s, "ps1_disasm", map[string]any{"path": "a.exe", "address": "xyz"}); err == nil {
		t.Fatal("endereço inválido deveria falhar")
	}
}

func TestRaizPermitida(t *testing.T) {
	s, dir := newSet(t)
	outside := t.TempDir()
	_ = os.WriteFile(filepath.Join(outside, "b.exe"), sampleExe(), 0o644)
	_ = os.Symlink(outside, filepath.Join(dir, "link"))
	for _, p := range []string{"../" + filepath.Base(outside) + "/b.exe", filepath.Join(outside, "b.exe"), "link/b.exe"} {
		if _, err := call(t, s, "ps1_header", map[string]any{"path": p}); err == nil || !strings.Contains(err.Error(), "fora da raiz") {
			t.Errorf("%q deveria ser recusado, veio %v", p, err)
		}
	}
	if _, err := call(t, s, "ps1_header", map[string]any{"path": filepath.Join(dir, "a.exe")}); err != nil {
		t.Errorf("caminho absoluto dentro da raiz deveria funcionar: %v", err)
	}
}

func TestFerramentaPS1Function(t *testing.T) {
	s, dir := newSet(t)
	if err := os.WriteFile(filepath.Join(dir, "e2.exe"), mustRead(t, "../../testdata/exemplo2.exe"), 0o644); err != nil {
		t.Fatal(err)
	}
	out, err := call(t, s, "ps1_function", map[string]any{"path": "e2.exe", "address": "0x80010074"})
	if err != nil || !strings.Contains(out, "# Função 0x80010074") || !strings.Contains(out, "repete enquanto (I_STAT & 0x1) == 0") || !strings.Contains(out, "(derived)") {
		t.Fatalf("ps1_function: %v\n%s", err, out)
	}
	if _, err := call(t, s, "ps1_function", map[string]any{"path": "e2.exe", "address": "0x70000000"}); err == nil {
		t.Error("endereço fora do código deveria falhar")
	}
	if _, err := call(t, s, "ps1_function", map[string]any{"path": "e2.exe", "address": "lixo"}); err == nil {
		t.Error("endereço inválido deveria falhar")
	}
}

func mustRead(t *testing.T, p string) []byte {
	b, err := os.ReadFile(p)
	if err != nil {
		t.Fatal(err)
	}
	return b
}

func TestFerramentasXrefEMem(t *testing.T) {
	s, dir := newSet(t)
	if err := os.WriteFile(filepath.Join(dir, "e7.exe"), mustRead(t, "../../testdata/exemplo7.exe"), 0o644); err != nil {
		t.Fatal(err)
	}
	out, err := call(t, s, "ps1_xref", map[string]any{"path": "e7.exe", "address": "0x800100a0"})
	if err != nil || !strings.Contains(out, "sb escreve 0x05") || !strings.Contains(out, "(derived)") {
		t.Fatalf("ps1_xref: %v\n%s", err, out)
	}
	out, err = call(t, s, "ps1_mem", map[string]any{"path": "e7.exe", "address": "0x800100a4", "bytes": float64(12)})
	if err != nil || !strings.Contains(out, "10 00 00 00") || !strings.Contains(out, "(observed)") {
		t.Fatalf("ps1_mem: %v\n%s", err, out)
	}
	if _, err := call(t, s, "ps1_mem", map[string]any{"path": "e7.exe", "address": "0x70000000"}); err == nil {
		t.Error("endereço fora da imagem deveria falhar")
	}
	if _, err := call(t, s, "ps1_xref", map[string]any{"path": "e7.exe", "address": "zzz"}); err == nil {
		t.Error("endereço inválido deveria falhar")
	}
}
