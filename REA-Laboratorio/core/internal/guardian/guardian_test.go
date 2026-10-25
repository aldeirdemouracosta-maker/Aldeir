package guardian

import (
	"os"
	"path/filepath"
	"testing"
)

func TestCheckExecBloqueiaEscritaEFirmware(t *testing.T) {
	p := Policy{}
	for _, b := range []string{"flashrom", "/usr/sbin/dd", "mkfs.ext4", "fdisk", "wipefs", "rm", "fwupdmgr"} {
		if p.CheckExec(b) == nil {
			t.Errorf("%s deveria ser bloqueado", b)
		}
	}
	for _, b := range []string{"file", "readelf", "strings", "/usr/bin/objdump"} {
		if err := p.CheckExec(b); err != nil {
			t.Errorf("%s deveria ser permitido: %v", b, err)
		}
	}
}

func TestCheckReadSoArquivoRegular(t *testing.T) {
	d := t.TempDir()
	f := filepath.Join(d, "a")
	os.WriteFile(f, []byte("x"), 0o644)
	p := Policy{}
	if err := p.CheckRead(f); err != nil {
		t.Fatal(err)
	}
	if p.CheckRead(d) == nil {
		t.Error("diretório deveria ser negado")
	}
	if p.CheckRead("/dev/null") == nil {
		t.Error("dispositivo deveria ser negado")
	}
}

func TestCheckWriteSomenteNaAreaDeTrabalho(t *testing.T) {
	d := t.TempDir()
	p := Policy{WorkDir: d}
	if err := p.CheckWrite(filepath.Join(d, "sub", "r.json")); err != nil {
		t.Fatal(err)
	}
	for _, bad := range []string{filepath.Join(d, "..", "fora"), "/etc/passwd", "/dev/sda"} {
		if p.CheckWrite(bad) == nil {
			t.Errorf("%s deveria ser negado", bad)
		}
	}
	if (Policy{}).CheckWrite(filepath.Join(d, "x")) == nil {
		t.Error("sem WorkDir toda escrita deve ser negada")
	}
}

func TestCheckNetwork(t *testing.T) {
	p := Policy{}
	for _, u := range []string{"http://127.0.0.1:11434", "http://localhost:1234", "http://[::1]:8080"} {
		if err := p.CheckNetwork(u, false); err != nil {
			t.Errorf("%s loopback deveria passar: %v", u, err)
		}
	}
	if p.CheckNetwork("http://192.168.0.10:1234", false) == nil {
		t.Error("remoto sem autorização deve ser negado")
	}
	if err := p.CheckNetwork("http://192.168.0.10:1234", true); err != nil {
		t.Error("remoto autorizado deve passar")
	}
}
