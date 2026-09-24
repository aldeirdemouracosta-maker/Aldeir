# IA-Linux MiniVideo

Sistema Linux dedicado **somente** a criar e editar vídeo com agentes de IA
locais. Separado do Mini IA Local, da Fábrica - App e do Avalia Matemática.
Usa o kernel do IA Linux Minimal, sem alterá-lo, e acrescenta por cima uma
camada de vídeo. O comando `mini-ia-videos` do editor original continua
aceito quando estiver instalado.

> **Estado em 2026-09-24:**
> - Código Python testado de verdade (88 testes, com FFmpeg, RIFE,
>   Real-ESRGAN e Auto-Editor reais), incluindo os especialistas e o
>   gerenciador de modelos.
> - Configuração do ISO validada contra o Buildroot 2026.08 e kernel 6.18.52
>   compilado.
> - **ISO completo ainda não compilado nem inicializado; nada testado na RX
>   580.** Veja `docs/ISO.md`.
> - O código do editor `mini-ia-videos` ainda não está neste repositório
>   (`docs/AUDITORIA.md`).

## Componentes

| Comando | O que faz |
|---|---|
| `minivideo-ui` | interface de pastas (Projetos, Midia, Modelos, Saidas, Jobs, Logs), só teclado, com terminal de prompt |
| `minivideo-agentes` | dispositivos, agentes, `plano`, `executar`, `motores` (matriz CUDA/Vulkan/CPU), `schemas` e `especialistas planejar/editar/reproduzir` |
| `minivideo-modelos` | catálogo, inventário (formato pelo cabeçalho), organizar, verificar (sha256 com cache), recomendar por hardware, instruções manuais e calibração com `llama-bench`; **nenhum download automático** |
| `minivideo-guard` | Hardware Safety Guard somente leitura (RX 580 via sysfs; NVIDIA via `nvidia-smi`) |
| `minivideo-audit` | auditoria da máquina, sem root e sem rede |
| `image/` | camada Buildroot do ISO (defconfig, pacotes, overlay, scripts) |

## Uso no Linux instalado

```bash
cd ia-linux-minivideo
python3 -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
python -m pytest -q

minivideo-ui                                   # interface; F1 mostra as teclas
minivideo-agentes dispositivos                 # CPU, dGPU/APU Vulkan, CUDA
minivideo-agentes agentes                      # quem está pronto e o que falta
minivideo-agentes plano "corte 00:00:15 até 00:00:30, retire os silêncios e melhore para 1080p"
minivideo-agentes executar entrada.mp4 "limpe o áudio e converta para 720p sem IA" -o saida.mp4 --confirmar
minivideo-guard detect

# especialistas: Diretor → Editor → Fiscal → execução → Continuísta
minivideo-agentes especialistas planejar "cena 1: 00:00:00 até 00:00:05 limpe o áudio; cena 2: 00:00:08 até 00:00:12 câmera lenta" --entrada entrada.mp4
minivideo-agentes especialistas editar entrada.mp4 "<pedido>" -o saida.mp4 --confirmar
minivideo-agentes especialistas reproduzir ~/MiniVideo/Jobs/<id>/job.json --confirmar

minivideo-modelos recomendar
minivideo-modelos instrucoes whisper-small
```

## Agentes

Estar no registro não significa estar disponível. Cada agente mostra o
motivo quando falta ferramenta, pesos, driver ou VRAM.

| Agente | Ferramenta | Dispositivo |
|---|---|---|
| Coordenador | llama-server + Qwen3 (GGUF) | Vulkan → CPU |
| Cortador, Áudio, Cenas, Escala, Legendas, Exportador | FFmpeg | CPU (exportador usa VA-API na AMD quando existe) |
| Removedor de silêncios | auto-editor | CPU |
| Transcritor | whisper.cpp | Vulkan → CPU |
| Interpolador | rife-ncnn-vulkan | Vulkan |
| Upscaler IA | realesrgan-ncnn-vulkan | Vulkan |
| Gerador de vídeo, Editor generativo | mini-ia-videos (Wan/LTX/VACE/DFVEdit/EditCtrl) | **CUDA ≥ 12 GB** (futuro) |

Os dispositivos são classificados como `cpu`, `vulkan-dgpu` (RX 580),
`vulkan-apu` (APU AMD), `cuda` (NVIDIA) e `vulkan-sw` (llvmpipe, só para
teste). Etapas em GPU rodam sob o Safety Guard. O plano nunca roda se
alguma etapa estiver indisponível.

## Documentos

- `docs/ESPECIALISTAS.md`: Diretor, Editor, Continuísta e Fiscal: arquitetura, schemas, matriz de motores, exemplo real e pendências.
- `docs/ISO.md`: arquitetura do ISO, como compilar e gravar, testes, defeitos da base, hardware futuro.
- `docs/SUGESTOES_GITHUB.md`: projetos recomendados para RX 580/X79, com links.
- `docs/AUDITORIA.md`: quadro implementado / configurado / testado / pendente.
- `docs/INTEGRACAO_IA_LINUX_MINIMAL.md`: diagnóstico do boot da base.
