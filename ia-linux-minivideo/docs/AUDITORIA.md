# Auditoria — IA-Linux MiniVideo (2026-09-24)

Legenda de estado: **implementado** = código presente · **configurado** =
dependências/pesos instalados · **testado** = executado de verdade (não
dry-run, não inspeção) · **pendente** = não existe ou não verificável.

## 1. O que foi encontrado nos repositórios acessíveis

| Local | Conteúdo real | Relação com este projeto |
|---|---|---|
| `Aldeir` — branch `main` | Projeto Android **Lumivox** (WebView, APK) + zip | Nenhuma. Preservado intacto. |
| `Aldeir` — `claude/friendly-rubin-xg4c53` | **Fábrica - App** (orquestrador, microagentes, mockups) | Deve ficar separado. Não usado. |
| `Aldeir` — `claude/dreamy-curie-j1yy53` | **IA Linux Minimal** (Buildroot, kernel 6.18.52, ai-core Rust, GRUB) | Base futura, só referência. Não alterado. |
| `ChamaMula-ROM` | Queimador de CD/DVD em Python | Nenhuma. |
| `lumivox-android` | Lumivox Android | Nenhuma. |

**O código do editor "Mini - IA Vídeos" (`mini-ia-videos`) não está em
nenhum repositório acessível nesta sessão.** Não há README, ROADMAP,
ORCHESTRATOR, `pyproject.toml`, CLI, adaptadores nem testes dele. Busca
feita em todos os branches (`git ls-tree -r`) e em todo o histórico
(`git log --all`, 77 commits). Por isso nenhum dos recursos listados no
ROADMAP pôde ser inspecionado nem executado.

## 2. Quadro de recursos do editor (ROADMAP)

Todos marcados **pendente — código ausente**. Nada aqui foi executado; os
comandos documentados (`mini-ia-videos hardware`, `doctor`, `engines`,
`generative-doctor`, `vision-doctor`, `orchestrator-doctor`, `plan`,
`run`, `chunk-plan`, `continuity-check`, `cost-estimate`) **não puderam
ser conferidos com `--help`** porque o executável não existe aqui.

| Recurso | Implementado | Configurado | Testado | Depende de |
|---|---|---|---|---|
| CLI modular, detecção de hardware, governador de VRAM | ? | — | não | código do editor |
| Catálogo de engines, roteador, planejador | ? | — | não | código do editor |
| Projetos, jobs, logs JSONL | ? | — | não | código do editor |
| FFmpeg (corte, exportação, áudio) | ? | não | não | `ffmpeg`/`ffprobe` |
| PySceneDetect → CSV de cenas | ? | não | não | `scenedetect` |
| Auto-Editor (silêncios) | ? | não | não | `auto-editor` |
| whisper.cpp → SRT → JSON | ? | não | não | binário + `ggml-*.bin` |
| RIFE NCNN Vulkan (interpolação/slow motion) | ? | não | não | binário + modelos `.param/.bin` + Vulkan |
| Real-ESRGAN NCNN Vulkan (upscale) | ? | não | não | binário + modelos + Vulkan |
| Wan2.1 VACE 1.3B / LTX-Video 2B Distilled | ? | não | não | CUDA ≥12 GB + pesos |
| DFVEdit (Wan2.1 1.3B) / EditCtrl 1.3B (experimental) | ? | não | não | CUDA ≥12 GB + pesos |
| Pré-validação CUDA/VRAM, recuperação de OOM (49/33/17/9 frames) | ? | — | não | CUDA |
| Vídeo longo em chunks, overlap, recomposição, áudio | ? | — | não | código + FFmpeg |
| Continuidade (básica/perceptual/semântica), frame-âncora | ? | não | não | extras `[vision]` |
| Regeneração seletiva, limites de custo | ? | — | não | código |
| Orquestrador Qwen (auto/qwen/rules) | ? | não | não | servidor OpenAI-compatible local |

`?` = sem como afirmar; o ROADMAP diz que existe, mas o código não foi entregue a esta sessão.

## 3. O que foi feito e testado nesta sessão

| Item | Implementado | Testado | Como |
|---|---|---|---|
| `minivideo-audit` (auditoria somente leitura) | sim | sim, neste container + testes com `/proc` e `/sys` simulados do Xeon E5-2630L v2 / RX 580 2048SP | `pytest`, execução real |
| Hardware Safety Guard — coleta amdgpu (sysfs) | sim | só com sysfs **simulado** no layout da Polaris | `pytest` |
| Guard — política (limites + histerese + amostras para rebaixar) | sim | sim | `pytest` |
| Guard — ações (reduzir/pausar/retomar/encerrar) em processo real | sim | sim (SIGSTOP/SIGCONT/SIGTERM num processo Python real) | `pytest` |
| Guard — log JSONL por job | sim | sim | `pytest` |
| Guard — backend NVIDIA (`nvidia-smi`) | sim | só o parser, com saída de exemplo | `pytest` |
| **Guard na RX 580 real** | — | **não** — este container não tem GPU | pendente: rodar na máquina alvo |

## 4. Diagnóstico deste ambiente (não é a máquina alvo)

Saída real de `minivideo-audit` no container da sessão:

- CPU: Xeon virtual 2,10 GHz, 4 threads, **com AVX2/AVX-512** (a máquina
  alvo **não** tem AVX2, então resultados de CPU daqui não transferem).
- RAM 15,7 GiB; disco ~30 GiB livres.
- GPU: nenhuma (`/sys/class/drm` inexistente). Vulkan: ausente. CUDA: ausente.
- FFmpeg, PySceneDetect, Auto-Editor, whisper.cpp, RIFE, Real-ESRGAN,
  llama-server, `mini-ia-videos`: **ausentes**.
- Pesos: nenhum.

## 5. Matriz de recursos por hardware (o que é esperado, a validar)

| Função | Xeon E5-2630L v2 + RX 580 (atual) | NVIDIA 16 GB (alvo) | NVIDIA 12 GB | Só CPU |
|---|---|---|---|---|
| Corte, concatenação, exportação (FFmpeg) | sim | sim | sim | sim |
| Cenas / silêncios | sim (CPU) | sim | sim | sim |
| Transcrição whisper.cpp | sim, modelos `small`/`base` na CPU; **compilar sem AVX2** | sim (CUDA) | sim | lento |
| Interpolação RIFE / upscale Real-ESRGAN | sim via Vulkan (leve; VRAM 8 GB) | sim | sim | não (sem Vulkan) |
| Wan VACE / LTX / DFVEdit / EditCtrl | **não** (sem CUDA) | alvo principal | a testar (offload, menos frames) | não |
| Orquestrador Qwen3 0.6B/1.7B | CPU ou llama.cpp Vulkan | sim | sim | CPU |
| Safety Guard | backend amdgpu | backend NVIDIA (não validado) | idem | sem sensores de GPU |

GPUs mistas: cada GPU vira um dispositivo independente no Guard (`amdgpu:cardN`,
`nvidia:N`). Nenhum modelo é dividido entre GPUs diferentes.

## 6. Reproduzir esta auditoria

```bash
cd ia-linux-minivideo
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
minivideo-audit --models-dir ~/modelos -o auditoria.json   # somente leitura
minivideo-guard detect                                       # sensores da GPU
python -m pytest -q
```
