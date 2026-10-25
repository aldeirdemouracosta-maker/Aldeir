// Package binfmt identifica formatos por assinatura (cabeçalho). Nunca executa nada.
package binfmt

import (
	"bytes"
	"encoding/binary"
	"io"
	"os"
)

type Info struct {
	Formato     string `json:"formato"`
	Bits        int    `json:"bits,omitempty"`
	Arquitetura string `json:"arquitetura,omitempty"`
	Detalhe     string `json:"detalhe,omitempty"`
}

const HeaderBytes = 0x8006 // cobre "CD001" do ISO9660 em 0x8001

var peMachines = map[uint16]string{0x14c: "x86", 0x8664: "x86-64", 0xaa64: "ARM64", 0x1c0: "ARM", 0x1c4: "ARM"}
var elfMachines = map[uint16]string{3: "x86", 62: "x86-64", 40: "ARM", 183: "ARM64", 8: "MIPS", 243: "RISC-V", 20: "PowerPC", 21: "PowerPC64"}

func Detect(h []byte) Info {
	switch {
	case len(h) >= 0x40 && h[0] == 'M' && h[1] == 'Z':
		pe := int(binary.LittleEndian.Uint32(h[0x3c:]))
		if pe > 0 && pe+26 <= len(h) && bytes.Equal(h[pe:pe+4], []byte("PE\x00\x00")) {
			i := Info{Formato: "PE", Arquitetura: peMachines[binary.LittleEndian.Uint16(h[pe+4:])]}
			switch binary.LittleEndian.Uint16(h[pe+24:]) {
			case 0x20b:
				i.Bits = 64
			case 0x10b:
				i.Bits = 32
			}
			return i
		}
		return Info{Formato: "MZ/DOS", Detalhe: "cabeçalho PE não encontrado"}
	case bytes.HasPrefix(h, []byte("\x7fELF")) && len(h) >= 20:
		i := Info{Formato: "ELF"}
		if h[4] == 1 {
			i.Bits = 32
		} else if h[4] == 2 {
			i.Bits = 64
		}
		var m uint16
		if h[5] == 2 {
			m = binary.BigEndian.Uint16(h[18:])
		} else {
			m = binary.LittleEndian.Uint16(h[18:])
		}
		i.Arquitetura = elfMachines[m]
		return i
	case bytes.HasPrefix(h, []byte("PK\x03\x04")), bytes.HasPrefix(h, []byte("PK\x05\x06")):
		return Info{Formato: "ZIP"}
	case bytes.HasPrefix(h, []byte("\x1f\x8b")):
		return Info{Formato: "GZIP"}
	case bytes.HasPrefix(h, []byte("7z\xbc\xaf\x27\x1c")):
		return Info{Formato: "7-Zip"}
	case bytes.HasPrefix(h, []byte("\xfd7zXZ\x00")):
		return Info{Formato: "XZ"}
	case bytes.HasPrefix(h, []byte("BZh")):
		return Info{Formato: "BZIP2"}
	case bytes.HasPrefix(h, []byte("Rar!")):
		return Info{Formato: "RAR"}
	case bytes.HasPrefix(h, []byte("%PDF")):
		return Info{Formato: "PDF"}
	case bytes.HasPrefix(h, []byte("GGUF")):
		return Info{Formato: "GGUF", Detalhe: "modelo de IA"}
	case bytes.HasPrefix(h, []byte("hsqs")):
		return Info{Formato: "SquashFS"}
	case bytes.HasPrefix(h, []byte("\x89PNG")):
		return Info{Formato: "PNG"}
	case bytes.HasPrefix(h, []byte("\xd0\xcf\x11\xe0")):
		return Info{Formato: "OLE2", Detalhe: "documento Office antigo"}
	case bytes.HasPrefix(h, []byte("\xca\xfe\xba\xbe")):
		return Info{Formato: "Java class ou Mach-O universal"}
	case bytes.HasPrefix(h, []byte("\xcf\xfa\xed\xfe")), bytes.HasPrefix(h, []byte("\xce\xfa\xed\xfe")):
		return Info{Formato: "Mach-O"}
	case len(h) >= 0x8006 && bytes.Equal(h[0x8001:0x8006], []byte("CD001")):
		return Info{Formato: "ISO9660"}
	case len(h) >= 262 && bytes.Equal(h[257:262], []byte("ustar")):
		return Info{Formato: "TAR"}
	}
	return Info{Formato: "desconhecido"}
}

// DetectFile lê só o cabeçalho do arquivo.
func DetectFile(path string) (Info, error) {
	f, err := os.Open(path)
	if err != nil {
		return Info{}, err
	}
	defer f.Close()
	buf := make([]byte, HeaderBytes)
	n, err := io.ReadFull(f, buf)
	if err != nil && err != io.ErrUnexpectedEOF && err != io.EOF {
		return Info{}, err
	}
	return Detect(buf[:n]), nil
}
