// Package tim lê imagens TIM do PS1 (sprites, fundos, paletas) e as converte em imagens comuns.
package tim

import (
	"encoding/binary"
	"fmt"
	"image"
	"image/color"
)

// TIM é uma imagem TIM já interpretada.
type TIM struct {
	BPP          int      // 4, 8, 16 ou 24
	CLUT         []uint16 // cores da paleta (15 bits BGR); vazio se não há paleta
	ClutW, ClutH int
	ImgW16, H    int // largura em unidades de 16 bits, e altura
	Pix          []byte
	Total        int // bytes que a imagem ocupa no arquivo
}

var le = binary.LittleEndian

// Parse interpreta os bytes de um TIM, validando os tamanhos dos blocos.
func Parse(b []byte) (*TIM, error) {
	if len(b) < 20 || le.Uint32(b[0:4]) != 0x10 {
		return nil, fmt.Errorf("não é um TIM (cabeçalho 0x10 ausente)")
	}
	flags := le.Uint32(b[4:8])
	if flags > 0x0B || flags&0x4 != 0 {
		return nil, fmt.Errorf("flags de TIM inválidas: 0x%x", flags)
	}
	t := &TIM{BPP: [4]int{4, 8, 16, 24}[flags&3]}
	pos := 8
	if flags&8 != 0 {
		size := int(le.Uint32(b[pos:]))
		w, h := int(le.Uint16(b[pos+8:])), int(le.Uint16(b[pos+10:]))
		if w == 0 || h == 0 || size != w*h*2+12 || pos+size > len(b) {
			return nil, fmt.Errorf("bloco de paleta inválido (tamanho %d, %d×%d, arquivo com %d bytes)", size, w, h, len(b))
		}
		t.ClutW, t.ClutH = w, h
		t.CLUT = make([]uint16, w*h)
		for k := range t.CLUT {
			t.CLUT[k] = le.Uint16(b[pos+12+2*k:])
		}
		pos += size
	} else if t.BPP <= 8 {
		return nil, fmt.Errorf("TIM de %d bpp sem paleta não é suportado", t.BPP)
	}
	if pos+12 > len(b) {
		return nil, fmt.Errorf("bloco de imagem ausente")
	}
	size := int(le.Uint32(b[pos:]))
	w, h := int(le.Uint16(b[pos+8:])), int(le.Uint16(b[pos+10:]))
	if w == 0 || h == 0 || w > 1024 || h > 1024 || size != w*h*2+12 || pos+size > len(b) {
		return nil, fmt.Errorf("bloco de imagem inválido (tamanho %d, %d×%d, arquivo com %d bytes)", size, w, h, len(b))
	}
	t.ImgW16, t.H = w, h
	t.Pix = b[pos+12 : pos+size]
	t.Total = pos + size
	return t, nil
}

// Width devolve a largura em pixels.
func (t *TIM) Width() int {
	switch t.BPP {
	case 4:
		return t.ImgW16 * 4
	case 8:
		return t.ImgW16 * 2
	case 16:
		return t.ImgW16
	}
	return t.ImgW16 * 2 / 3
}

func (t *TIM) colorsPerPalette() int {
	if t.BPP == 4 {
		return 16
	}
	return 256
}

// Palettes diz quantas paletas completas a imagem tem (cada linha de 16 cores em 4 bpp, de 256 em 8 bpp).
func (t *TIM) Palettes() int {
	if len(t.CLUT) == 0 {
		return 0
	}
	return max(1, len(t.CLUT)/t.colorsPerPalette())
}

// rgb converte uma cor de 15 bits do PS1 (bits 0-4 vermelho, 5-9 verde, 10-14 azul). O valor 0x0000 é transparente.
func rgb(v uint16) color.NRGBA {
	e := func(c uint16) uint8 { return uint8(c<<3 | c>>2) }
	if v == 0 {
		return color.NRGBA{}
	}
	return color.NRGBA{R: e(v & 31), G: e(v >> 5 & 31), B: e(v >> 10 & 31), A: 255}
}

// Render desenha a imagem usando a paleta pal (ignorada em 16 e 24 bpp).
func (t *TIM) Render(pal int) (*image.NRGBA, error) {
	w := t.Width()
	img := image.NewNRGBA(image.Rect(0, 0, w, t.H))
	var colors []uint16
	if t.BPP <= 8 {
		if pal < 0 || pal >= t.Palettes() {
			return nil, fmt.Errorf("paleta %d não existe (a imagem tem %d)", pal, t.Palettes())
		}
		n := t.colorsPerPalette()
		colors = t.CLUT[pal*n : min(len(t.CLUT), (pal+1)*n)]
	}
	stride := t.ImgW16 * 2
	pick := func(i int) color.NRGBA {
		if i < len(colors) {
			return rgb(colors[i])
		}
		return color.NRGBA{}
	}
	for y := 0; y < t.H; y++ {
		row := t.Pix[y*stride : (y+1)*stride]
		for x := 0; x < w; x++ {
			switch t.BPP {
			case 4:
				v := row[x/2]
				if x%2 == 0 {
					v &= 0xF // o pixel da esquerda fica no nibble baixo
				} else {
					v >>= 4
				}
				img.SetNRGBA(x, y, pick(int(v)))
			case 8:
				img.SetNRGBA(x, y, pick(int(row[x])))
			case 16:
				img.SetNRGBA(x, y, rgb(le.Uint16(row[2*x:])))
			case 24:
				img.SetNRGBA(x, y, color.NRGBA{R: row[3*x], G: row[3*x+1], B: row[3*x+2], A: 255})
			}
		}
	}
	return img, nil
}

// Sheet junta todas as paletas numa folha, em grade de até 4 colunas, para comparar variações de cor.
func (t *TIM) Sheet() (*image.NRGBA, error) {
	n := max(1, t.Palettes())
	if t.BPP > 8 {
		n = 1
	}
	cols := min(4, n)
	rows := (n + cols - 1) / cols
	w, h := t.Width(), t.H
	sheet := image.NewNRGBA(image.Rect(0, 0, cols*(w+4), rows*(h+4)))
	for p := 0; p < n; p++ {
		one, err := t.Render(p)
		if err != nil {
			return nil, err
		}
		ox, oy := (p%cols)*(w+4), (p/cols)*(h+4)
		for y := 0; y < h; y++ {
			for x := 0; x < w; x++ {
				sheet.SetNRGBA(ox+x, oy+y, one.NRGBAAt(x, y))
			}
		}
	}
	return sheet, nil
}
