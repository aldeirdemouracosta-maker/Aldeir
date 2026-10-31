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

// buildHidden monta os bytes de um ISO de 40 setores em que dados "escondidos" (fora de qualquer arquivo) contêm texto.
func buildHidden() ([]byte, int64) {
	iso := newBuilder().iso(sampleFiles())
	for len(iso) < 40*userSize {
		iso = append(iso, 0)
	}
	hidden := int64(31*userSize - 2) // "Freya" atravessa a fronteira entre os setores 30 e 31
	copy(iso[hidden:], "Freya")
	copy(iso[35*userSize+100:], []byte{'r' + 0x20, 'e' + 0x20, 'y' + 0x20, 'a' + 0x20}) // "reya" numa tabela deslocada de 0x20
	copy(iso[37*userSize:], UTF16LE("Freya"))
	copy(iso[38*userSize+8:], "FREYA")
	return iso, hidden
}

func imagemComDadosEscondidos(t *testing.T) (*Image, int64) {
	iso, hidden := buildHidden()
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

// grava um .bin bruto (2352 por setor) e um .cue numa pasta temporária
func gravaCueBruto(t *testing.T, dir string) (cue, bin string, hidden int64) {
	iso, hidden := buildHidden()
	bin = filepath.Join(dir, "jogo.bin")
	cue = filepath.Join(dir, "jogo.cue")
	if err := os.WriteFile(bin, raw(iso), 0o644); err != nil {
		t.Fatal(err)
	}
	text := "FILE \"jogo.bin\" BINARY\r\n  TRACK 01 MODE2/2352\r\n    INDEX 01 00:00:00\r\n"
	if err := os.WriteFile(cue, []byte(text), 0o644); err != nil {
		t.Fatal(err)
	}
	return cue, bin, hidden
}

func TestCopiaComPatchNaoTocaNoOriginal(t *testing.T) {
	dir := t.TempDir()
	cue, bin, hidden := gravaCueBruto(t, dir)
	before, _ := os.ReadFile(bin)
	out := filepath.Join(dir, "novo.cue")
	// troca "Freya" por "Frxya" atravessando a fronteira entre os setores 30 e 31 (2 bytes de cada lado)
	written, err := CopyAndPatch(cue, out, []BytePatch{{Abs: hidden, Data: []byte("Frxya")}})
	if err != nil {
		t.Fatal(err)
	}
	if len(written) != 2 || written[0] != out || filepath.Base(written[1]) != "novo.bin" {
		t.Fatalf("arquivos gravados: %v", written)
	}
	// o original continua idêntico
	after, _ := os.ReadFile(bin)
	if !bytes.Equal(before, after) {
		t.Fatal("o .bin original foi alterado")
	}
	// o novo .cue aponta para o novo .bin e o conteúdo mudou onde pedido
	cueText, _ := os.ReadFile(out)
	if !strings.Contains(string(cueText), `FILE "novo.bin" BINARY`) || !strings.Contains(string(cueText), "TRACK 01 MODE2/2352") {
		t.Errorf("novo .cue: %q", cueText)
	}
	novo, err := Open(out)
	if err != nil {
		t.Fatal(err)
	}
	defer novo.Close()
	got, _ := novo.ReadUser(hidden, 5)
	if string(got) != "Frxya" {
		t.Errorf("conteúdo do patch: %q", got)
	}
	// o cabeçalho bruto dos setores continua válido (a imagem ainda abre e o resto é igual)
	orig, _ := Open(cue)
	defer orig.Close()
	rep, err := DiffReport(orig, novo, 10)
	if err != nil || !strings.Contains(rep, "Regiões diferentes: 1") || !strings.Contains(rep, "1 byte(s)") ||
		!strings.Contains(rep, fmt.Sprintf("Byte 0x%x", hidden+2)) || !strings.Contains(rep, "FORA dos arquivos") {
		t.Errorf("diff (%v):\n%s", err, rep)
	}
	same, _ := DiffReport(orig, orig, 10)
	if !strings.Contains(same, "idênticas") {
		t.Errorf("diff de imagem consigo mesma:\n%s", same)
	}
}

func TestPatchRecusaCasosPerigosos(t *testing.T) {
	dir := t.TempDir()
	cue, bin, hidden := gravaCueBruto(t, dir)
	ok := []BytePatch{{Abs: hidden, Data: []byte("X")}}
	if _, err := CopyAndPatch(cue, cue, ok); err == nil || !strings.Contains(err.Error(), "próprio original") {
		t.Errorf("mesmo arquivo: %v", err)
	}
	if _, err := CopyAndPatch(cue, filepath.Join(dir, "x.bin"), ok); err == nil || !strings.Contains(err.Error(), "mesma extensão") {
		t.Errorf("extensão diferente: %v", err)
	}
	if _, err := CopyAndPatch(cue, filepath.Join(dir, "n.cue"), nil); err == nil {
		t.Error("sem alterações deveria dar erro")
	}
	if _, err := CopyAndPatch(cue, filepath.Join(dir, "n.cue"), []BytePatch{{Abs: 40 * userSize, Data: []byte("X")}}); err == nil || !strings.Contains(err.Error(), "fora da imagem") {
		t.Errorf("fora da imagem: %v", err)
	}
	// não sobrescreve saída existente
	if _, err := CopyAndPatch(cue, filepath.Join(dir, "n.cue"), ok); err != nil {
		t.Fatal(err)
	}
	if _, err := CopyAndPatch(cue, filepath.Join(dir, "n.cue"), ok); err == nil || !strings.Contains(err.Error(), "já existe") {
		t.Errorf("sobrescrita: %v", err)
	}
	// o .bin original continua sem alteração mesmo depois de tudo isso
	if got, _ := os.ReadFile(bin); !bytes.Equal(got, raw(func() []byte { i, _ := buildHidden(); return i }())) {
		t.Error("o original mudou")
	}
	// .cue com dois arquivos de dados não é suportado
	dois := filepath.Join(dir, "dois.cue")
	_ = os.WriteFile(dois, []byte("FILE \"jogo.bin\" BINARY\r\n FILE \"audio.bin\" BINARY\r\n"), 0o644)
	if _, err := CopyAndPatch(dois, filepath.Join(dir, "d2.cue"), ok); err == nil || !strings.Contains(err.Error(), "2 arquivos de dados") {
		t.Errorf("cue com 2 arquivos: %v", err)
	}
}

func TestPatchEmIsoDe2048(t *testing.T) {
	dir := t.TempDir()
	iso, hidden := buildHidden()
	src := filepath.Join(dir, "jogo.iso")
	_ = os.WriteFile(src, iso, 0o644)
	out := filepath.Join(dir, "novo.iso")
	if _, err := CopyAndPatch(src, out, []BytePatch{{Abs: hidden, Data: []byte("Frxya")}}); err != nil {
		t.Fatal(err)
	}
	novo, err := Open(out)
	if err != nil {
		t.Fatal(err)
	}
	defer novo.Close()
	if got, _ := novo.ReadUser(hidden, 5); string(got) != "Frxya" {
		t.Errorf("patch em ISO: %q", got)
	}
}

// monta um disco bruto com recursos conhecidos escondidos fora dos arquivos do ISO
func discoComRecursos(t *testing.T) (*Image, map[string]int64) {
	iso := newBuilder().iso(sampleFiles())
	for len(iso) < 60*userSize {
		iso = append(iso, 0)
	}
	at := map[string]int64{"tim": 30*userSize + 16, "vag": 31*userSize - 2, "vab": 33 * userSize, "seq": 34*userSize + 5, "timRGB": 36 * userSize}
	// TIM 4bpp com paleta de 16 cores x 1 linha: bloco de paleta 12+32 = 44 bytes; imagem 8x4 em unidades de 16 bits
	clut := []byte{0x10, 0, 0, 0, 0x08, 0, 0, 0, 44, 0, 0, 0, 0, 0, 0, 0, 16, 0, 1, 0}
	copy(iso[at["tim"]:], clut)
	copy(iso[at["tim"]+8+44:], []byte{12 + 8*4*2, 0, 0, 0, 0, 0, 0, 0, 8, 0, 4, 0})
	copy(iso[at["vag"]:], "VAGp")
	copy(iso[at["vab"]:], "pBAV")
	copy(iso[at["seq"]:], "pQES")
	// cabeçalho que lembra TIM mas com tamanho incoerente: não pode ser contado
	copy(iso[at["timRGB"]:], []byte{0x10, 0, 0, 0, 0x08, 0, 0, 0, 99, 0, 0, 0, 0, 0, 0, 0, 16, 0, 1, 0})
	data := raw(iso)
	// setores 50..54: áudio XA (submodo Form 2 + áudio), arquivo 1, canal 2; 55: outro canal; 56: dados comuns
	for lba := 50; lba <= 55; lba++ {
		ch := byte(2)
		if lba == 55 {
			ch = 3
		}
		copy(data[lba*rawSize+16:], []byte{1, ch, 0x64, 0x01, 1, ch, 0x64, 0x01})
	}
	img, err := New(bytes.NewReader(data), int64(len(data)))
	if err != nil {
		t.Fatal(err)
	}
	return img, at
}

func TestScanInventariaRecursos(t *testing.T) {
	img, at := discoComRecursos(t)
	res, err := img.Scan(10)
	if err != nil {
		t.Fatal(err)
	}
	for kind, want := range map[string]int{"TIM": 1, "VAG": 1, "VAB": 1, "SEQ": 1} {
		if res.Counts[kind] != want {
			t.Errorf("%s: %d achados, esperado %d (o falso TIM de tamanho incoerente não conta)", kind, res.Counts[kind], want)
		}
	}
	var tim *Asset
	for k := range res.Assets {
		if res.Assets[k].Kind == "TIM" {
			tim = &res.Assets[k]
		}
	}
	if tim == nil || tim.Abs != at["tim"] || !strings.Contains(tim.Detail, "4 bpp com paleta de 16 cores × 1 linha(s)") || !strings.Contains(tim.Detail, "imagem 32×4 pixels") {
		t.Errorf("detalhe do TIM: %+v", tim)
	}
	// o VAG atravessa a fronteira entre setores e ainda é achado
	for _, a := range res.Assets {
		if a.Kind == "VAG" && a.Abs != at["vag"] {
			t.Errorf("posição do VAG: %+v", a)
		}
	}
	// áudio XA: 5 setores no canal 2 e 1 no canal 3, em duas faixas
	if res.XASectors != 6 || len(res.XA) != 2 || res.XA[0].Start != 50 || res.XA[0].Count != 5 || res.XA[0].Channel != 2 || res.XA[1].Channel != 3 {
		t.Errorf("áudio XA: setores=%d faixas=%+v", res.XASectors, res.XA)
	}
	rep := res.Report(img)
	for _, want := range []string{"TIM: 1 achado(s)", "VAB: 1", "Áudio XA: 6 setor(es) em 2 faixa(s)", "setor 50 a 54 (5 setores): arquivo 1, canal 2", "FORA dos arquivos do ISO 9660", "Limites:"} {
		if !strings.Contains(rep, want) {
			t.Errorf("relatório sem %q:\n%s", want, rep)
		}
	}
	// o limite de listagem não altera as contagens
	small, _ := img.Scan(0)
	if small.Counts["TIM"] != 1 || len(small.Assets) != 0 || !small.ListLimited {
		t.Errorf("limite de listagem: %+v", small)
	}
	// imagem que não é bruta: sem XA, e o relatório avisa
	iso := newBuilder().iso(sampleFiles())
	plain, _ := New(bytes.NewReader(iso), int64(len(iso)))
	r2, _ := plain.Scan(5)
	if r2.XASectors != 0 || !strings.Contains(r2.Report(plain), "não dá para detectar") {
		t.Errorf("imagem de 2048: %+v", r2)
	}
}
