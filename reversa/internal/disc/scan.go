package disc

import (
	"encoding/binary"
	"fmt"
	"sort"
	"strings"
)

// Asset é um recurso de formato conhecido achado nos dados do disco.
type Asset struct {
	Kind   string // TIM, VAG, VAB, SEQ
	Abs    int64
	LBA    uint32
	Offset int
	Detail string
}

// XARange é uma sequência contígua de setores de áudio XA com o mesmo arquivo e canal.
type XARange struct {
	Start, Count      uint32
	File, Channel, Cd byte
}

// ScanResult é o inventário do disco.
type ScanResult struct {
	Assets      []Asset
	Counts      map[string]int
	XA          []XARange
	XASectors   uint32
	ListLimited bool // há mais achados do que os listados
}

const scanWindow = 20

// tim reconhece o cabeçalho de uma imagem TIM do PS1 (bloco de paleta ou de pixels) e valida o tamanho do bloco:
// size == largura*altura*2 + 12. Devolve se vale e o detalhe parcial.
func tim(w []byte) (ok bool, flags uint32, size uint32, wd, ht uint16) {
	if binary.LittleEndian.Uint32(w[0:4]) != 0x10 {
		return
	}
	flags = binary.LittleEndian.Uint32(w[4:8])
	if flags > 0x0B || flags&0x4 != 0 {
		return
	}
	size = binary.LittleEndian.Uint32(w[8:12])
	wd, ht = binary.LittleEndian.Uint16(w[16:18]), binary.LittleEndian.Uint16(w[18:20])
	if wd == 0 || ht == 0 || size > 1<<22 || size != uint32(wd)*uint32(ht)*2+12 {
		return
	}
	return true, flags, size, wd, ht
}

// Scan varre TODOS os setores atrás de imagens TIM, bancos de som (VAB), amostras (VAG) e sequências (SEQ), e, se a
// imagem é bruta (2352 por setor), das faixas de áudio XA pelo subcabeçalho dos setores. list limita quantos achados
// de cada tipo são listados; as contagens são completas.
func (i *Image) Scan(list int) (ScanResult, error) {
	res := ScanResult{Counts: map[string]int{}}
	shown := map[string]int{}
	add := func(kind string, abs int64, detail string) {
		res.Counts[kind]++
		if shown[kind] >= list {
			res.ListLimited = true
			return
		}
		shown[kind]++
		res.Assets = append(res.Assets, Asset{Kind: kind, Abs: abs, LBA: uint32(abs / userSize), Offset: int(abs % userSize), Detail: detail})
	}
	var carry []byte
	var base int64
	for lba := uint32(0); lba < i.Sectors(); lba++ {
		sec, err := i.Sector(lba)
		if err != nil {
			return res, err
		}
		buf := append(carry, sec...)
		for p := 0; p+scanWindow <= len(buf); p++ {
			w := buf[p : p+scanWindow]
			abs := base + int64(p)
			switch {
			case w[0] == 'V' && w[1] == 'A' && w[2] == 'G' && w[3] == 'p':
				add("VAG", abs, "amostra de áudio (VAGp)")
			case w[0] == 'p' && w[1] == 'B' && w[2] == 'A' && w[3] == 'V':
				add("VAB", abs, "banco de sons (pBAV)")
			case w[0] == 'p' && w[1] == 'Q' && w[2] == 'E' && w[3] == 'S':
				add("SEQ", abs, "sequência musical (pQES)")
			default:
				if ok, flags, size, wd, ht := tim(w); ok {
					add("TIM", abs, i.timDetail(abs, flags, size, wd, ht))
				}
			}
		}
		keep := min(scanWindow-1, len(buf))
		carry = append([]byte(nil), buf[len(buf)-keep:]...)
		base += int64(len(buf) - keep)
	}
	i.scanXA(&res)
	return res, nil
}

func (i *Image) timDetail(abs int64, flags, size uint32, wd, ht uint16) string {
	bpp := [4]string{"4 bpp", "8 bpp", "16 bpp", "24 bpp"}[flags&3]
	if flags&8 == 0 {
		return fmt.Sprintf("%s sem paleta, pixels %d×%d (em unidades de 16 bits)", bpp, wd, ht)
	}
	// o primeiro bloco é a paleta: wd cores por linha, ht linhas (= paletas, se 16 ou 256 cores cada)
	d := fmt.Sprintf("%s com paleta de %d cores × %d linha(s)", bpp, wd, ht)
	hdr, err := i.ReadUser(abs+8+int64(size), 12)
	if err == nil && len(hdr) == 12 {
		w16, h := binary.LittleEndian.Uint16(hdr[8:10]), binary.LittleEndian.Uint16(hdr[10:12])
		px := map[uint32]int{0: 4, 1: 2, 2: 1}[flags&3] * int(w16)
		if flags&3 == 3 {
			px = int(w16) * 2 / 3
		}
		d += fmt.Sprintf("; imagem %d×%d pixels", px, h)
	}
	return d
}

// scanXA lê o subcabeçalho dos setores brutos: submodo 0x04 = áudio. Só funciona em imagens de 2352 bytes por setor.
func (i *Image) scanXA(res *ScanResult) {
	if i.sectorSize != rawSize {
		return
	}
	var cur *XARange
	for lba := uint32(0); lba < i.Sectors(); lba++ {
		var sh [8]byte
		if _, err := i.r.ReadAt(sh[:], int64(lba)*rawSize+16); err != nil {
			return
		}
		file, ch, sub, cd := sh[0], sh[1], sh[2], sh[3]
		if sub&0x04 == 0 || sub&0x20 == 0 { // áudio XA é Form 2 com o bit de áudio
			cur = nil
			continue
		}
		res.XASectors++
		if cur != nil && cur.File == file && cur.Channel == ch && cur.Cd == cd && cur.Start+cur.Count == lba {
			cur.Count++
			res.XA[len(res.XA)-1].Count = cur.Count
			continue
		}
		res.XA = append(res.XA, XARange{Start: lba, Count: 1, File: file, Channel: ch, Cd: cd})
		cur = &res.XA[len(res.XA)-1]
	}
}

// Report formata o inventário.
func (r ScanResult) Report(i *Image) string {
	var b strings.Builder
	b.WriteString("# Inventário do disco\n\n")
	fmt.Fprintf(&b, "- Setores de dados: %d\n", i.Sectors())
	kinds := make([]string, 0, len(r.Counts))
	for k := range r.Counts {
		kinds = append(kinds, k)
	}
	sort.Strings(kinds)
	for _, k := range kinds {
		fmt.Fprintf(&b, "- %s: %d achado(s)\n", k, r.Counts[k])
	}
	if len(kinds) == 0 {
		b.WriteString("- Nenhuma imagem TIM, VAB, VAG ou SEQ reconhecida nos dados (podem estar comprimidos ou em formato próprio)\n")
	}
	if i.sectorSize == rawSize {
		fmt.Fprintf(&b, "- Áudio XA: %d setor(es) em %d faixa(s)\n", r.XASectors, len(r.XA))
	} else {
		b.WriteString("- Áudio XA: não dá para detectar (a imagem não é bruta, 2352 bytes por setor)\n")
	}
	if r.ListLimited {
		b.WriteString("- Há mais achados do que os listados (limite por tipo); as contagens acima são completas\n")
	}
	b.WriteString("\n## Achados\n\n")
	for _, a := range r.Assets {
		fmt.Fprintf(&b, "- %s no setor %d (0x%x), posição 0x%x, byte 0x%x: %s; %s\n", a.Kind, a.LBA, a.LBA, a.Offset, a.Abs, a.Detail, i.where(a.LBA))
	}
	if len(r.XA) > 0 {
		b.WriteString("\n## Faixas de áudio XA\n\n")
		for k, x := range r.XA {
			if k >= 60 {
				fmt.Fprintf(&b, "- ... e mais %d faixa(s)\n", len(r.XA)-k)
				break
			}
			fmt.Fprintf(&b, "- setor %d a %d (%d setores): arquivo %d, canal %d, codificação 0x%02x\n", x.Start, x.Start+x.Count-1, x.Count, x.File, x.Channel, x.Cd)
		}
	}
	b.WriteString("\nLimites: reconheço só formatos sem compressão e pelo cabeçalho. Dados comprimidos ou em formato próprio não aparecem aqui, e um achado não prova que o jogo o usa (nem que não usa).\n")
	return b.String()
}
