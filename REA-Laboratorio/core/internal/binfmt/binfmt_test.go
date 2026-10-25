package binfmt

import "testing"

func TestPE64(t *testing.T) {
	b := make([]byte, 0x200)
	copy(b, "MZ")
	b[0x3c] = 0x80
	copy(b[0x80:], "PE\x00\x00")
	b[0x84], b[0x85] = 0x64, 0x86
	b[0x98], b[0x99] = 0x0b, 0x02
	i := Detect(b)
	if i.Formato != "PE" || i.Bits != 64 || i.Arquitetura != "x86-64" {
		t.Fatalf("%+v", i)
	}
}

func TestELFLEeBE(t *testing.T) {
	b := make([]byte, 64)
	copy(b, "\x7fELF")
	b[4], b[5], b[18] = 2, 1, 62
	if i := Detect(b); i.Formato != "ELF" || i.Bits != 64 || i.Arquitetura != "x86-64" {
		t.Fatalf("LE %+v", i)
	}
	b[5], b[18], b[19] = 2, 0, 8
	if i := Detect(b); i.Arquitetura != "MIPS" {
		t.Fatalf("BE %+v", i)
	}
}

func TestOutrosFormatos(t *testing.T) {
	iso := make([]byte, 0x8006)
	copy(iso[0x8001:], "CD001")
	casos := map[string][]byte{"ZIP": []byte("PK\x03\x04xx"), "PDF": []byte("%PDF-1.7"), "GGUF": []byte("GGUF\x03"),
		"GZIP": {0x1f, 0x8b, 8}, "ISO9660": iso, "SquashFS": []byte("hsqs")}
	for esperado, b := range casos {
		if i := Detect(b); i.Formato != esperado {
			t.Errorf("%s: obtive %s", esperado, i.Formato)
		}
	}
	if Detect([]byte{1, 2, 3}).Formato != "desconhecido" {
		t.Error("deveria ser desconhecido")
	}
	if Detect(nil).Formato != "desconhecido" {
		t.Error("vazio deveria ser desconhecido")
	}
}
