package llm

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
)

// Cached grava respostas em disco, indexadas pelo hash do modelo + mensagens + ferramentas.
// Reexecutar a mesma análise não gasta GPU. Só use com temperatura baixa/determinística.
type Cached struct {
	Inner Chatter
	Model string // entra no hash: trocar de modelo invalida o cache
	Dir   string
}

func (c Cached) Chat(ctx context.Context, msgs []Message, tools []ToolDef) (Message, error) {
	key, _ := json.Marshal([]any{c.Model, msgs, tools})
	sum := sha256.Sum256(key)
	path := filepath.Join(c.Dir, hex.EncodeToString(sum[:])+".json")
	if raw, err := os.ReadFile(path); err == nil {
		var m Message
		if json.Unmarshal(raw, &m) == nil {
			return m, nil
		}
	}
	m, err := c.Inner.Chat(ctx, msgs, tools)
	if err != nil {
		return m, err
	}
	if raw, err := json.Marshal(m); err == nil && os.MkdirAll(c.Dir, 0o755) == nil {
		_ = os.WriteFile(path, raw, 0o644)
	}
	return m, nil
}
