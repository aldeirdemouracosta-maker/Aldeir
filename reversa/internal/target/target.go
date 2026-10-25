// Package target carrega o alvo de análise do PS1: um PS-X EXE solto ou o executável de boot de um disco.
package target

import (
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"reversa/internal/disc"
)

// maxExe evita ler um arquivo gigante por engano como se fosse um executável.
const maxExe = 64 << 20

// LoadPS1 devolve os bytes do PS-X EXE e uma descrição da origem.
func LoadPS1(path string) ([]byte, string, error) {
	switch strings.ToLower(filepath.Ext(path)) {
	case ".cue", ".bin", ".iso":
		img, err := disc.Open(path)
		if err != nil {
			return nil, "", err
		}
		defer img.Close()
		name, exe, err := img.BootExe()
		if err != nil {
			return nil, "", err
		}
		return exe, fmt.Sprintf("disco %q, boot %s", img.VolumeID, name), nil
	}
	st, err := os.Stat(path)
	if err != nil {
		return nil, "", err
	}
	if st.Size() > maxExe {
		return nil, "", fmt.Errorf("%s tem %d bytes, acima do limite de %d", path, st.Size(), maxExe)
	}
	b, err := os.ReadFile(path)
	return b, "arquivo " + filepath.Base(path), err
}
