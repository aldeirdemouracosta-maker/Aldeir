# 🎬 FrameLTX Studio

Gerador **100% local** de vídeos curtos (TikTok, Shorts, Reels) com IA open-source:

- **FramePack** (FP8): vídeos longos (até 60 s) com pouca VRAM;
- **LTX-2** (destilado FP8): mais qualidade e **áudio sincronizado**;
- **Modo combinado**: o FramePack gera o movimento longo e o LTX refina cada trecho
  usando frames-chave (primeiro/último frame), adicionando áudio.

Você não precisa mexer em nós do ComfyUI: o app conversa com o ComfyUI pela API
(`localhost:8188`) e entrega um MP4 9:16 pronto para postar.

![fluxo](https://img.shields.io/badge/Gradio-UI-ff2d6f) ![local](https://img.shields.io/badge/100%25-local-7b5cff)

---

## Sumário

1. [Requisitos](#1-requisitos)
2. [Instalação do ComfyUI e dos modelos](#2-instalação-do-comfyui-e-dos-modelos)
3. [Instalação do FrameLTX Studio](#3-instalação-do-frameltx-studio)
4. [Como usar](#4-como-usar)
5. [Modos de geração](#5-modos-de-geração)
6. [Qualidade automática por VRAM](#6-qualidade-automática-por-vram)
7. [Presets e estilos](#7-presets-e-estilos)
8. [Workflows JSON](#8-workflows-json)
9. [Configuração](#9-configuração)
10. [Solução de problemas](#10-solução-de-problemas)
11. [Arquitetura (para desenvolvedores)](#11-arquitetura-para-desenvolvedores)

---

## 1. Requisitos

| Item | Mínimo | Recomendado |
|---|---|---|
| GPU | NVIDIA 6 GB VRAM | NVIDIA 8–12 GB VRAM |
| RAM | 16 GB | 32 GB (o FramePack descarrega modelos para a RAM) |
| Disco | ~60 GB livres para modelos | SSD |
| Sistema | Windows 10/11 ou Linux | — |
| Python | 3.10+ | 3.11 |

> O app foi ajustado com prioridade para **placas de 8 GB** (perfil "Médio").

## 2. Instalação do ComfyUI e dos modelos

1. Instale o [ComfyUI](https://github.com/comfyanonymous/ComfyUI) (no Windows, a versão
   *portable* é a mais simples). Use uma versão **recente** — os nós do LTX-2 são nativos.
2. Instale o pacote de nós do FramePack pelo **ComfyUI-Manager**:
   `ComfyUI-FramePackWrapper` (kijai).
3. Baixe os modelos e coloque nas pastas do ComfyUI:

| Arquivo | Pasta (`ComfyUI/models/…`) | Uso |
|---|---|---|
| `FramePackI2V_HY_fp8_e4m3fn.safetensors` | `diffusion_models/` | FramePack |
| `clip_l.safetensors` | `text_encoders/` | FramePack |
| `llava_llama3_fp8_scaled.safetensors` | `text_encoders/` | FramePack |
| `sigclip_vision_patch14_384.safetensors` | `clip_vision/` | FramePack |
| `hunyuan_video_vae_bf16.safetensors` | `vae/` | FramePack |
| `ltx-2-19b-distilled-fp8.safetensors` | `checkpoints/` | LTX-2 (vídeo + áudio) |
| `gemma_3_12B_it_fp8_scaled.safetensors` | `text_encoders/` | LTX-2 |

> Os nomes exatos variam conforme a versão baixada. **Se o seu arquivo tiver outro
> nome, basta ajustá-lo no `config.json`** (seção `models`) — não é preciso editar os workflows.

4. Inicie o ComfyUI com previews ativados para ver os frames sendo gerados:

```bash
# Linux
python main.py --preview-method auto
# Windows portable: edite run_nvidia_gpu.bat e acrescente  --preview-method auto
```

Para GPUs de 6–8 GB, `--lowvram` também ajuda.

## 3. Instalação do FrameLTX Studio

**Windows**

```bat
install.bat
run.bat
```

**Linux**

```bash
./install.sh
./run.sh
```

Os scripts criam um ambiente virtual (`.venv`), instalam o `requirements.txt` e criam
o `config.json` a partir de `config.example.json`. A interface abre em
<http://127.0.0.1:7860>.

Instalação manual (qualquer sistema):

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

### Testar sem GPU (modo demonstração)

```bash
python app.py --demo
```

Gera vídeos sintéticos com ffmpeg (zoom na imagem + tom de áudio). Serve para conhecer
a interface, a fila e o histórico em qualquer computador.

### Opções de linha de comando

| Opção | Descrição |
|---|---|
| `--comfy URL` | Endereço do ComfyUI (padrão `http://127.0.0.1:8188`) |
| `--port N` | Porta da interface (padrão 7860) |
| `--host 0.0.0.0` | Permite abrir a interface pelo celular na mesma rede |
| `--profile baixo\|medio\|alto\|ultra` | Força um perfil de qualidade |
| `--demo` | Modo demonstração |
| `--debug` | Logs detalhados |

## 4. Como usar

1. Escolha o **Modo** (FramePack, LTX ou Vídeo Longo + Qualidade).
2. Envie a **imagem inicial** (e, opcionalmente, a final no FramePack/Combinado).
3. Escolha um **Preset** e um **Estilo** — ou deixe "Livre".
4. Descreva o movimento no **prompt** (inglês costuma funcionar melhor).
5. Escolha a **duração** e clique em **🎬 Gerar Vídeo**.

Durante a geração você acompanha a **barra de progresso**, a **prévia em tempo real**
(frames parciais do ComfyUI) e o **log**. Ao final aparece o vídeo e o botão de
**download (MP4 9:16, 1080×1920)**.

Outras abas:

- **🕘 Histórico** — todas as gerações, com miniatura, prompt, seed e avisos. Dá para
  rever, baixar e apagar.
- **📋 Fila** — você pode clicar em "Gerar" várias vezes: os pedidos entram numa fila e
  são processados um por vez (a GPU só aguenta um vídeo por vez). A interface nunca trava.
- **🖥️ Sistema** — GPU detectada, perfil escolhido, status do ComfyUI e validação dos
  workflows (aponta nós que faltam instalar).

Os vídeos ficam salvos automaticamente em:

```
outputs/AAAA-MM-DD/<modo>/HHMMSS_<prompt>.mp4   (+ .jpg miniatura, + .json metadados)
```

## 5. Modos de geração

| Modo | Entrada | Duração | Áudio | Quando usar |
|---|---|---|---|---|
| **FramePack** | 1 imagem (ou início + fim) | 5–60 s | não | Vídeos longos, pouca VRAM |
| **LTX** | texto **ou** imagem | 5–60 s* | **sim** | Qualidade, pessoa falando, cenas curtas |
| **Vídeo Longo + Qualidade** | 1 imagem (ou início + fim) | 5–60 s | **sim** | Melhor resultado final |

\* O LTX gera clipes de até 4–10 s (depende do perfil). Durações maiores são
**encadeadas automaticamente**: o último frame de um clipe vira o primeiro do próximo.

**Pipeline do modo combinado:**

```
imagem ──► FramePack (vídeo longo, sem áudio)
              │
              ├─► extrai frames-chave a cada N segundos (N = limite do LTX no perfil)
              │
              └─► para cada trecho: LTX-2 primeiro/último frame (+ áudio)
                       │  (se um trecho falhar, usa o trecho do FramePack)
                       ▼
                 concatena ─► exporta MP4 9:16 1080×1920
```

## 6. Qualidade automática por VRAM

A VRAM é lida do próprio ComfyUI (`/system_stats`), com fallback para `nvidia-smi`
e PyTorch.

| Perfil | VRAM | FramePack | LTX | Clipe LTX máx. |
|---|---|---|---|---|
| Baixo | 6–7 GB | 384×672 | 384×672 | 4 s |
| **Médio** | 8–11 GB | 480×832 | 448×800 | 5 s |
| Alto | 12–15 GB | 544×960 | 544×960 | 8 s |
| Ultra | 16 GB+ | 640×1136 | 704×1248 | 10 s |

**Proteção contra falta de VRAM:** se o ComfyUI retornar *CUDA out of memory*, o app
libera a memória, mostra *"⚠️ VRAM insuficiente, reduzindo qualidade: Médio → Baixo"*
e tenta de novo automaticamente — até um perfil de emergência (320×576).

Todo vídeo é exportado em 1080×1920 (upscale Lanczos) — desmarque em *Avançado* para
manter a resolução nativa.

## 7. Presets e estilos

Presets incluídos: **Pessoa falando**, **Produto girando**, **Cena cinematográfica**,
**Stop-motion style** (reamostra para 12 fps), **Dança**, **Paisagem timelapse** e **Livre**.

Estilos: Realista, Cinematográfico, Comercial, Anime, Stop-motion, Vintage.

O prompt final é: `seu prompt + descrição do preset + descrição do estilo`. Se o prompt
ficar vazio, o preset usa um prompt padrão.

**Criar seus presets:** copie `presets_custom.example.json` para `presets_custom.json`
e edite. Campos: `name`, `prompt_suffix`, `default_prompt`, `negative`,
`recommended_mode`, `recommended_style`, `post_fps`, `motion_guidance`.

## 8. Workflows JSON

Ficam em `workflows/`, no formato **API** do ComfyUI:

| Arquivo | Uso |
|---|---|
| `framepack_i2v.json` | FramePack imagem→vídeo (imagem final opcional) |
| `ltx2_t2v.json` | LTX-2 texto→vídeo com áudio |
| `ltx2_i2v.json` | LTX-2 imagem→vídeo com áudio |
| `ltx2_first_last.json` | LTX-2 primeiro/último frame com áudio (modo combinado) |

Valores dinâmicos usam placeholders como `"{{prompt}}"`, `"{{seed}}"`, `"{{width}}"`.
Se um placeholder recebe "vazio" (ex.: sem imagem final), o nó correspondente é
removido automaticamente junto com suas ligações.

**Trocar um workflow pelo seu:** monte/teste no ComfyUI, exporte com
*Workflow → Export (API)*, substitua os valores pelos placeholders (lista em `_about`
de cada arquivo) e salve com o mesmo nome. A aba **Sistema** valida se todos os nós
existem no seu ComfyUI.

> ⚠️ Os nós do FramePack (wrapper do kijai) e do LTX-2 mudam com frequência. Se o
> ComfyUI recusar um workflow, a mensagem aparece na interface com o nó e o campo com
> problema; normalmente basta reexportar o workflow de exemplo do próprio pacote de nós
> e recolocar os placeholders.

## 9. Configuração

`config.json` (criado pelo instalador; todas as chaves são opcionais):

```json
{
  "comfy_url": "http://127.0.0.1:8188",
  "output_dir": "outputs",
  "force_profile": "",
  "export_width": 1080,
  "export_height": 1920,
  "models": { "ltx_checkpoint": "meu-ltx.safetensors" }
}
```

Variáveis de ambiente equivalentes: `COMFYUI_URL`, `FRAMELTX_OUTPUT_DIR`,
`FRAMELTX_WORKFLOWS_DIR`, `FRAMELTX_PROFILE`, `FRAMELTX_DEMO`, `FRAMELTX_HOST`,
`FRAMELTX_PORT`.

## 10. Solução de problemas

| Mensagem | O que fazer |
|---|---|
| *Não foi possível conectar ao ComfyUI* | Abra o ComfyUI e confira a URL/porta. |
| *Workflow rejeitado… value not in list* | Um modelo não foi encontrado: confira a pasta e o nome no `config.json`. |
| *nós ausentes no ComfyUI* (aba Sistema) | Instale o pacote de nós pelo ComfyUI-Manager e atualize o ComfyUI. |
| *VRAM insuficiente, reduzindo qualidade…* | Normal — o app se ajusta sozinho. Feche jogos/navegadores com aceleração para ganhar VRAM. |
| *VRAM insuficiente mesmo na qualidade mínima* | Reduza a duração, inicie o ComfyUI com `--lowvram`. |
| Sem prévia em tempo real | Inicie o ComfyUI com `--preview-method auto`. |
| Vídeo sem áudio | Áudio vem do LTX-2. O modo FramePack puro não gera áudio. |

Logs detalhados: `python app.py --debug`.

## 11. Arquitetura (para desenvolvedores)

```
frameltx_studio/
├── app.py                  # entrada (CLI) → frameltx.ui.launch
├── frameltx/
│   ├── config.py           # padrões + config.json + variáveis de ambiente
│   ├── vram.py             # detecção de GPU, perfis de qualidade, redução em OOM
│   ├── presets.py          # presets/estilos e montagem dos prompts
│   ├── workflows.py        # carrega JSON, preenche placeholders, remove nós opcionais, valida
│   ├── comfy_client.py     # API ComfyUI: upload, /prompt, WebSocket (progresso + previews), download
│   ├── backends.py         # ComfyBackend (real) e DemoBackend (ffmpeg)
│   ├── pipelines.py        # modos FramePack / LTX / Combinado + fallback de VRAM
│   ├── jobs.py             # fila de gerações (thread única de GPU)
│   ├── storage.py          # pastas organizadas + history.json
│   ├── video_utils.py      # ffmpeg: frames-chave, concatenação, export 9:16
│   └── ui.py               # interface Gradio
├── workflows/              # 4 workflows ComfyUI (formato API)
└── tests/                  # pytest (roda sem GPU)
```

Fluxo: **UI** → `JobManager.submit` → thread de trabalho → `run_generation` →
modo (`pipelines.py`) → `Backend.generate` → `ComfyClient.run` (WebSocket com progresso)
→ `video_utils` (concatena/exporta) → `Storage` (salva + histórico). A UI só consulta
o estado do job a cada 0,5 s.

**Como estender:**

- *Novo modelo/modo*: crie o workflow em `workflows/`, registre em
  `WORKFLOW_FILES` e escreva uma função `run_<modo>` em `pipelines.py` adicionando-a
  em `RUNNERS` e `MODES`.
- *Novo preset*: adicione em `PRESETS` (`presets.py`) ou em `presets_custom.json`.
- *Novo perfil de VRAM*: adicione um `QualityProfile` em `PROFILES` (`vram.py`).

Testes:

```bash
pip install -r requirements.txt
python -m pytest -q
```

Os testes cobrem os workflows (placeholders, remoção de nós opcionais), perfis de
VRAM, presets, histórico, fila, redução automática de qualidade em OOM e os três modos
de ponta a ponta usando o backend de demonstração.
