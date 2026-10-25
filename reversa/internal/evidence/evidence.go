// Package evidence guarda cada fato produzido por uma ferramenta, com seus limites.
package evidence

import (
	"sync"
	"time"
)

// Record é uma afirmação rastreável: qual ferramenta, com quais argumentos, o que retornou
// e o que o resultado NÃO garante.
type Record struct {
	ID     int       `json:"id"`
	Tool   string    `json:"tool"`
	Args   string    `json:"args"`
	Output string    `json:"output"`
	Limits string    `json:"limits,omitempty"`
	At     time.Time `json:"at"`
}

// Log é um registro append-only, seguro para uso concorrente.
type Log struct {
	mu      sync.Mutex
	records []Record
}

func (l *Log) Add(tool, args, output, limits string) Record {
	l.mu.Lock()
	defer l.mu.Unlock()
	r := Record{ID: len(l.records) + 1, Tool: tool, Args: args, Output: output, Limits: limits, At: time.Now().UTC()}
	l.records = append(l.records, r)
	return r
}

func (l *Log) All() []Record {
	l.mu.Lock()
	defer l.mu.Unlock()
	return append([]Record(nil), l.records...)
}
