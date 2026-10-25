// Package orchestrator coordena vários agentes locais sem estourar a GPU.
package orchestrator

import (
	"context"
	"sync"
)

// Result guarda o resultado da tarefa i, preservando a ordem da entrada.
type Result[R any] struct {
	Val R
	Err error
}

// Map aplica fn a cada item com no máximo workers execuções simultâneas.
// Um modelo local atende poucas requisições em paralelo: workers deve ser igual a OLLAMA_NUM_PARALLEL.
// Cancelar ctx interrompe as tarefas que ainda não começaram.
func Map[T, R any](ctx context.Context, items []T, workers int, fn func(context.Context, T) (R, error)) []Result[R] {
	if workers < 1 {
		workers = 1
	}
	out := make([]Result[R], len(items))
	sem := make(chan struct{}, workers)
	var wg sync.WaitGroup
	for i, it := range items {
		select {
		case sem <- struct{}{}:
		case <-ctx.Done():
			for j := i; j < len(items); j++ {
				out[j].Err = ctx.Err()
			}
			wg.Wait()
			return out
		}
		wg.Add(1)
		go func() {
			defer wg.Done()
			defer func() { <-sem }()
			out[i].Val, out[i].Err = fn(ctx, it)
		}()
	}
	wg.Wait()
	return out
}
