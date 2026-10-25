// Package evidence guarda cada fato produzido por uma ferramenta, com seus limites.
package evidence

import (
	"crypto/sha256"
	"encoding/hex"
	"sync"
	"time"
)

// Confidence segue a classificação do REA: o que foi lido, o que foi calculado e o que foi suposto.
type Confidence string

const (
	Observed Confidence = "observed" // lido direto do alvo ou da ferramenta (cabeçalho, bytes)
	Derived  Confidence = "derived"  // calculado de forma determinística a partir de observações
	Inferred Confidence = "inferred" // suposição, por exemplo texto de um modelo; nunca é fato
	Unknown  Confidence = "unknown"  // o que a análise não consegue resolver; nunca vira "ausente"
)

// Record é uma afirmação rastreável: qual ferramenta, com quais argumentos, o que retornou
// e o que o resultado NÃO garante.
type Record struct {
	ID         int        `json:"id"`
	Tool       string     `json:"tool"`
	Args       string     `json:"args"`
	Output     string     `json:"output"`
	Digest     string     `json:"digest"`            // sha256 do Output
	Subject    string     `json:"subject,omitempty"` // sha256 do alvo analisado
	Confidence Confidence `json:"confidence"`
	Limits     string     `json:"limits,omitempty"`
	At         time.Time  `json:"at"`
}

// Log é um registro append-only, seguro para uso concorrente.
type Log struct {
	Subject string // sha256 do alvo; carimbado em todo registro novo

	mu      sync.Mutex
	records []Record
}

// Add registra uma observação. Use AddAs para fatos derivados ou inferidos.
func (l *Log) Add(tool, args, output, limits string) Record {
	return l.AddAs(Observed, tool, args, output, limits)
}

func (l *Log) AddAs(c Confidence, tool, args, output, limits string) Record {
	sum := sha256.Sum256([]byte(output))
	l.mu.Lock()
	defer l.mu.Unlock()
	r := Record{ID: len(l.records) + 1, Tool: tool, Args: args, Output: output, Digest: hex.EncodeToString(sum[:]),
		Subject: l.Subject, Confidence: c, Limits: limits, At: time.Now().UTC()}
	l.records = append(l.records, r)
	return r
}

func (l *Log) All() []Record {
	l.mu.Lock()
	defer l.mu.Unlock()
	return append([]Record(nil), l.records...)
}
