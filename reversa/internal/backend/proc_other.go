//go:build !unix

package backend

import "os/exec"

// Sem grupos de processos: usa o encerramento padrão do processo principal.
func ownGroup(*exec.Cmd) {}
