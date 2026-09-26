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

## Interface gráfica (desktop) — Suíte IAVOX

A interface segue a **especificação oficial do tema** (azul profundo, azul
elétrico, foco amarelo, robô assistente) e reúne os módulos na tela inicial:

| Tecla | Módulo | O que faz |
|---|---|---|
| **F1** | LeitorVox | Lê PDF (com resumo e audiodescrição), imagem ou a tela (OCR) |
| **F2** | FalaVox | Responder com voz: grava, transcreve com Whisper local e pede confirmação |
| **F3** | OlhaVox | Descreve imagens (abrir, colar com Ctrl+V ou capturar a tela) |
| **F4** | EstudaVox | Resumo e perguntas de estudo de um PDF, TXT ou texto colado |
| **F5** | Modo Atividade | Lê cada pergunta, o aluno responde com a voz, confirma e continua |

Barra de navegação: **Início**, **Atividade** (Mini Caderno), **Ajuda** e **Ajustes**.
A barra de status mostra, com bolinha verde ou vermelha, o que está funcionando
na máquina: DOSVOX (`C:\winvox`), microfone, OCR (Tesseract) e modelos locais (Ollama).
Pressione Enter em um item para ouvir o detalhe.

**Teclado** (tudo funciona sem mouse; o foco aparece em amarelo):

- `F1`…`F5` abrem os módulos; `Esc` cancela ou volta ao início
- `Ctrl+Shift+M` começa e termina a gravação da resposta
- `Enter` confirma a resposta · `Espaço` grava de novo
- `Ctrl+R` repete a última mensagem falada · `Ctrl+.` cala a voz

**Mini Caderno**: tudo o que o aluno faz nos módulos fica registrado em ordem
cronológica (texto leve, até 30 itens na tela), para o professor acompanhar.
Botões: Ler Caderno, Salvar TXT, Abrir no EDIVOX (editor do DOSVOX) e Limpar.
As respostas confirmadas no FalaVox também vão para `IAVOX_respostas.txt`
na pasta do usuário e para a área de transferência (Ctrl+V no EDIVOX).

**Estados do robô**: Pronto, Ouvindo, Processando, Confirmando e Erro — o estado
aparece por escrito e é anunciado por voz, nunca só pela imagem.

Instalação:

```bash
pip install -r requirements.txt -r requirements-gui.txt
# opcional, para responder com a voz (F2 e F5):
pip install -r requirements-voz.txt
```

- **Linux**: `./run-gui-linux.sh` (ou `python3 run_gui.py`)
- **Windows**: dê duplo clique em `run-gui-windows.bat` (ou `python run_gui.py`)

Sem microfone ou sem Whisper, o FalaVox oferece digitar a resposta — o fluxo
de confirmação e o Mini Caderno continuam funcionando.

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

`tests/test_suite.py` testa os módulos (caderno, EstudaVox, OlhaVox, status) e
`tests/test_interface.py` dirige a interface pelo teclado (F1–F5, Esc, Enter,
Espaço, Ctrl+Shift+M) sem precisar de monitor.

## Estrutura

```
iavox_pdf_audio/
  core/        extractor.py, summarizer.py, image_description.py, reader.py
  tts/         motores de voz (espeak-ng, Piper, Kokoro, Coqui) + selector.py
  suite/
    caderno.py      # Mini Caderno (registro para o professor)
    ambiente.py     # detecção de DOSVOX, microfone, OCR e Ollama
    estudo.py       # EstudaVox: resumo + perguntas
    olhavox.py      # OlhaVox + OCR de imagem/tela
    voz_entrada.py  # FalaVox: gravação + Whisper local
  cli/main.py  # linha de comando acessível
gui/
  janela.py          # janela principal, atalhos, navegação e barra de status
  pagina_inicio.py   # tela inicial (F1–F5, robô, dicas rápidas)
  paginas.py         # telas dos módulos, Mini Caderno e Ajuda
  componentes.py     # cartões, robô com estados, voz de feedback, tarefas
  ajustes.py         # configurações avançadas
  theme.py, icones.py, assets/robo.png
run_gui.py
```
