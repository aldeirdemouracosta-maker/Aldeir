package tim

import (
	"encoding/binary"
	"testing"
)

func u32(v int) []byte { b := make([]byte, 4); binary.LittleEndian.PutUint32(b, uint32(v)); return b }
func u16(v int) []byte { b := make([]byte, 2); binary.LittleEndian.PutUint16(b, uint16(v)); return b }

// monta um TIM: flags, paleta (cores de 15 bits, em linhas de clutW) e pixels brutos (largura em unidades de 16 bits)
func build(flags int, clut []uint16, clutW int, w16, h int, pix []byte) []byte {
	b := append(u32(0x10), u32(flags)...)
	if flags&8 != 0 {
		ch := len(clut) / clutW
		b = append(b, u32(12+len(clut)*2)...)
		b = append(b, 0, 0, 0, 0, byte(clutW), byte(clutW>>8), byte(ch), byte(ch>>8))
		for _, c := range clut {
			b = append(b, u16(int(c))...)
		}
	}
	b = append(b, u32(12+len(pix))...)
	b = append(b, 0, 0, 0, 0)
	b = append(b, u16(w16)...)
	b = append(b, u16(h)...)
	return append(b, pix...)
}

func TestTIM4bppComDuasPaletas(t *testing.T) {
	// 16 cores por paleta, 2 paletas: cor 1 = vermelho puro (0x001F) na paleta 0 e azul puro (0x7C00) na 1
	clut := make([]uint16, 32)
	clut[1], clut[17] = 0x001F, 0x7C00
	clut[2], clut[18] = 0x03E0, 0x03E0 // verde nas duas
	// imagem 2 unidades de 16 bits = 8 pixels, 1 linha: nibbles baixos primeiro: pixels 1,2,0,1 | 2,2,0,0
	pix := []byte{0x21, 0x10, 0x22, 0x00}
	data := build(0x08, clut, 16, 2, 1, pix)
	im, err := Parse(data)
	if err != nil {
		t.Fatal(err)
	}
	if im.BPP != 4 || im.Width() != 8 || im.H != 1 || im.Palettes() != 2 || im.Total != len(data) {
		t.Fatalf("dados: %+v total=%d", im, len(data))
	}
	p0, err := im.Render(0)
	if err != nil {
		t.Fatal(err)
	}
	// o pixel da esquerda é o nibble baixo: 0x21 -> x=0 usa 1 (vermelho), x=1 usa 2 (verde)
	if c := p0.NRGBAAt(0, 0); c.R != 255 || c.G != 0 || c.B != 0 || c.A != 255 {
		t.Errorf("pixel 0 na paleta 0: %+v", c)
	}
	if c := p0.NRGBAAt(1, 0); c.G != 255 || c.R != 0 {
		t.Errorf("pixel 1 na paleta 0: %+v", c)
	}
	if c := p0.NRGBAAt(2, 0); c.A != 0 { // índice 0 -> cor 0x0000 = transparente
		t.Errorf("pixel 2 deveria ser transparente: %+v", c)
	}
	p1, _ := im.Render(1)
	if c := p1.NRGBAAt(0, 0); c.B != 255 || c.R != 0 { // mesma imagem, outra paleta: azul
		t.Errorf("pixel 0 na paleta 1: %+v", c)
	}
	if c := p1.NRGBAAt(1, 0); c.G != 255 {
		t.Errorf("verde nas duas paletas: %+v", c)
	}
	if _, err := im.Render(2); err == nil {
		t.Error("paleta inexistente deveria dar erro")
	}
	sheet, err := im.Sheet()
	if err != nil || sheet.Bounds().Dx() != 2*(8+4) {
		t.Errorf("folha de paletas: %v %v", sheet.Bounds(), err)
	}
}

func TestTIM8bppE16bpp(t *testing.T) {
	clut := make([]uint16, 256)
	clut[7] = 0x7FFF // branco
	im, err := Parse(build(0x09, clut, 256, 1, 1, []byte{7, 0}))
	if err != nil || im.Width() != 2 || im.Palettes() != 1 {
		t.Fatalf("8bpp: %+v %v", im, err)
	}
	p, _ := im.Render(0)
	if c := p.NRGBAAt(0, 0); c.R != 255 || c.G != 255 || c.B != 255 {
		t.Errorf("8bpp branco: %+v", c)
	}
	// 16 bpp direto, sem paleta: 0x03E0 verde; 0x0000 transparente
	d, err := Parse(build(0x02, nil, 0, 2, 1, []byte{0xE0, 0x03, 0, 0}))
	if err != nil || d.Width() != 2 || d.Palettes() != 0 {
		t.Fatalf("16bpp: %+v %v", d, err)
	}
	r, _ := d.Render(0)
	if c := r.NRGBAAt(0, 0); c.G != 255 || c.R != 0 || c.A != 255 {
		t.Errorf("16bpp verde: %+v", c)
	}
	if c := r.NRGBAAt(1, 0); c.A != 0 {
		t.Errorf("16bpp transparente: %+v", c)
	}
	// 24 bpp: 3 unidades de 16 bits = 2 pixels RGB
	f, err := Parse(build(0x03, nil, 0, 3, 1, []byte{10, 20, 30, 40, 50, 60}))
	if err != nil || f.Width() != 2 {
		t.Fatalf("24bpp: %+v %v", f, err)
	}
	g, _ := f.Render(0)
	if c := g.NRGBAAt(1, 0); c.R != 40 || c.G != 50 || c.B != 60 {
		t.Errorf("24bpp: %+v", c)
	}
}

func TestTIMInvalidos(t *testing.T) {
	good := build(0x08, make([]uint16, 16), 16, 1, 1, []byte{0, 0})
	for name, b := range map[string][]byte{
		"curto":              good[:10],
		"sem magic":          append([]byte{1, 0, 0, 0}, good[4:]...),
		"flags inválidas":    append(append(u32(0x10), u32(0x7)...), good[8:]...),
		"truncado":           good[:len(good)-1],
		"tamanho incoerente": append(append(append([]byte{}, good[:8]...), u32(99)...), good[12:]...),
	} {
		if _, err := Parse(b); err == nil {
			t.Errorf("%s deveria dar erro", name)
		}
	}
	if _, err := Parse(build(0x00, nil, 0, 1, 1, []byte{0, 0})); err == nil {
		t.Error("4 bpp sem paleta não é suportado")
	}
}
