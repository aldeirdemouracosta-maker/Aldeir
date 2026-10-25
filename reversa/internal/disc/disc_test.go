package disc

import (
	"bytes"
	"encoding/binary"
	"errors"
	"os"
	"path/filepath"
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
