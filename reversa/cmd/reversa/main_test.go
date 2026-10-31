package main

import (
	"bytes"
	"strings"
	"testing"
)

func TestBuildInfoNuncaVazio(t *testing.T) {
	if got := buildInfo(); strings.TrimSpace(got) == "" {
		t.Fatal("buildInfo vazio")
	}
}

func TestParseHexBytes(t *testing.T) {
	for _, in := range []string{"46 72 65", "467265", "0x46 0x72 0x65", "46,72,65"} {
		got, err := parseHexBytes(in)
		if err != nil || !bytes.Equal(got, []byte("Fre")) {
			t.Errorf("%q: %q %v", in, got, err)
		}
	}
	for _, bad := range []string{"", "zz", "4"} {
		if _, err := parseHexBytes(bad); err == nil {
			t.Errorf("%q deveria dar erro", bad)
		}
	}
}

func TestParsePatch(t *testing.T) {
	p, err := parsePatch("0x14064:46 72 65", false)
	if err != nil || p.Abs != 0x14064 || string(p.Data) != "Fre" {
		t.Errorf("deslocamento: %+v %v", p, err)
	}
	p, err = parsePatch("40+0x64:4672", false)
	if err != nil || p.Abs != 40*2048+0x64 || string(p.Data) != "Fr" {
		t.Errorf("setor+posição: %+v %v", p, err)
	}
	p, err = parsePatch("100:Frxya", true)
	if err != nil || p.Abs != 100 || string(p.Data) != "Frxya" {
		t.Errorf("ascii: %+v %v", p, err)
	}
	for _, bad := range []string{"semdoispontos", "xyz:46", "40+2048:46", "-1:46", "10:", "10:zz"} {
		if _, err := parsePatch(bad, false); err == nil {
			t.Errorf("%q deveria dar erro", bad)
		}
	}
	if _, err := parsePatch("10:", true); err == nil {
		t.Error("texto vazio deveria dar erro")
	}
}

func TestParseLoc(t *testing.T) {
	for in, want := range map[string]int64{"0x14064": 0x14064, "100": 100, "40+0x64": 40*2048 + 0x64, "36310+0x548": 36310*2048 + 0x548} {
		if got, err := parseLoc(in); err != nil || got != want {
			t.Errorf("%q: %d %v (esperado %d)", in, got, err, want)
		}
	}
	for _, bad := range []string{"", "x", "-5", "40+2048", "a+b"} {
		if _, err := parseLoc(bad); err == nil {
			t.Errorf("%q deveria dar erro", bad)
		}
	}
}
