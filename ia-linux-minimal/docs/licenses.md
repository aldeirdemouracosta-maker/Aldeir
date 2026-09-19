# Licenciamento

Resumo por componente. Nenhum componente central é fechado; nenhuma
dependência de nuvem é obrigatória para o sistema funcionar.

| Componente | Licença | Origem | Vendorizado neste repositório? |
|---|---|---|---|
| `ai-core` (Rust) | Apache-2.0 | código próprio deste projeto | sim — `ai-core/` |
| `ia-shell` e demais scripts `ia-*` | Apache-2.0 | código próprio deste projeto | sim — `rootfs-overlay/` |
| Scripts de build (`scripts/`, `build.sh`, `buildroot/board/`) | Apache-2.0 | código próprio deste projeto | sim |
| Linux kernel | GPL-2.0-only | upstream kernel.org | não — baixado pelo Buildroot; apenas `kernel/config/` (fragmentos de configuração, sem código) é nosso |
| Buildroot | GPL-2.0 (ferramentas) + licenças variadas (pacotes) | upstream buildroot.org | não — baixado por `scripts/fetch-buildroot.sh` |
| BusyBox | GPL-2.0 | via Buildroot | não |
| Mesa / RADV / Vulkan Loader | maioria MIT, algumas partes em outras licenças permissivas — varia por sub-componente | via Buildroot | não |
| `llama.cpp` | MIT | via Buildroot (pacote upstream oficial) | não |
| `linux-firmware` (blobs AMDGPU) | redistribuível, **não é código-fonte aberto** | via Buildroot | não |

## Por que a separação importa

O AI-Linux (dissertação de Nathan Loretan, MSc, University of Glasgow,
2018) — referência científica deste projeto, ver
`kernel/patches/README.md` — modifica arquivos GPL-2.0 do kernel Linux
diretamente. Este projeto **não** modifica o código-fonte do kernel: usa
Linux 6.18 LTS upstream, configurado por fragmentos (`kernel/config/`),
o que evita qualquer ambiguidade sobre licenciamento de código de kernel
modificado nesta série 0.x.

`linux-firmware` merece destaque separado: os blobs binários necessários
para GPUs AMD funcionarem são redistribuíveis (por isso podem estar na
imagem final), mas não são código-fonte aberto no sentido usual. Uma
imagem física do IA Linux Minimal com suporte a GPU AMD portanto não é
"100% código-fonte aberto" em sentido estrito — apenas o sistema
operacional e as ferramentas em torno dele são.

## Nossa escolha: Apache-2.0 para código de user-space

`ai-core`, `ia-shell` e os demais scripts `ia-*` são Apache-2.0
(`LICENSE` na raiz deste diretório; `ai-core/LICENSE` é uma cópia para
que o crate carregue sua própria licença, como é convenção no
ecossistema Rust). Apache-2.0 foi escolhida por ser permissiva o
suficiente para permitir portar este trabalho para outro hardware (ex.:
Raspberry Pi, Orange Pi, PCs antigos) sem obrigar quem faz isso a manter
tudo sob a mesma licença — diferente do que aconteceria se
inadvertidamente misturássemos código GPL de kernel com as ferramentas
de user-space.

## Conformidade ao distribuir uma imagem completa

Ao gerar uma imagem final (`disk.img`), rode `make legal-info` dentro da
árvore Buildroot (`.build/buildroot-2026.08/`) para produzir o material
de conformidade de todas as licenças de terceiros envolvidas (kernel,
BusyBox, Mesa, llama.cpp, linux-firmware etc.). Este repositório não
tenta reproduzir manualmente essa listagem — ela depende exatamente de
quais pacotes/opções estão habilitados no defconfig usado.
