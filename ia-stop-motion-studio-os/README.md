# IA Stop-Motion Studio OS

Sistema para criar filmes stop motion quadro a quadro com bonecos de pano:
captura, animação, edição e render, com IA local. Hardware alvo: Xeon X79 +
RX 580 8 GB, sobre Ubuntu 24.04 LTS.

Arquitetura completa: [`../docs/ia-linux-minimal/ia-stop-motion-studio-os-arquitetura.md`](../docs/ia-linux-minimal/ia-stop-motion-studio-os-arquitetura.md)

![Início](docs/screenshots/inicio.png)

## O que já funciona (v0.1)

**Interface da maquete original:** barra superior, menu lateral, dock inferior,
painel Sistema (CPU, RAM, GPU, VRAM e temperatura da RX 580, armazenamento) e
Projeto Recente.

**Captura** (`Espaço` captura):
- webcam/câmera USB via QtMultimedia, com seleção da câmera
- **Travar câmera**: foco, exposição e balanço de branco em manual (Qt e V4L2 via
  `v4l2-ctl`) para evitar flicker entre as fotos
- **onion skin** de 1 a 3 quadros (`O`), grade de terços (`G`), alternar ao vivo /
  último quadro (`L`)
- cada foto é gravada **no disco na hora**, de forma atômica (arquivo temporário + fsync + rename)
- **Apagar último** (`Backspace`): o quadro vai para `<projeto>/lixeira`, não é destruído
- **dope sheet**: cada foto pode ficar 1–24 quadros na tela
- reprodução a 8/12/15/24/30 fps (`P`), tira de quadros
- **Importar fotos** já tiradas (celular, DSLR), respeitando a rotação EXIF

![Captura](docs/screenshots/captura.png)

**Renderização:** exporta MP4 em YouTube 16:9, Reels/TikTok 9:16, Quadrado 1:1 ou
4K. Usa o encoder da GPU via VAAPI quando existe `/dev/dri/renderD128` (RX 580) e
cai para x264 na CPU se falhar.

As demais telas da maquete (Editor de Cenas, Timeline, IA Local, Personagens,
Cenários…) já existem na navegação e indicam em que etapa serão implementadas.

## Compilar e rodar (Ubuntu 24.04)

```bash
sudo apt install cmake g++ qt6-base-dev qt6-declarative-dev qt6-multimedia-dev \
  qml6-module-qtquick qml6-module-qtquick-controls qml6-module-qtquick-layouts \
  qml6-module-qtquick-window qml6-module-qtquick-dialogs qml6-module-qtmultimedia \
  qml6-module-qtqml-workerscript qml6-module-qtquick-templates \
  gstreamer1.0-plugins-good gstreamer1.0-plugins-bad ffmpeg v4l-utils

cmake -S app -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j
./build/ia-stop-motion-studio
```

Testes: `ctest --test-dir build --output-on-failure`

Projetos ficam em `~/IA-StopMotion/Projetos/<nome>/` (`project.json`, `frames/`,
`lixeira/`, `export/`). A pasta base pode ser trocada com a variável `IA_SMS_HOME`.

Captura de tela sem monitor: `./build/ia-stop-motion-studio --screenshot tela.png captura`

## Próximas etapas

3. Timeline sobre o MLT (cortes, áudio, títulos, transições) e dope sheet com trilha de áudio
4. Remoção de flicker e exportação com áudio
5. IA local: remover suportes/fundo, sincronia labial (Rhubarb), legendas (whisper.cpp)
6. Modos do sistema (Captura / Edição / IA / Render) com cgroups e perfis AMDGPU, depois sched_ext
7. ISO do IA Stop-Motion Studio OS
