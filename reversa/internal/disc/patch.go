package disc

import (
	"bytes"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

// BytePatch troca bytes na área de dados do usuário (os mesmos deslocamentos que find e sector mostram).
type BytePatch struct {
	Abs  int64
	Data []byte
}

var cueFileLine = regexp.MustCompile(`(?im)^(\s*FILE\s+)(?:"[^"]+"|\S+)(\s+\S+.*)$`)

// CopyAndPatch cria uma CÓPIA da imagem com os bytes trocados. O original nunca é aberto para escrita.
// out é o caminho do novo .cue, .bin ou .iso, com a mesma extensão da entrada. Recusa sobrescrever um arquivo
// existente e só aceita .cue com um único arquivo de dados. Não recalcula os códigos de correção (EDC/ECC) dos
// setores brutos: emuladores os ignoram, mas um disco gravado de verdade poderia recusar.
func CopyAndPatch(src, out string, patches []BytePatch) ([]string, error) {
	if len(patches) == 0 {
		return nil, fmt.Errorf("nenhuma alteração pedida")
	}
	if same(src, out) {
		return nil, fmt.Errorf("a saída é o próprio original; escolha outro nome")
	}
	if !strings.EqualFold(filepath.Ext(src), filepath.Ext(out)) {
		return nil, fmt.Errorf("a saída deve ter a mesma extensão da entrada (%s)", filepath.Ext(src))
	}
	img, err := Open(src)
	if err != nil {
		return nil, err
	}
	defer img.Close()
	for _, p := range patches {
		if p.Abs < 0 || p.Abs+int64(len(p.Data)) > int64(img.Sectors())*userSize {
			return nil, fmt.Errorf("alteração em 0x%x (%d bytes) fora da imagem de %d bytes de dados", p.Abs, len(p.Data), int64(img.Sectors())*userSize)
		}
	}
	var written []string
	dstBin := out
	isCue := strings.EqualFold(filepath.Ext(src), ".cue")
	if isCue {
		cueText, err := os.ReadFile(src)
		if err != nil {
			return nil, err
		}
		if n := len(cueFileLine.FindAllString(string(cueText), -1)); n != 1 {
			return nil, fmt.Errorf("o .cue tem %d arquivos de dados; só aceito um (.bin único)", n)
		}
		dstBin = strings.TrimSuffix(out, filepath.Ext(out)) + ".bin"
		newCue := cueFileLine.ReplaceAllString(string(cueText), `${1}"`+filepath.Base(dstBin)+`"${2}`)
		if _, err := os.Stat(out); err == nil {
			return nil, fmt.Errorf("%s já existe; não sobrescrevo", out)
		}
		if err := os.WriteFile(out, []byte(newCue), 0o644); err != nil {
			return nil, err
		}
		written = append(written, out)
	}
	if _, err := os.Stat(dstBin); err == nil {
		return written, fmt.Errorf("%s já existe; não sobrescrevo", dstBin)
	}
	in, err := os.Open(img.BinPath())
	if err != nil {
		return written, err
	}
	defer in.Close()
	f, err := os.OpenFile(dstBin, os.O_CREATE|os.O_EXCL|os.O_RDWR, 0o644)
	if err != nil {
		return written, err
	}
	if _, err := io.Copy(f, in); err != nil {
		f.Close()
		return written, err
	}
	written = append(written, dstBin)
	for _, p := range patches {
		for done := 0; done < len(p.Data); {
			abs := p.Abs + int64(done)
			lba, off := abs/userSize, int(abs%userSize)
			n := min(len(p.Data)-done, userSize-off)
			if _, err := f.WriteAt(p.Data[done:done+n], lba*img.sectorSize+img.dataOffset+int64(off)); err != nil {
				f.Close()
				return written, err
			}
			done += n
		}
	}
	if err := f.Close(); err != nil {
		return written, err
	}
	// confere relendo a cópia
	chk, err := Open(out)
	if err != nil {
		return written, fmt.Errorf("a cópia não abre como imagem: %w", err)
	}
	defer chk.Close()
	for _, p := range patches {
		got, err := chk.ReadUser(p.Abs, len(p.Data))
		if err != nil || !bytes.Equal(got, p.Data) {
			return written, fmt.Errorf("verificação falhou em 0x%x: gravado %x, esperado %x (%v)", p.Abs, got, p.Data, err)
		}
	}
	return written, nil
}

func same(a, b string) bool {
	ab, e1 := filepath.Abs(a)
	bb, e2 := filepath.Abs(b)
	return e1 == nil && e2 == nil && strings.EqualFold(ab, bb)
}

// DiffReport compara os dados de usuário de duas imagens e lista as regiões diferentes.
func DiffReport(a, b *Image, maxRanges int) (string, error) {
	n := min(a.Sectors(), b.Sectors())
	type rng struct{ start, end int64 }
	var rs []rng
	var truncated bool
	for lba := uint32(0); lba < n; lba++ {
		sa, err := a.Sector(lba)
		if err != nil {
			return "", err
		}
		sb, err := b.Sector(lba)
		if err != nil {
			return "", err
		}
		if bytes.Equal(sa, sb) {
			continue
		}
		for k := 0; k < userSize; k++ {
			if sa[k] == sb[k] {
				continue
			}
			abs := int64(lba)*userSize + int64(k)
			if len(rs) > 0 && abs <= rs[len(rs)-1].end+16 { // junta alterações próximas
				rs[len(rs)-1].end = abs + 1
			} else {
				if len(rs) >= maxRanges {
					truncated = true
					break
				}
				rs = append(rs, rng{abs, abs + 1})
			}
		}
		if truncated {
			break
		}
	}
	var sb strings.Builder
	fmt.Fprintf(&sb, "# Diferenças entre as imagens\n\n")
	if a.Sectors() != b.Sectors() {
		fmt.Fprintf(&sb, "- AVISO: tamanhos diferentes (%d e %d setores); comparados os %d primeiros\n", a.Sectors(), b.Sectors(), n)
	}
	fmt.Fprintf(&sb, "- Regiões diferentes: %d%s\n", len(rs), map[bool]string{true: " (limite atingido: pode haver mais)", false: ""}[truncated])
	for _, r := range rs {
		size := int(r.end - r.start)
		va, _ := a.ReadUser(r.start, min(size, 32))
		vb, _ := b.ReadUser(r.start, min(size, 32))
		fmt.Fprintf(&sb, "\n## Byte 0x%x, setor %d, posição 0x%x, %d byte(s)\n\n- Local: %s\n\n```\noriginal:\n%salterado:\n%s```\n",
			r.start, r.start/userSize, r.start%userSize, size, a.where(uint32(r.start/userSize)), Hexdump(va, r.start), Hexdump(vb, r.start))
	}
	if len(rs) == 0 {
		sb.WriteString("\nAs imagens são idênticas nos dados do usuário.\n")
	}
	return sb.String(), nil
}
