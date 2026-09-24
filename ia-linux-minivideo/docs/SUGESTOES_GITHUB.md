# Sugestões de recursos (GitHub e afins) para RX 580 + X79

Pesquisa de 2026-09-24. Legenda: **no ISO** = empacotado e com teste
registrado · **próximo** = recomendado, ainda não integrado ·
**experimental** = funciona com ressalvas · **evitar** = custo maior que o ganho.

## Já integrados

| Projeto | Papel | Estado | Observação |
|---|---|---|---|
| [nihui/rife-ncnn-vulkan](https://github.com/nihui/rife-ncnn-vulkan) | interpolação / câmera lenta | **no ISO** | release 20221029; rodou aqui (llvmpipe) e em CPU IvyBridge emulada |
| [xinntao/Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) (ncnn-vulkan) | upscale | **no ISO** | o zip vem sem bit de execução e exige `models` no caminho (ambos tratados) |
| [WyattBlue/auto-editor](https://github.com/WyattBlue/auto-editor) | remoção de silêncios | **no ISO** | binário 31.6.0 com FFmpeg próprio; glibc ≥ 2.38; sem AVX2 (testado) |
| [ggml-org/whisper.cpp](https://github.com/ggml-org/whisper.cpp) | transcrição/legendas | **no ISO** (pacote próprio, não compilado ainda) | Vulkan no Linux com RADV é muito mais rápido que na CPU ([guia RX 580](https://github.com/aivisionslab-studios/rx580-local-ai-guide)) |
| [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) | coordenador (Qwen3) | **no ISO** (pacote do Buildroot) | em cross-compilação o ggml usa só o `-march` do toolchain; por isso a variante corei7-avx (Sandy Bridge) |
| FFmpeg VA-API (Mesa radeonsi) | exportação por hardware | **no ISO** | Polaris codifica H.264/HEVC por VA-API, **sem B-frames** (`-bf 0`), [referência](https://gist.github.com/Brainiarc7/95c9338a737aa36d9bb2931bed379219) |
| mpv (`--vo=drm`) | prévia sem ambiente gráfico | **no ISO** | — |

## Próximos (maior retorno para esta máquina)

1. **[mostlygeek/llama-swap](https://github.com/mostlygeek/llama-swap)**: troca
   modelos sob demanda atrás de uma única API OpenAI. Na RX 580 com 8 GB,
   é o que permite vários agentes LLM/visão sem manter todos na VRAM ao
   mesmo tempo. Binário Go estático, uma configuração. Serve também para
   stable-diffusion.cpp.
2. **[OHF-Voice/piper1-gpl](https://github.com/OHF-Voice/piper1-gpl)**
   (Piper TTS): narração em **pt_BR** (voz `pt_BR-faber-medium`), em CPU e
   rápido. Seria o agente "narrador". Licença GPL-3.0.
3. **Redução de ruído com RNNoise**: o FFmpeg tem o filtro `arnndn`, e o
   Buildroot tem `rnnoise`. Tende a ser melhor que o `afftdn` atual em voz;
   exige um arquivo de modelo.
4. **[Syllo/nvtop](https://github.com/Syllo/nvtop)**: monitor de GPU com
   suporte a amdgpu (kernel ≥ 5.14), agora e para NVIDIA no futuro. Útil ao
   lado do Safety Guard (apenas leitura).
5. **Modelos NCNN extras da mesma família**: Real-CUGAN, waifu2x e IFRNet
   (nihui/*-ncnn-vulkan). Mesmo formato de pacote dos atuais.
6. **Variante `BR2_x86_ivybridge`** para quem tem só Xeon E5 **v2** (o seu
   caso): liga F16C/RDRAND. O ISO padrão fica em sandybridge para rodar
   também no E5 v1.

## Experimentais

- **[leejet/stable-diffusion.cpp](https://github.com/leejet/stable-diffusion.cpp)**:
  gera imagem e até vídeo Wan2.1/2.2 em C++ com Vulkan e GGUF. Na RX 580 é
  o único caminho de geração sem CUDA, mas o próprio projeto registra
  desempenho fraco do Wan em Vulkan e regressões recentes de memória
  ([issue #1976](https://github.com/leejet/stable-diffusion.cpp/issues/1976)).
  Candidato a agente "quadro-chave" (imagem SD1.5/SDXL-Turbo quantizada),
  não a gerador de vídeo nesta GPU.

## Evitar nesta máquina

- **ROCm/PyTorch na RX 580 (gfx803)**: a AMD parou de compilar gfx803 depois
  do ROCm 6.0, e o ROCm 7 recusa a placa. Só há builds comunitários e
  imagens Docker ([woodrex83/ROCm-For-RX580](https://github.com/woodrex83/ROCm-For-RX580),
  [tópico gfx803](https://github.com/topics/gfx803)). Frágil demais para uma
  imagem mínima. Vulkan (RADV) é o caminho.
- **Binários pré-compilados com AVX2** (llama.cpp, whisper.cpp, wheels):
  SIGILL no X79 ([discussão no llama.cpp](https://github.com/ggml-org/llama.cpp/discussions/7723)).
  Compilar com a variante de CPU correta.
- **Alterar clocks ou voltagens da RX 580** (LACT, `pp_od_clk_voltage`): o
  Safety Guard é deliberadamente somente leitura.

## Para o alvo CUDA (16 GB)

- Módulos de kernel abertos da NVIDIA ([open-gpu-kernel-modules](https://github.com/NVIDIA/open-gpu-kernel-modules))
  como pacote próprio, mais o espaço de usuário do driver. Wan2.1 VACE 1.3B,
  LTX-Video e DFVEdit/EditCtrl via PyTorch com CUDA, isolados num ambiente
  Python na partição de dados. Tudo isso exige teste físico antes de ser
  anunciado.
