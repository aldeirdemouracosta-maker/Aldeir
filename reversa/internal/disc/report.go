package disc

import (
	"fmt"
	"math"
	"strings"
)

// Hexdump formata bytes em linhas de 16, com o deslocamento e a versão em ASCII.
func Hexdump(b []byte, base int64) string {
	var sb strings.Builder
	for off := 0; off < len(b); off += 16 {
		row := b[off:min(len(b), off+16)]
		fmt.Fprintf(&sb, "%08x: ", base+int64(off))
		var ascii strings.Builder
		for k := 0; k < 16; k++ {
			if k < len(row) {
				fmt.Fprintf(&sb, "%02x ", row[k])
				if row[k] >= 0x20 && row[k] <= 0x7E {
					ascii.WriteByte(row[k])
				} else {
					ascii.WriteByte('.')
				}
			} else {
				sb.WriteString("   ")
			}
			if k%4 == 3 {
				sb.WriteByte(' ')
			}
		}
		fmt.Fprintf(&sb, "|%s|\n", ascii.String())
	}
	return sb.String()
}

// fileAt diz a qual arquivo da raiz do ISO 9660 pertence o setor, ou "" se estiver fora de todos (dados que o
// jogo lê por número de setor).
func (i *Image) fileAt(lba uint32) string {
	ex, err := i.Extents()
	if err != nil {
		return ""
	}
	for _, e := range ex {
		if lba >= e.LBA && lba < e.LBA+(e.Size+userSize-1)/userSize {
			return e.Name
		}
	}
	return ""
}

func (i *Image) where(lba uint32) string {
	if f := i.fileAt(lba); f != "" {
		return "dentro do arquivo " + f
	}
	return "FORA dos arquivos do ISO 9660 (dados lidos por setor)"
}

// FindReport procura em todos os setores e mostra cada ocorrência com o contexto em volta.
func (i *Image) FindReport(what string, window int, test func([]byte) bool, max, ctx int, relative bool) (string, error) {
	ms, err := i.Search(window, test, max)
	if err != nil {
		return "", err
	}
	var b strings.Builder
	fmt.Fprintf(&b, "# Busca por %s\n\n", what)
	fmt.Fprintf(&b, "- Setores de dados varridos: %d (%d MiB de dados do usuário)\n", i.Sectors(), int64(i.Sectors())*userSize>>20)
	fmt.Fprintf(&b, "- Ocorrências: %d%s\n", len(ms), map[bool]string{true: " (limite atingido: pode haver mais)", false: ""}[len(ms) >= max])
	exp := ExpectedByChance(int64(i.Sectors())*userSize, window, relative)
	fmt.Fprintf(&b, "- Esperado só por acaso em dados aleatórios deste tamanho: cerca de %.1f ocorrência(s)\n", exp)
	if exp >= 1 && float64(len(ms)) <= 2*exp {
		b.WriteString("- ATENÇÃO: o número de achados é compatível com pura coincidência. Use uma palavra mais longa antes de confiar nestes resultados.\n")
	}
	for _, m := range ms {
		start := max64(0, m.Abs-int64(ctx))
		blob, err := i.ReadUser(start, window+2*ctx)
		if err != nil {
			return "", err
		}
		fmt.Fprintf(&b, "\n## Setor %d (0x%x), posição 0x%x no setor — byte 0x%x dos dados\n\n", m.LBA, m.LBA, m.Offset, m.Abs)
		fmt.Fprintf(&b, "- Local: %s\n\n```\n%s```\n", i.where(m.LBA), Hexdump(blob, start))
	}
	if len(ms) == 0 {
		b.WriteString("\nNenhuma ocorrência.\n")
	}
	return b.String(), nil
}

func max64(a, b int64) int64 {
	if a > b {
		return a
	}
	return b
}

// SectorReport mostra n bytes a partir do setor lba (dados contíguos, atravessando setores).
func (i *Image) SectorReport(lba uint32, n int) (string, error) {
	if lba >= i.Sectors() {
		return "", fmt.Errorf("setor %d fora da imagem (%d setores)", lba, i.Sectors())
	}
	blob, err := i.ReadUser(int64(lba)*userSize, n)
	if err != nil {
		return "", err
	}
	var b strings.Builder
	fmt.Fprintf(&b, "# Setor %d (0x%x), %d bytes\n\n- Local: %s\n\n```\n%s```\n", lba, lba, len(blob), i.where(lba), Hexdump(blob, int64(lba)*userSize))
	return b.String(), nil
}

// ExpectedByChance estima quantas ocorrências uma busca de window bytes acharia por pura coincidência em totalBytes
// de dados aleatórios: cada byte exigido tem chance 1/256. A busca relativa exige uma diferença a menos (window-1).
// É uma aproximação: dados reais (texto, tabelas, áudio) não são aleatórios.
func ExpectedByChance(totalBytes int64, window int, relative bool) float64 {
	n := window
	if relative {
		n = window - 1
	}
	return float64(totalBytes) * math.Pow(256, -float64(n))
}
