// Package archive lista arquivos ZIP com limites anti-bomba. Não extrai nada.
package archive

import (
	"archive/zip"
	"strings"
)

type Limits struct {
	MaxEntries      int
	MaxUncompressed uint64
	MaxRatio        float64
}

var DefaultLimits = Limits{MaxEntries: 10000, MaxUncompressed: 1 << 30, MaxRatio: 200}

type Entry struct {
	Nome       string   `json:"nome"`
	Tamanho    uint64   `json:"tamanho"`
	Comprimido uint64   `json:"comprimido"`
	Alertas    []string `json:"alertas,omitempty"`
}

type Result struct {
	Entradas []Entry  `json:"entradas"`
	Total    uint64   `json:"total_descomprimido"`
	Truncado bool     `json:"truncado"`
	Alertas  []string `json:"alertas,omitempty"`
}

// SuspectPath detecta path traversal e caminhos absolutos.
func SuspectPath(name string) bool {
	n := strings.ReplaceAll(name, "\\", "/")
	if strings.HasPrefix(n, "/") || (len(n) > 1 && n[1] == ':') {
		return true
	}
	for _, p := range strings.Split(n, "/") {
		if p == ".." {
			return true
		}
	}
	return false
}

func ListZip(path string, lim Limits) (*Result, error) {
	zr, err := zip.OpenReader(path)
	if err != nil {
		return nil, err
	}
	defer zr.Close()
	return List(&zr.Reader, lim), nil
}

// List analisa os metadados de um zip.Reader já aberto.
func List(zr *zip.Reader, lim Limits) *Result {
	res := &Result{}
	for i, f := range zr.File {
		if i >= lim.MaxEntries {
			res.Truncado = true
			res.Alertas = append(res.Alertas, "número de entradas acima do limite; listagem truncada")
			break
		}
		e := Entry{Nome: f.Name, Tamanho: f.UncompressedSize64, Comprimido: f.CompressedSize64}
		if SuspectPath(f.Name) {
			e.Alertas = append(e.Alertas, "caminho suspeito (traversal/absoluto)")
		}
		if f.Mode()&0o170000 == 0o120000 {
			e.Alertas = append(e.Alertas, "link simbólico")
		}
		if f.Flags&1 != 0 {
			e.Alertas = append(e.Alertas, "criptografado")
		}
		if f.CompressedSize64 > 0 && float64(f.UncompressedSize64)/float64(f.CompressedSize64) > lim.MaxRatio {
			e.Alertas = append(e.Alertas, "razão de compressão extrema")
		}
		res.Total += f.UncompressedSize64
		res.Entradas = append(res.Entradas, e)
	}
	if res.Total > lim.MaxUncompressed {
		res.Alertas = append(res.Alertas, "tamanho descomprimido total acima do limite: possível zip-bomb; NÃO extrair")
	}
	for _, e := range res.Entradas {
		if len(e.Alertas) > 0 {
			res.Alertas = append(res.Alertas, e.Nome+": "+strings.Join(e.Alertas, ", "))
		}
	}
	return res
}
