package disc

import (
	"bytes"
	"encoding/binary"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// builder monta uma imagem ISO 9660 mínima com setores de 2048 bytes.
type builder struct{ sectors map[uint32][]byte }

func newBuilder() *builder { return &builder{sectors: map[uint32][]byte{}} }

func (b *builder) put(lba uint32, data []byte) {
	for i := 0; i*userSize < len(data); i++ {
		sec := make([]byte, userSize)
		copy(sec, data[i*userSize:min(len(data), (i+1)*userSize)])
		b.sectors[lba+uint32(i)] = sec
	}
}

func record(name string, lba, size uint32, dir bool) []byte {
	n := 33 + len(name)
	if n%2 == 1 {
		n++
	}
	r := make([]byte, n)
	r[0], r[32] = byte(n), byte(len(name))
	binary.LittleEndian.PutUint32(r[2:], lba)
	binary.LittleEndian.PutUint32(r[10:], size)
	if dir {
		r[25] = 2
	}
	copy(r[33:], name)
	return r
}

func (b *builder) iso(files map[string][]byte) []byte {
	pvd := make([]byte, userSize)
	pvd[0] = 1
	copy(pvd[1:], "CD001")
	copy(pvd[40:72], "TESTE_PS1                       ")
	var dir []byte
	next := uint32(20)
	for name, data := range files {
		dir = append(dir, record(name+";1", next, uint32(len(data)), false)...)
		b.put(next, data)
		next += uint32(len(data)+userSize-1) / userSize
	}
	b.put(18, dir)
	copy(pvd[156:], record("\x00", 18, uint32(len(dir)), true))
	b.put(16, pvd)
	var out bytes.Buffer
	for lba := uint32(0); lba < next; lba++ {
		if s, ok := b.sectors[lba]; ok {
			out.Write(s)
		} else {
			out.Write(make([]byte, userSize))
		}
	}
	return out.Bytes()
}

// raw converte setores de 2048 em setores brutos de 2352 (Mode 2 Form 1).
func raw(iso []byte) []byte {
	var out bytes.Buffer
	for off := 0; off < len(iso); off += userSize {
		sec := make([]byte, rawSize)
		copy(sec, sync)
		sec[15] = 2
		copy(sec[rawOffset:], iso[off:off+userSize])
		out.Write(sec)
	}
	return out.Bytes()
}

func sampleFiles() map[string][]byte {
	exe := bytes.Repeat([]byte{0xAB}, 3000) // atravessa 2 setores
	return map[string][]byte{
		"SYSTEM.CNF":  []byte("BOOT = cdrom:\\SLUS_006.64;1\r\nTCB = 4\r\nEVENT = 10\r\nSTACK = 801FFFF0\r\n"),
		"SLUS_006.64": exe,
	}
}

func TestISO2048(t *testing.T) {
	iso := newBuilder().iso(sampleFiles())
	img, err := New(bytes.NewReader(iso), int64(len(iso)))
	if err != nil {
		t.Fatal(err)
	}
	if img.VolumeID != "TESTE_PS1" {
		t.Errorf("volume %q", img.VolumeID)
	}
	name, exe, err := img.BootExe()
	if err != nil || name != "SLUS_006.64" || len(exe) != 3000 || exe[2999] != 0xAB {
		t.Fatalf("boot: %q len=%d err=%v", name, len(exe), err)
	}
}

func TestBinCueBruto(t *testing.T) {
	dir := t.TempDir()
	img := raw(newBuilder().iso(sampleFiles()))
	if err := os.WriteFile(filepath.Join(dir, "jogo.bin"), img, 0o644); err != nil {
		t.Fatal(err)
	}
	cue := `FILE "jogo.bin" BINARY` + "\r\n  TRACK 01 MODE2/2352\r\n    INDEX 01 00:00:00\r\n"
	if err := os.WriteFile(filepath.Join(dir, "jogo.cue"), []byte(cue), 0o644); err != nil {
		t.Fatal(err)
	}
	d, err := Open(filepath.Join(dir, "jogo.cue"))
	if err != nil {
		t.Fatal(err)
	}
	defer d.Close()
	if d.sectorSize != rawSize {
		t.Fatalf("setor %d, esperava bruto", d.sectorSize)
	}
	files, err := d.List("/")
	if err != nil || len(files) != 2 {
		t.Fatalf("lista: %v %v", files, err)
	}
	if _, exe, err := d.BootExe(); err != nil || len(exe) != 3000 {
		t.Fatalf("boot bruto: len=%d err=%v", len(exe), err)
	}
}

func TestCueNaoSaiDaPasta(t *testing.T) {
	dir := t.TempDir()
	cue := filepath.Join(dir, "x.cue")
	_ = os.WriteFile(cue, []byte(`FILE "../../etc/passwd" BINARY`), 0o644)
	got, err := cueBinary(cue)
	if err != nil || filepath.Dir(got) != dir {
		t.Fatalf("caminho escapou da pasta: %q %v", got, err)
	}
}

func TestErros(t *testing.T) {
	if _, err := New(bytes.NewReader(make([]byte, 40000)), 40000); !errors.Is(err, ErrFormato) {
		t.Fatalf("lixo deveria dar ErrFormato, veio %v", err)
	}
	iso := newBuilder().iso(sampleFiles())
	img, _ := New(bytes.NewReader(iso), int64(len(iso)))
	if _, err := img.ReadFile("NAO_EXISTE"); !errors.Is(err, ErrNaoExiste) {
		t.Fatalf("esperava ErrNaoExiste, veio %v", err)
	}
	// imagem truncada no meio do arquivo de boot não pode dar pânico
	cut := iso[:len(iso)-3000]
	img2, err := New(bytes.NewReader(cut), int64(len(cut)))
	if err == nil {
		if _, err = img2.ReadFile("SLUS_006.64"); err == nil {
			t.Fatal("esperava erro em imagem truncada")
		}
	}
}

// imagem com 40 setores em que dados "escondidos" (fora de qualquer arquivo do ISO) contêm texto
func imagemComDadosEscondidos(t *testing.T) (*Image, int64) {
	iso := newBuilder().iso(sampleFiles())
	for len(iso) < 40*userSize {
		iso = append(iso, 0)
	}
	hidden := int64(31*userSize - 2) // "Freya" atravessa a fronteira entre os setores 30 e 31
	copy(iso[hidden:], "Freya")
	copy(iso[35*userSize+100:], []byte{'r' + 0x20, 'e' + 0x20, 'y' + 0x20, 'a' + 0x20}) // "reya" numa tabela deslocada de 0x20
	copy(iso[37*userSize:], UTF16LE("Freya"))
	copy(iso[38*userSize+8:], "FREYA")
	img, err := New(bytes.NewReader(iso), int64(len(iso)))
	if err != nil {
		t.Fatal(err)
	}
	return img, hidden
}

func TestBuscaExataAtravessaSetores(t *testing.T) {
	img, hidden := imagemComDadosEscondidos(t)
	m, err := img.Search(5, ExactTest([]byte("Freya"), false), 10)
	if err != nil {
		t.Fatal(err)
	}
	if len(m) != 1 || m[0].Abs != hidden || m[0].LBA != 30 || m[0].Offset != userSize-2 {
		t.Fatalf("busca exata: %+v (esperado abs=%d, setor 30)", m, hidden)
	}
	// sem diferenciar maiúsculas, também acha "FREYA"
	m, _ = img.Search(5, ExactTest([]byte("freya"), true), 10)
	if len(m) != 2 || m[1].LBA != 38 || m[1].Offset != 8 {
		t.Errorf("busca sem diferenciar maiúsculas: %+v", m)
	}
	// o limite de resultados vale
	if m, _ := img.Search(5, ExactTest([]byte("freya"), true), 1); len(m) != 1 {
		t.Errorf("limite: %+v", m)
	}
}

func TestBuscaUTF16ERelativa(t *testing.T) {
	img, _ := imagemComDadosEscondidos(t)
	u := UTF16LE("Freya")
	m, _ := img.Search(len(u), ExactTest(u, false), 10)
	if len(m) != 1 || m[0].LBA != 37 || m[0].Offset != 0 {
		t.Errorf("UTF-16: %+v", m)
	}
	// busca relativa por "reya": acha a ASCII (setor 30/31) e a deslocada (setor 35)
	m, _ = img.Search(4, RelativeTest([]byte("reya")), 20)
	var sec35 bool
	for _, x := range m {
		sec35 = sec35 || (x.LBA == 35 && x.Offset == 100)
	}
	if !sec35 {
		t.Errorf("a busca relativa deveria achar a tabela deslocada no setor 35: %+v", m)
	}
}

func TestExtentsEReadUser(t *testing.T) {
	img, hidden := imagemComDadosEscondidos(t)
	ex, err := img.Extents()
	if err != nil || len(ex) != 2 {
		t.Fatalf("extents: %+v %v", ex, err)
	}
	var boot *Extent
	for k := range ex {
		if ex[k].Name == "SLUS_006.64" {
			boot = &ex[k]
		}
	}
	if boot == nil || boot.Size != 3000 || boot.LBA < 20 {
		t.Errorf("extent do boot: %+v", boot)
	}
	// lê através da fronteira dos setores 30 e 31
	b, err := img.ReadUser(hidden-1, 8)
	if err != nil || string(b[1:6]) != "Freya" {
		t.Errorf("ReadUser: %q %v", b, err)
	}
	// perto do fim devolve só o que existe
	b, err = img.ReadUser(int64(img.Sectors())*userSize-4, 100)
	if err != nil || len(b) != 4 {
		t.Errorf("fim da imagem: %d bytes, %v", len(b), err)
	}
	if _, err := img.ReadUser(int64(img.Sectors())*userSize, 4); err == nil {
		t.Error("além do fim deveria dar erro")
	}
}

func TestRelatoriosDeBuscaESetor(t *testing.T) {
	img, hidden := imagemComDadosEscondidos(t)
	out, err := img.FindReport(`"Freya"`, 5, ExactTest([]byte("Freya"), false), 10, 8)
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{
		"Ocorrências: 1", "## Setor 30 (0x1e), posição 0x7fe no setor", "FORA dos arquivos do ISO 9660 (dados lidos por setor)", "|", "Freya",
	} {
		if !strings.Contains(out, want) {
			t.Errorf("relatório sem %q:\n%s", want, out)
		}
	}
	if !strings.Contains(out, fmt.Sprintf("byte 0x%x dos dados", hidden)) {
		t.Errorf("deslocamento absoluto:\n%s", out)
	}
	// dado de um arquivo do ISO é reconhecido como tal
	ex, _ := img.Extents()
	var cnf Extent
	for _, e := range ex {
		if e.Name == "SYSTEM.CNF" {
			cnf = e
		}
	}
	rep, err := img.SectorReport(cnf.LBA, 64)
	if err != nil || !strings.Contains(rep, "dentro do arquivo SYSTEM.CNF") || !strings.Contains(rep, "BOOT") {
		t.Errorf("setor do SYSTEM.CNF (%v):\n%s", err, rep)
	}
	if _, err := img.SectorReport(9999, 16); err == nil {
		t.Error("setor fora da imagem deveria dar erro")
	}
	if none, _ := img.FindReport("x", 5, ExactTest([]byte("ZZZZZ"), false), 10, 4); !strings.Contains(none, "Nenhuma ocorrência") {
		t.Errorf("sem ocorrências:\n%s", none)
	}
	// Hexdump com linha curta e bytes não imprimíveis
	if h := Hexdump([]byte{'A', 0, 'B'}, 0x10); !strings.HasPrefix(h, "00000010: 41 00 42 ") || !strings.Contains(h, "|A.B|") {
		t.Errorf("hexdump: %q", h)
	}
}
