// Package disc lê imagens de CD do PS1 (.bin/.cue com setores brutos de 2352 bytes ou .iso de 2048)
// e o sistema de arquivos ISO 9660, em Go puro e somente leitura.
package disc

import (
	"bytes"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

const (
	userSize  = 2048
	rawSize   = 2352
	rawOffset = 24 // 12 sync + 4 cabeçalho + 8 subcabeçalho (Mode 2 Form 1)
	pvdLBA    = 16
)

var (
	ErrFormato   = errors.New("formato de imagem não reconhecido")
	ErrNaoExiste = errors.New("arquivo não encontrado na imagem")
)

var sync = []byte{0, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0}

// Image é uma imagem de disco já aberta. Guarda só o leitor, nunca o arquivo inteiro na memória.
type Image struct {
	r          io.ReaderAt
	size       int64
	sectorSize int64
	dataOffset int64
	closer     io.Closer
	// VolumeID lido do descritor primário.
	VolumeID string
	path     string // arquivo de dados aberto (o .bin, mesmo que se tenha aberto o .cue)
	root     entry
}

type entry struct {
	Name  string
	LBA   uint32
	Size  uint32
	IsDir bool
}

// Open abre .cue (segue o primeiro FILE), .bin ou .iso.
func Open(path string) (*Image, error) {
	if strings.EqualFold(filepath.Ext(path), ".cue") {
		bin, err := cueBinary(path)
		if err != nil {
			return nil, err
		}
		path = bin
	}
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	st, err := f.Stat()
	if err != nil {
		f.Close()
		return nil, err
	}
	img, err := New(f, st.Size())
	if err != nil {
		f.Close()
		return nil, err
	}
	img.closer = f
	img.path = path
	return img, nil
}

// BinPath devolve o arquivo de dados aberto (o .bin ou .iso; vazio se a imagem veio da memória).
func (i *Image) BinPath() string { return i.path }

// SectorSize devolve o tamanho de cada setor no arquivo: 2352 (bruto) ou 2048.
func (i *Image) SectorSize() int { return int(i.sectorSize) }

func (i *Image) Close() error {
	if i.closer != nil {
		return i.closer.Close()
	}
	return nil
}

var cueFile = regexp.MustCompile(`(?i)^\s*FILE\s+(?:"([^"]+)"|(\S+))`)

func cueBinary(cue string) (string, error) {
	raw, err := os.ReadFile(cue)
	if err != nil {
		return "", err
	}
	for _, line := range strings.Split(string(raw), "\n") {
		if m := cueFile.FindStringSubmatch(line); m != nil {
			name := m[1] + m[2]
			// o nome vem do arquivo de entrada: só aceita o nome base, nunca caminho para fora da pasta
			return filepath.Join(filepath.Dir(cue), filepath.Base(strings.ReplaceAll(name, `\`, "/"))), nil
		}
	}
	return "", fmt.Errorf("%w: .cue sem linha FILE", ErrFormato)
}

// New detecta o tamanho de setor e lê o descritor de volume primário.
func New(r io.ReaderAt, size int64) (*Image, error) {
	img := &Image{r: r, size: size}
	head := make([]byte, 12)
	if _, err := r.ReadAt(head, 0); err == nil && bytes.Equal(head, sync) {
		img.sectorSize, img.dataOffset = rawSize, rawOffset
	} else {
		img.sectorSize, img.dataOffset = userSize, 0
	}
	pvd, err := img.Sector(pvdLBA)
	if err != nil || string(pvd[1:6]) != "CD001" || pvd[0] != 1 {
		return nil, fmt.Errorf("%w: sem descritor ISO 9660 no setor 16", ErrFormato)
	}
	img.VolumeID = strings.TrimSpace(string(pvd[40:72]))
	root, err := parseRecord(pvd[156:190])
	if err != nil {
		return nil, err
	}
	img.root = root
	return img, nil
}

// Sector devolve os 2048 bytes de dados do setor lba.
func (i *Image) Sector(lba uint32) ([]byte, error) {
	off := int64(lba)*i.sectorSize + i.dataOffset
	if off+userSize > i.size {
		return nil, fmt.Errorf("setor %d fora da imagem (%d bytes)", lba, i.size)
	}
	buf := make([]byte, userSize)
	if _, err := i.r.ReadAt(buf, off); err != nil {
		return nil, err
	}
	return buf, nil
}

func parseRecord(b []byte) (entry, error) {
	if len(b) < 34 {
		return entry{}, fmt.Errorf("%w: registro de diretório truncado", ErrFormato)
	}
	nameLen := int(b[32])
	if 33+nameLen > len(b) {
		return entry{}, fmt.Errorf("%w: nome fora do registro", ErrFormato)
	}
	name := string(b[33 : 33+nameLen])
	switch name {
	case "\x00":
		name = "."
	case "\x01":
		name = ".."
	}
	if i := strings.IndexByte(name, ';'); i >= 0 {
		name = name[:i] // remove ";1"
	}
	return entry{
		Name:  name,
		LBA:   leU32(b[2:6]),
		Size:  leU32(b[10:14]),
		IsDir: b[25]&2 != 0,
	}, nil
}

func leU32(b []byte) uint32 {
	return uint32(b[0]) | uint32(b[1])<<8 | uint32(b[2])<<16 | uint32(b[3])<<24
}

// readDir lê todos os registros de um diretório, com limite de tamanho para imagens corrompidas.
func (i *Image) readDir(d entry) ([]entry, error) {
	if d.Size > 1<<20 {
		return nil, fmt.Errorf("%w: diretório com %d bytes", ErrFormato, d.Size)
	}
	var out []entry
	for off := uint32(0); off < d.Size; off += userSize {
		sec, err := i.Sector(d.LBA + off/userSize)
		if err != nil {
			return nil, err
		}
		for pos := 0; pos < userSize; {
			n := int(sec[pos])
			if n == 0 {
				break // resto do setor é preenchimento
			}
			if pos+n > userSize || n < 34 {
				return nil, fmt.Errorf("%w: registro inválido", ErrFormato)
			}
			e, err := parseRecord(sec[pos : pos+n])
			if err != nil {
				return nil, err
			}
			if e.Name != "." && e.Name != ".." {
				out = append(out, e)
			}
			pos += n
		}
	}
	return out, nil
}

// File descreve uma entrada de diretório.
type File struct {
	Name  string
	Size  uint32
	IsDir bool
}

// List lista um diretório ("/" ou "" para a raiz).
func (i *Image) List(dir string) ([]File, error) {
	d, err := i.lookup(dir)
	if err != nil {
		return nil, err
	}
	if !d.IsDir {
		return nil, fmt.Errorf("%q não é um diretório", dir)
	}
	es, err := i.readDir(d)
	if err != nil {
		return nil, err
	}
	out := make([]File, len(es))
	for k, e := range es {
		out[k] = File{e.Name, e.Size, e.IsDir}
	}
	return out, nil
}

func (i *Image) lookup(path string) (entry, error) {
	cur := i.root
	for _, part := range strings.FieldsFunc(path, func(r rune) bool { return r == '/' || r == '\\' }) {
		if !cur.IsDir {
			return entry{}, ErrNaoExiste
		}
		es, err := i.readDir(cur)
		if err != nil {
			return entry{}, err
		}
		found := false
		for _, e := range es {
			if strings.EqualFold(e.Name, part) {
				cur, found = e, true
				break
			}
		}
		if !found {
			return entry{}, fmt.Errorf("%w: %s", ErrNaoExiste, path)
		}
	}
	return cur, nil
}

// maxFile impede que uma imagem corrompida faça o programa alocar gigabytes.
const maxFile = 64 << 20

// ReadFile lê um arquivo inteiro da imagem.
func (i *Image) ReadFile(path string) ([]byte, error) {
	e, err := i.lookup(path)
	if err != nil {
		return nil, err
	}
	if e.IsDir {
		return nil, fmt.Errorf("%q é um diretório", path)
	}
	if e.Size > maxFile {
		return nil, fmt.Errorf("%q tem %d bytes, acima do limite de %d", path, e.Size, maxFile)
	}
	buf := make([]byte, 0, e.Size)
	for off := uint32(0); off < e.Size; off += userSize {
		sec, err := i.Sector(e.LBA + off/userSize)
		if err != nil {
			return nil, err
		}
		buf = append(buf, sec[:min(uint32(userSize), e.Size-off)]...)
	}
	return buf, nil
}

var bootLine = regexp.MustCompile(`(?im)^\s*BOOT\s*=\s*cdrom:\\?([^\s;]+)`)

// BootPath lê o SYSTEM.CNF e devolve o caminho do executável de boot (por exemplo SLUS_006.64).
func (i *Image) BootPath() (string, error) {
	cnf, err := i.ReadFile("SYSTEM.CNF")
	if err != nil {
		return "", err
	}
	m := bootLine.FindSubmatch(cnf)
	if m == nil {
		return "", fmt.Errorf("SYSTEM.CNF sem linha BOOT")
	}
	return strings.ReplaceAll(string(m[1]), `\`, "/"), nil
}

// BootExe devolve o nome e o conteúdo do executável de boot.
func (i *Image) BootExe() (string, []byte, error) {
	p, err := i.BootPath()
	if err != nil {
		return "", nil, err
	}
	b, err := i.ReadFile(p)
	return p, b, err
}

// Sectors devolve quantos setores de dados a imagem tem.
func (i *Image) Sectors() uint32 { return uint32(i.size / i.sectorSize) }

// ReadUser lê n bytes a partir do deslocamento abs na área de dados do usuário: 2048 bytes por setor, contíguos
// (sem o cabeçalho e o código de correção dos setores brutos).
func (i *Image) ReadUser(abs int64, n int) ([]byte, error) {
	if abs < 0 {
		return nil, fmt.Errorf("deslocamento negativo")
	}
	out := make([]byte, 0, n)
	for len(out) < n {
		lba := uint32((abs + int64(len(out))) / userSize)
		off := int((abs + int64(len(out))) % userSize)
		sec, err := i.Sector(lba)
		if err != nil {
			if len(out) > 0 {
				return out, nil // fim da imagem: devolve o que existe
			}
			return nil, err
		}
		out = append(out, sec[off:min(userSize, off+(n-len(out)))]...)
	}
	return out, nil
}

// Extent é um arquivo da raiz do ISO 9660 e onde ele começa no disco.
type Extent struct {
	Name      string
	LBA, Size uint32
}

// Extents lista os arquivos da raiz com o setor inicial e o tamanho. O que está fora deles não tem nome no ISO 9660.
func (i *Image) Extents() ([]Extent, error) {
	es, err := i.readDir(i.root)
	if err != nil {
		return nil, err
	}
	var out []Extent
	for _, e := range es {
		if !e.IsDir {
			out = append(out, Extent{e.Name, e.LBA, e.Size})
		}
	}
	return out, nil
}

// Match é uma ocorrência achada por Search.
type Match struct {
	Abs    int64  // deslocamento na área de dados do usuário
	LBA    uint32 // setor
	Offset int    // posição dentro do setor
}

// Search varre os dados de TODOS os setores (inclusive os que não pertencem a nenhum arquivo do ISO 9660) e devolve
// até max posições onde test(janela) é verdadeiro, com janelas de window bytes. Uma ocorrência pode atravessar a
// fronteira entre dois setores.
func (i *Image) Search(window int, test func([]byte) bool, max int) ([]Match, error) {
	if window < 1 {
		return nil, fmt.Errorf("janela inválida")
	}
	var out []Match
	var carry []byte
	var base int64
	for lba := uint32(0); lba < i.Sectors(); lba++ {
		sec, err := i.Sector(lba)
		if err != nil {
			return out, err
		}
		buf := append(carry, sec...)
		for p := 0; p+window <= len(buf); p++ {
			if test(buf[p : p+window]) {
				abs := base + int64(p)
				out = append(out, Match{Abs: abs, LBA: uint32(abs / userSize), Offset: int(abs % userSize)})
				if len(out) >= max {
					return out, nil
				}
			}
		}
		keep := min(window-1, len(buf))
		carry = append([]byte(nil), buf[len(buf)-keep:]...)
		base += int64(len(buf) - keep)
	}
	return out, nil
}

// ExactTest compara a janela com pat; com fold, ignora maiúsculas e minúsculas ASCII.
func ExactTest(pat []byte, fold bool) func([]byte) bool {
	p := append([]byte(nil), pat...)
	if fold {
		for k := range p {
			p[k] = lowerASCII(p[k])
		}
	}
	return func(w []byte) bool {
		for k := range p {
			b := w[k]
			if fold {
				b = lowerASCII(b)
			}
			if b != p[k] {
				return false
			}
		}
		return true
	}
}

func lowerASCII(b byte) byte {
	if b >= 'A' && b <= 'Z' {
		return b + 0x20
	}
	return b
}

// RelativeTest acha texto em codificação desconhecida: só exige que as diferenças entre bytes consecutivos sejam
// as mesmas das letras de word (por exemplo, 'r','e','y','a' em qualquer tabela em que as letras minúsculas sejam
// consecutivas). Dá falsos positivos: confira o contexto. Palavras curtas dão muitos.
func RelativeTest(word []byte) func([]byte) bool {
	d := make([]byte, len(word)-1)
	for k := 1; k < len(word); k++ {
		d[k-1] = word[k] - word[k-1]
	}
	return func(w []byte) bool {
		for k := range d {
			if w[k+1]-w[k] != d[k] {
				return false
			}
		}
		return true
	}
}

// UTF16LE codifica ASCII como UTF-16 little-endian (cada caractere seguido de um zero).
func UTF16LE(s string) []byte {
	out := make([]byte, 0, 2*len(s))
	for _, b := range []byte(s) {
		out = append(out, b, 0)
	}
	return out
}
