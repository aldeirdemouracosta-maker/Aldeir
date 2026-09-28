# IA Stop-Motion Studio OS — arquitetura híbrida (kernel + sistema)

Sistema para criar vídeos stop motion quadro a quadro com bonecos de pano,
montagem e edição estilo Clipchamp, com IA local. Hardware alvo: Xeon X79 +
RX 580 8 GB. Base: Ubuntu 24.04 LTS (ou IA Linux Minimal).

## Princípio

O kernel **não** executa a IA nem a edição. Ele cuida do caminho crítico de
dados e de tempo real (câmera → memória → GPU → encoder) e prioriza a tarefa
certa em cada modo. Aplicativo, IA e edição rodam em espaço de usuário.

```
┌─────────────────────────── ESPAÇO DE USUÁRIO ───────────────────────────┐
│  IA Stop-Motion Studio OS — app principal (Qt6/QML)                     │
│  Início · Captura · Editor de Cenas · Timeline · Biblioteca · IA Local  │
│  Personagens · Cenários · Renderização · Terminal                       │
│                                                                         │
│  Captura        Edição/Timeline     IA Local              Render        │
│  gPhoto2/V4L2   MLT framework       stable-diffusion.cpp  FFmpeg        │
│  onion skin     (motor do Kdenlive  rembg / realesrgan    VAAPI H.264/  │
│  GStreamer      e Shotcut)          whisper.cpp, piper    HEVC na RX580 │
│                                     llama.cpp (roteiro)                 │
│                        ▲ Orquestrador de modos (daemon)                 │
├────────────────────────┼───────────────── KERNEL ───────────────────────┤
│  V4L2/UVC + DMA-BUF (zero cópia)   io_uring (gravação de quadros)       │
│  sched_ext: perfis Captura / Edição / IA / Render                       │
│  AMDGPU/DRM: perfis de energia, VCE (encode), Vulkan compute            │
│  eBPF: telemetria (latência de captura, fila da GPU, disco)             │
└─────────────────────────────────────────────────────────────────────────┘
```

## Modos do sistema (o "híbrido")

| Modo | Kernel prioriza | GPU faz |
|---|---|---|
| **Captura** | thread da câmera e preview com baixa latência; nada de travar no live view | preview + onion skin (shader) |
| **Edição** | interface fluida, decodificação da timeline | composição/preview (OpenGL/Vulkan) |
| **IA** | processo de inferência, afinidade de núcleos, sem swap | Vulkan compute (SD, upscale, remoção de fundo) |
| **Render** | throughput, disco sequencial | encoder de hardware (VCE via VAAPI) |

Primeira versão sem kernel customizado: `chrt`/`taskset`/cgroups + sysfs do
AMDGPU. Segunda versão: scheduler `sched_ext` próprio (`scx_studio`) trocado
automaticamente pelo orquestrador.

## Módulos e o que reaproveitar (não construir do zero)

| Módulo | Reaproveitar | Licença |
|---|---|---|
| Captura por câmera DSLR/mirrorless | libgphoto2 (base do Entangle) | LGPL |
| Captura por webcam/celular | V4L2 + GStreamer; celular via DroidCam/IP | LGPL |
| Onion skin, loop de preview, contagem de quadros | referência: Stopmotion (linuxstopmotion), qStopMotion | GPL |
| Timeline / edição estilo Clipchamp | **MLT framework** (motor do Kdenlive e Shotcut) | LGPL |
| Render e exportação | FFmpeg com VAAPI (h264_vaapi / hevc_vaapi) | LGPL/GPL |
| Remover fundo / chroma key de bonecos | rembg (ONNX), filtro chroma do MLT | MIT/LGPL |
| Cenários e personagens com IA | stable-diffusion.cpp (Vulkan) + LoRA de feltro/pano/claymation | MIT |
| Upscale 4K | realesrgan-ncnn-vulkan | BSD |
| Legendas automáticas | whisper.cpp (Vulkan) | MIT |
| Narração | Piper TTS | MIT |
| Roteiro → lista de cenas/planos | llama.cpp + Qwen pequeno | MIT |
| Rigging e cenários 3D | Blender (exporta para a Biblioteca) | GPL |

Consequência de licença: se incorporar código do Stopmotion ou do Blender, o
app inteiro fica GPL. Usando só bibliotecas LGPL/MIT, a licença fica livre.

## Fluxo de um projeto

```
Roteiro (llama.cpp) → cenas/planos/tomadas
  → Captura (quadro a quadro, onion skin, 12 ou 24 fps)
  → Limpeza (remover suportes/fios com inpainting, estabilizar)
  → Editor de Cenas (fundo por IA, chroma, cenários)
  → Timeline MLT (cortes, trilhas, áudio, títulos, transições)
  → Legendas (whisper.cpp) + narração (Piper)
  → Render VAAPI → MP4 1080p/4K
```

## Decisões de escopo

A interface segue a maquete original: barra superior, menu lateral, dock
inferior, painel Sistema e Projeto Recente, com todas as seções (Editor de
Cenas, Rigging e Cenários, Terminal, Lixeira…).

**Entra no MVP:** travar câmera contra flicker, onion skin, grade, alternar ao
vivo/último, gravação segura de cada quadro, dope sheet (hold por quadro),
importar fotos, exportação com formatos prontos (16:9, 9:16, 1:1, 4K) usando o
encoder da RX 580 e a telemetria de VRAM/temperatura.

**Fica para depois:** roteiro com LLM.

**Fora do escopo:** IA em Ring 0, módulo de kernel próprio / eBPF no AMDGPU,
geração de vídeo por IA, interpolação de quadros (destrói o visual stop motion),
4K como padrão (padrão 1080p) e distribuição Linux feita do zero (base Ubuntu 24.04).

## Etapas de implementação

1. ✅ App em Qt6/QML com a navegação da maquete (Início, Captura, ...)
2. ✅ Captura: webcam, travar câmera, onion skin, grade, quadros salvos com segurança, dope sheet (gPhoto2 para DSLR ainda falta)
3. ✅ Player (8–30 fps) e exportação FFmpeg VAAPI com fallback x264
4. ✅ Timeline sobre MLT: cenas, vídeos, fotos, títulos, áudio, dissolver, dividir/aparar, render VAAPI/x264 e exportação .mlt para Shotcut/Kdenlive
5. ✅ Dope sheet com trilha de áudio, sincronia labial (Rhubarb) e remoção de flicker
6. ✅ IA Local: limpar suportes (placa limpa, preenchimento, LaMa), fundo por IA (IS-Net) e chroma key, upscale Real-ESRGAN (Vulkan); captura DSLR via gPhoto2
7. ✅ Modos do sistema: helper root via polkit (perfis AMDGPU COMPUTE/VIDEO, governor, prioridades) com troca automática pelo app, e escalonador sched_ext próprio `scx_studio` (classes UI/worker por modo)
8. Imagem ISO do IA Stop-Motion Studio OS com o app como sessão principal
