// Package modules embute os manifestos dos laboratórios no binário.
package modules

import "embed"

//go:embed *.json
var FS embed.FS
