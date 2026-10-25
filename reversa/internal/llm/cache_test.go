package llm

import (
	"context"
	"testing"
)

type counter struct{ n int }

func (c *counter) Chat(context.Context, []Message, []ToolDef) (Message, error) {
	c.n++
	return Message{Role: "assistant", Content: "ok"}, nil
}

func TestCacheEvitaSegundaChamada(t *testing.T) {
	in := &counter{}
	c := Cached{Inner: in, Model: "m", Dir: t.TempDir()}
	msgs := []Message{{Role: "user", Content: "oi"}}
	for i := 0; i < 3; i++ {
		if _, err := c.Chat(context.Background(), msgs, nil); err != nil {
			t.Fatal(err)
		}
	}
	if in.n != 1 {
		t.Fatalf("modelo chamado %d vezes, esperado 1", in.n)
	}
	c.Model = "outro"
	_, _ = c.Chat(context.Background(), msgs, nil)
	if in.n != 2 {
		t.Fatal("trocar de modelo deveria invalidar o cache")
	}
}
