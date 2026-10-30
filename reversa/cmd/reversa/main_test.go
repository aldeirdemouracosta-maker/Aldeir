package main

import (
	"strings"
	"testing"
)

func TestBuildInfoNuncaVazio(t *testing.T) {
	if got := buildInfo(); strings.TrimSpace(got) == "" {
		t.Fatal("buildInfo vazio")
	}
}
