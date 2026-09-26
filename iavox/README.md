# IAVOX — Leitor de PDF em Áudio

Módulo do IAVOX que transforma qualquer PDF em áudio, com audiodescrição
de imagens e resumo por IA. Feito para funcionar em conjunto com o DOSVOX
e leitores de tela em geral.

## O que faz

- **Extrai texto de qualquer PDF**, mesmo escaneado (usa OCR em português
  automaticamente quando o PDF não tem camada de texto).
- **Três modos de densidade de leitura**: curto, médio, detalhado — o texto
  é resumido/reescrito por IA local (Ollama) conforme o nível escolhido.
- **Audiodescrição automática de imagens**: cada figura, gráfico ou foto do
  PDF é descrita em português por um modelo de visão local (Ollama + llava).
- **4 motores de voz (TTS)**, para você escolher o equilíbrio entre
  qualidade e facilidade de instalação:
  1. `offline` — espeak-ng, sempre disponível, voz mais robótica.
  2. `piper` — Piper TTS, voz offline natural (exige baixar um modelo `.onnx`).
  3. `kokoro` — Kokoro, voz neural leve (~80-300MB) com voz nativa em
     português brasileiro, muito mais natural que o espeak-ng.
  4. `ia` — Coqui TTS, voz neural gerada por IA local (`pip install TTS`,
     mais pesado — puxa PyTorch).
  5. `automatico` — usa o melhor motor disponível na sua máquina
     (ia > kokoro > piper > offline).
- **Salva o resultado como arquivo de áudio (.wav)** e/ou lê em voz alta na hora.

Tudo roda localmente — nenhuma etapa depende de nuvem ou API paga. Os
recursos de IA (resumo e audiodescrição) usam o [Ollama](https://ollama.com)
local; se o Ollama não estiver rodando, o IAVOX cai graciosamente para o
texto completo (sem resumir) e uma descrição genérica de imagem, sem travar.

## Instalação

O IAVOX (código Python) roda igual em **Windows e Linux** — a diferença está
só em como você instala as ferramentas externas (OCR, voz, poppler) em cada
sistema.

### Linux (Debian/Ubuntu)

```bash
# dependências Python
pip install -r requirements.txt

# OCR em português
sudo apt-get install tesseract-ocr tesseract-ocr-por poppler-utils

# motor de voz offline básico (sempre recomendado ter instalado)
sudo apt-get install espeak-ng
```

### Windows

```powershell
# dependências Python (use o mesmo requirements.txt)
pip install -r requirements.txt
```

Depois, instale as ferramentas externas manualmente (não têm `apt` no Windows):

1. **Tesseract OCR (com idioma português)**
   Baixe o instalador em https://github.com/UB-Mannheim/tesseract/wiki e
   marque o idioma "Portuguese" na instalação. Anote o caminho do
   `tesseract.exe` (padrão: `C:\Program Files\Tesseract-OCR\tesseract.exe`).

2. **Poppler para Windows** (necessário só para o fallback de OCR de PDFs
   escaneados). Baixe em https://github.com/oschwartz10612/poppler-windows/releases,
   descompacte e anote a pasta `Library\bin`.

3. **espeak-ng para Windows**
   Baixe o instalador `.msi` em https://github.com/espeak-ng/espeak-ng/releases
   e instale normalmente — ele se registra no PATH do sistema. **Importante**:
   feche e reabra o IAVOX (ou o Prompt de Comando) depois de instalar — o
   Windows só atualiza o PATH em janelas novas, então uma janela que já
   estava aberta antes da instalação não vai encontrar o programa.

Depois de instalar, se o Tesseract/Poppler/espeak-ng não ficarem no PATH do
Windows (ou você preferir não reiniciar a janela), informe os caminhos
direto na hora de rodar:

```powershell
python -m iavox_pdf_audio.cli.main documento.pdf `
    --tesseract-cmd "C:\Program Files\Tesseract-OCR\tesseract.exe" `
    --poppler-path "C:\poppler-24.02.0\Library\bin" `
    --espeak-cmd "C:\Program Files\eSpeak NG\espeak-ng.exe" `
    --modo resumo --densidade curto --tts offline
```

Na interface gráfica, os mesmos caminhos podem ser informados pelo botão
"⚙ Configurações avançadas" na barra lateral — não precisa usar o terminal.

Se o espeak-ng, Tesseract e Poppler estiverem todos no PATH do Windows
(instalador padrão costuma cuidar disso), não precisa passar `--tesseract-cmd`
nem `--poppler-path` — funciona igual ao Linux.

### Opcional: voz mais natural (Piper) — Windows e Linux

1. Baixe o binário do [Piper](https://github.com/rhasspy/piper/releases)
   (existe build para Windows e para Linux).
2. Baixe um modelo de voz em português, ex: `pt_BR-faber-medium.onnx`.
3. Linux: coloque o modelo em `~/.iavox/piper_voices/`, ou aponte o caminho
   com `--piper-model caminho\para\modelo.onnx` (funciona nos dois sistemas).

### Opcional: voz neural leve com português nativo (Kokoro) — Windows e Linux

```bash
pip install kokoro-onnx soundfile
```

Depois, baixe os 2 arquivos de modelo (não vêm no zip do IAVOX por serem
grandes, ~140MB juntos) em
https://github.com/thewh1teagle/kokoro-onnx/releases e coloque em
`~/.iavox/kokoro/` (Linux) ou `C:\Users\SeuUsuario\.iavox\kokoro\` (Windows):

- `kokoro-v1.0.int8.onnx` (versão leve, ~88MB — recomendada) ou
  `kokoro-v1.0.onnx` (versão completa, ~310MB, um pouco melhor qualidade)
- `voices-v1.0.bin`

Depois de baixados, o motor `kokoro` já funciona sem mais configuração — a
voz padrão é `pf_dora` (feminina, português brasileiro).

**Nota sobre desempenho**: o Kokoro é bem mais pesado de processar que o
espeak-ng ou o Piper — ele usa o ONNX Runtime, que aproveita automaticamente
os núcleos de CPU disponíveis na sua máquina. Em computadores com poucos
núcleos ou mais antigos, a síntese pode demorar bem mais que os outros
motores; teste com um PDF curto primeiro para ter uma ideia do tempo na sua
máquina.

### Opcional: voz por IA (Coqui TTS)

```bash
pip install TTS
```

### Opcional: resumo e audiodescrição por IA (Ollama)

```bash
# instale o Ollama: https://ollama.com/download
ollama pull llama3.2:3b   # para resumo de texto
ollama pull llava:7b      # para audiodescrição de imagens
```

## Interface gráfica (desktop)

Além da CLI, o IAVOX tem uma interface gráfica desktop (Linux e Windows),
com painel lateral de documentos recentes, opções de leitura e um botão de
play para ouvir o resultado.

```bash
pip install -r requirements.txt -r requirements-gui.txt
```

- **Linux**: `./run-gui-linux.sh` (ou `python3 run_gui.py`)
- **Windows**: dê duplo clique em `run-gui-windows.bat` (ou `python run_gui.py`)

A reprodução do áudio tenta tocar dentro da própria janela; se as bibliotecas
de multimídia do sistema não estiverem disponíveis, o IAVOX abre o áudio
gerado no tocador padrão do seu sistema operacional automaticamente.

## Uso por linha de comando (CLI)

### Modo interativo (recomendado com leitor de tela)

```bash
python -m iavox_pdf_audio.cli.main
```

O IAVOX vai perguntar, passo a passo: o arquivo, o modo de leitura, a
densidade (se resumo), se deve descrever imagens, o motor de voz e se deve
salvar o áudio.

### Modo direto (linha de comando)

```bash
python -m iavox_pdf_audio.cli.main documento.pdf \
    --modo resumo --densidade curto \
    --imagens sim --tts automatico \
    --saida ./saida_audio --ler-agora
```

## Testes

```bash
python tests/make_sample_pdf.py   # gera um PDF de exemplo
python -m pytest tests/ -v
```

## Estrutura

```
iavox_pdf_audio/
  core/
    extractor.py          # extração de texto + imagens do PDF (com OCR)
    summarizer.py          # resumo por IA, 3 níveis de densidade
    image_description.py   # audiodescrição de imagens por IA (visão)
    reader.py               # orquestrador: junta tudo em um roteiro + áudio
  tts/
    base.py                 # interface comum dos motores de voz
    espeak_engine.py        # motor offline básico
    piper_engine.py         # motor offline natural
    ai_engine.py             # motor por IA (Coqui TTS)
    selector.py              # escolhe o motor (as 4 opções)
  cli/
    main.py                  # interface de linha de comando acessível
gui/
  main_window.py              # janela principal (layout do mockup)
  worker.py                    # thread de fundo (não trava a interface)
  audio_player.py              # player com fallback pro tocador do sistema
  styles.py                     # visual (branco/azul, cantos arredondados)
run_gui.py                       # ponto de entrada da interface gráfica
run-gui-linux.sh / run-gui-windows.bat   # scripts de execução
```
