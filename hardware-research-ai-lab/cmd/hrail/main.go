// Comando hrail: CLI do Hardware Research AI Lab (Fase 0).
package main

import (
	"os"
)

func main() {
	os.Exit(newApp(os.Stdout, os.Stderr).Run(os.Args[1:]))
}
