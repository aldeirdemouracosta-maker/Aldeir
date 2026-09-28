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

## Etapas de implementação

1. Casca do app em Qt6/QML com a navegação da maquete (Início, Captura, ...)
2. Módulo de Captura: V4L2 + gPhoto2, onion skin, salvar quadros numerados
3. Player de sequência (12/24 fps) e exportação via FFmpeg VAAPI
4. Timeline sobre MLT (importar sequências, áudio, cortes, títulos)
5. IA Local: remoção de fundo, upscale, geração de cenários
6. Orquestrador de modos + perfis de kernel (cgroups/AMDGPU → sched_ext)
7. Imagem ISO do IA Stop-Motion Studio OS com o app como sessão principal
