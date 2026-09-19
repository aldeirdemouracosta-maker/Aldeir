# Modelos GGUF

Modelos **nunca** ficam dentro da imagem do sistema. Copie arquivos
`.gguf` para `/data/models/` no sistema instalado (partição DATA — ver
`docs/architecture.md`). `ai-core` os descobre automaticamente
(`ai-core/src/model.rs::list_models`), sem precisar reiniciar o daemon.

## Uso

```
IA> models
1) qwen3.5-0.8b-q4.gguf (512 MB)
2) smollm3-3b-q4.gguf (1900 MB)

IA> model select 2
modelo ativo definido: smollm3-3b-q4.gguf

IA> chat
```

## Recomendação por perfil de hardware

`ia-core` calcula o perfil (`TINY`/`LOW`/`MEDIUM`/`LARGE`) a partir da RAM
total detectada (`ai-core/src/hardware.rs::ram_profile`) e sugere um
tamanho de modelo (`MODEL RECOMMEND` / `ia-model recommend`). Ver
`profiles.md` para a tabela completa e exemplos de modelos abertos
conhecidos por faixa.

| Perfil | RAM        | Contexto sugerido | Exemplo de modelo |
|--------|-----------:|-------------------:|--------------------|
| TINY   | < 6 GB     | 1024                | ~0.3-1B Q4 (ex.: Qwen3.5 0.8B) |
| LOW    | 6-12 GB    | 2048                | ~0.8-1.5B Q4 |
| MEDIUM | 12-24 GB   | 4096                | ~1.5-4B Q4 (ex.: SmolLM3 3B, Gemma 3 4B) |
| LARGE  | 24 GB+     | 8192                | ~4-8B Q4 com offload GPU |

A recomendação é um ponto de partida, não um limite — qualquer `.gguf`
compatível com `llama.cpp` funciona, dado RAM/VRAM suficiente.
