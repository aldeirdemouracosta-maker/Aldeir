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
