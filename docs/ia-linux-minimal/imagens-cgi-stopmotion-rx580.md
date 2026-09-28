# Imagens CGI e estilo stop motion na RX 580 8 GB (Linux, Xeon X79)

Guia prático para o IA Linux Minimal. Os tempos citados são estimativas para
comparação entre opções — meça sempre na sua máquina com o mesmo prompt,
resolução e número de passos.

## Restrição mais importante do hardware

A RX 580 é Polaris (gfx803). As versões atuais do ROCm/PyTorch **não suportam
mais** essa geração. Por isso, a base do sistema deve ser **Vulkan (RADV)**, e
não ROCm. A maior parte do ecossistema "padrão" (ComfyUI, Automatic1111, Forge)
depende de PyTorch e fica em "experimental" nesta placa.

O Xeon X79 sem AVX2 não é problema quando o cálculo pesado fica na GPU; só
evite caminhos que caiam para CPU.

## Classificação

### Leve — funciona bem e rápido

| Ferramenta | Uso | Por quê |
|---|---|---|
| `stable-diffusion.cpp` (backend Vulkan) + **SD 1.5** | texto→imagem, img2img, inpainting | Mesma família do llama.cpp (ggml), roda via RADV, 512×512 cabe folgado em 8 GB |
| `stable-diffusion.cpp` + **SD-Turbo / LCM** | rascunhos rápidos | 1–4 passos em vez de 20–30: ideal para testar composição |
| `realesrgan-ncnn-vulkan` | upscale 2×/4× | Vulkan puro, excelente em Polaris |
| `realcugan-ncnn-vulkan` / `waifu2x-ncnn-vulkan` | upscale de arte/ilustração | idem |
| `ffmpeg` | montar frames em vídeo | CPU, leve |

### Ideal — melhor custo/qualidade para CGI e stop motion

| Componente | Função |
|---|---|
| `stable-diffusion.cpp` Vulkan + **SD 1.5 fine-tune estilizado** (modelos 3D/cartoon) | base de geração |
| **LoRA de claymation / stop motion / clay / puppet** | dá o visual de massinha, textura artesanal, miniatura |
| **ControlNet** (pose, depth, canny) para SD 1.5 | mantém personagem e pose consistentes entre quadros |
| **Blender (Eevee ou Workbench)** | monta cena 3D simples → exporta depth/pose → IA estiliza (CGI "de verdade" + acabamento IA) |
| **SDXL em GGUF quantizado** (Q8/Q4) no sd.cpp | mais qualidade em 768–1024 px, porém bem mais lento |

Observação sobre o Blender: o Cycles em GPU via HIP exige RDNA, então na RX 580
use **Eevee** (OpenGL) para renders de apoio; Cycles fica em CPU.

### Experimental — possível, mas lento ou instável

| Opção | Situação |
|---|---|
| **FLUX.1 schnell/dev em GGUF Q4** no sd.cpp | cabe em 8 GB com quantização, qualidade alta, mas minutos por imagem |
| **SD 3.5 Medium** GGUF | idem, tempo alto |
| **Wan 2.1 1.3B** (vídeo) no sd.cpp | clipes muito curtos em baixa resolução; bom apenas para teste |
| **ComfyUI com ROCm patchado para gfx803** (builds da comunidade/Docker) | funciona em alguns casos, frágil e preso a versões antigas |
| **AnimateDiff** | depende de PyTorch → mesma limitação acima |
| `rife-ncnn-vulkan` (interpolação de quadros) | funciona bem, mas para stop motion normalmente **não** se quer suavizar o movimento |

### Não recomendado nesta placa

- FLUX / SD 3.5 Large em FP16 (não cabe em 8 GB)
- HunyuanVideo, Wan 14B e outros modelos grandes de vídeo
- Treinar modelos base (LoRA pequena é possível, mas lenta; prefira LoRAs prontas)
- Qualquer fluxo que dependa de CUDA ou de ROCm moderno

## Fluxo recomendado para "stop motion" com IA

A estética stop motion joga a favor do hardware: ela *espera* 8–12 quadros por
segundo e pequenas imperfeições entre quadros.

```
1. Personagem de referência
   SD 1.5 + LoRA claymation, seed fixa → escolher o melhor resultado

2. Poses/keyframes
   ControlNet (openpose ou depth) com a mesma seed, LoRA e prompt
   (ou poses montadas no Blender com bonecos simples)

3. Correções
   inpainting só nas partes erradas (mãos, rosto, objetos)

4. Acabamento
   realesrgan-ncnn-vulkan 2×

5. Montagem
   ffmpeg -framerate 12 -i frame_%03d.png -c:v libx264 -pix_fmt yuv420p saida.mp4
```

Para CGI estilizado o fluxo é o mesmo, trocando a LoRA por uma de estilo 3D/
render e usando o Blender para gerar a composição (depth map) antes da IA.

## Onde o "Modo IA" do kernel entra

Nada muda no modelo — o ganho é de sistema:

- `power_dpm_force_performance_level=profile_peak` durante a geração
- prioridade/afinidade para o processo do sd.cpp (sched_ext `scx_lavd` ou
  `taskset`/`chrt` como primeira versão)
- desktop mínimo para liberar VRAM
- variáveis RADV a testar: `RADV_PERFTEST=nogttspill`
- evitar swap: usar `--vae-tiling` do sd.cpp em resoluções maiores

## Ordem sugerida de testes

1. Compilar `stable-diffusion.cpp` com `-DSD_VULKAN=ON` e medir SD 1.5 512×512
2. Adicionar LoRA claymation e ControlNet
3. Instalar `realesrgan-ncnn-vulkan`
4. Montar uma sequência de 12–24 quadros com ffmpeg
5. Só então testar SDXL GGUF e FLUX Q4

## Links

- stable-diffusion.cpp: https://github.com/leejet/stable-diffusion.cpp
- Real-ESRGAN ncnn Vulkan: https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan
- Real-CUGAN ncnn Vulkan: https://github.com/nihui/realcugan-ncnn-vulkan
- waifu2x ncnn Vulkan: https://github.com/nihui/waifu2x-ncnn-vulkan
- RIFE ncnn Vulkan: https://github.com/nihui/rife-ncnn-vulkan
- Blender: https://www.blender.org
- LoRAs e modelos estilizados: buscar "claymation", "stop motion", "clay" em https://civitai.com e https://huggingface.co
