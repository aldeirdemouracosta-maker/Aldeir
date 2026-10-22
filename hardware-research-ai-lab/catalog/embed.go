// Package catalog embute os catálogos de ferramentas e fontes.
package catalog

import _ "embed"

//go:embed tools.json
var ToolsJSON []byte

//go:embed sources.json
var SourcesJSON []byte
