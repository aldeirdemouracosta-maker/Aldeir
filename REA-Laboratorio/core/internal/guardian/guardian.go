// Package guardian aplica a política de segurança: somente leitura, sem firmware, sem execução de amostras, rede só com autorização.
package guardian

import (
	"fmt"
	"net"
	"net/url"
	"os"
	"path/filepath"
	"strings"
)

// Binários que o REA nunca executa (gravação de disco/firmware/particionamento).
var proibidos = map[string]string{
	"flashrom": "gravação de firmware", "fwupdmgr": "gravação de firmware", "fwupdtool": "gravação de firmware",
	"dd": "escrita bruta em disco", "mkfs": "formatação", "fdisk": "particionamento", "sfdisk": "particionamento",
	"parted": "particionamento", "gdisk": "particionamento", "wipefs": "apagamento", "shred": "apagamento",
	"mount": "montagem fora da política", "rm": "remoção", "mv": "alteração", "cp": "cópia fora do Oficina",
}

type Policy struct {
	WorkDir string // única área onde o REA grava (relatórios, cópias de trabalho)
}

// CheckExec decide se um binário pode ser executado pelo REA.
func (p Policy) CheckExec(bin string) error {
	base := filepath.Base(bin)
	for k, why := range proibidos {
		if base == k || strings.HasPrefix(base, k+".") || strings.HasPrefix(base, "mkfs.") {
			return fmt.Errorf("guardian: %q bloqueado (%s)", base, why)
		}
	}
	return nil
}

// CheckRead exige arquivo regular (nunca dispositivo, pipe ou diretório).
func (p Policy) CheckRead(path string) error {
	fi, err := os.Lstat(path)
	if err != nil {
		return err
	}
	if fi.Mode()&os.ModeSymlink != 0 {
		if fi, err = os.Stat(path); err != nil {
			return err
		}
	}
	if !fi.Mode().IsRegular() {
		return fmt.Errorf("guardian: %q não é arquivo regular (dispositivos e pipes são bloqueados)", path)
	}
	return nil
}

// CheckWrite só permite escrita dentro de WorkDir.
func (p Policy) CheckWrite(path string) error {
	if p.WorkDir == "" {
		return fmt.Errorf("guardian: área de trabalho não definida; escrita negada")
	}
	wd, err := filepath.Abs(p.WorkDir)
	if err != nil {
		return err
	}
	ap, err := filepath.Abs(path)
	if err != nil {
		return err
	}
	rel, err := filepath.Rel(wd, ap)
	if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return fmt.Errorf("guardian: escrita fora da área de trabalho negada: %s", path)
	}
	return nil
}

// CheckNetwork: loopback é livre; qualquer outro destino exige autorização explícita.
func (p Policy) CheckNetwork(rawURL string, autorizado bool) error {
	u, err := url.Parse(rawURL)
	if err != nil || u.Hostname() == "" {
		return fmt.Errorf("guardian: URL inválida")
	}
	if IsLoopback(u.Hostname()) || autorizado {
		return nil
	}
	return fmt.Errorf("guardian: destino remoto %q exige autorização do usuário (dados sairiam do computador)", u.Hostname())
}

func IsLoopback(host string) bool {
	if host == "localhost" {
		return true
	}
	ip := net.ParseIP(host)
	return ip != nil && ip.IsLoopback()
}
