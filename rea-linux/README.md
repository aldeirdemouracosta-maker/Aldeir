# REA Linux

Distro mínima (Debian 13 + Openbox) feita só para o laboratório de engenharia reversa com IA local:
**Ghidra 12.1.4 + GhidraMCP 2.0 + REA + Ollama (RX 580 via Vulkan) + Codex leve + Painel REA**.

ISO estimada: ~2-3 GB (sem CUDA do Ollama) · instalado: ~4 GB · modelos: ~9 GB (fora da ISO).

## Gerar a ISO

Num Linux com Docker ou Podman (ex.: o PC H61 com Ubuntu):

```bash
sudo ./build.sh
```

O build roda dentro de um container `debian:trixie` (ambiente oficial do live-build) e baixa
Ghidra, GhidraMCP, Node, REA, Ollama e JADX da internet. Leva de 30 a 90 min.
Resultado: `rea-linux-AAAAMMDD.iso` (+ `.sha256`). Log completo em `build.log`.

Em um Debian 13 com live-build: `sudo ./build.sh --direto`.

## Testar antes do SSD

```bash
qemu-system-x86_64 -enable-kvm -m 8G -smp 4 -cdrom rea-linux-*.iso
```

(Na VM não há RX 580: serve para testar boot, painel, Ghidra e REA. A IA roda na CPU.)

## Usar direto do pendrive (com persistência)

A ISO já liga a opção `persistence`: se o pendrive tiver uma área de persistência,
tudo o que você salvar (configurações, projetos e os ~9 GB de modelos) continua lá depois de desligar.
Sem essa área, o sistema funciona igual, mas esquece tudo ao desligar.

Recomendado: pendrive de **32 GB ou mais, USB 3.0** (os modelos são lidos do pendrive).

Jeito mais simples, pelo Windows, com o **Ventoy** (ventoy.net):
1. Instale o Ventoy no pendrive e copie a ISO para ele.
2. Crie um arquivo de persistência com rótulo `persistence` (Ventoy oferece imagens prontas
   e o utilitário de persistência na documentação "Persistence Plugin").
3. Dentro do arquivo de persistência deve existir `persistence.conf` com a linha `/ union`.
4. No `ventoy.json`, associe a ISO do REA Linux a esse arquivo de persistência.
5. Dê boot pelo pendrive e escolha a ISO com persistência.

O painel mostra no status se a persistência está ativa; o botão **Baixar modelos**
avisa antes de baixar se ela não estiver.

## Instalar na máquina Xeon/RX 580

1. Grave a ISO num pendrive (`dd` ou Ventoy).
2. No menu de boot, escolha **Install** (instalador Debian, já em pt-BR).
3. Usuário: **rea** (já vem preenchido; o login automático usa esse nome).
4. Opcional e recomendado: crie uma partição ext4 com rótulo **MODELOS** (≥ 20 GB).
   Ela é montada em `/modelos` sozinha e guarda os modelos entre reinstalações:
   `sudo mkfs.ext4 -L MODELOS /dev/sdXN`

## Primeiro uso

O sistema entra direto no **Painel REA**:

1. **Baixar/preparar modelos** – baixa `qwen3:8b` (agente, GPU) e LLM4Decompile 6.7B v2 (CPU)
   e cria `qwen3-8b-gpu` (contexto 16k) e `llm4decompile-cpu`.
2. Escolha o modo do Ghidra para o Codex:
   - **Modo janela**: abra o Ghidra, o projeto e o binário no CodeBrowser (porta 8080).
   - **Modo headless**: escolha o binário no painel; o Codex abre e analisa sozinho, sem janela.
3. **Abrir Codex leve** e peça, por exemplo:
   `Chame a ferramenta MCP ghidra.list_functions com offset 0 e limit 10.`
4. **Refinar**: cole o pseudocódigo do Ghidra e receba C legível do LLM4Decompile.

Clique com o botão direito na área de trabalho para o menu (terminal, Ghidra, desligar).

## O que vem instalado

| Item | Onde |
|---|---|
| Ghidra 12.1.4 | `/opt/ghidra/atual` (comando `ghidra`) |
| GhidraMCP 2.0 | extensão no perfil do usuário + `/opt/ghidra-mcp`; servidor `ghidra-mcp` (com headless) |
| REA (rea-agents) + Frida | `/opt/node`, comando `rea` |
| Codex CLI | comando `codex`; configuração enxuta em `~/.codex/config.toml` |
| Ollama | serviço `ollama` (Vulkan, 1 pedido por vez, modelos em `/modelos/ollama`) |
| JADX, Apktool, adb, binwalk, gdb, pwntools | `/usr/local/bin` |
| Painel REA | `rea-painel` (PySide6) |

Atualizar REA, Codex, Ollama e ferramentas Python: botão **Atualizar ferramentas**
(Ghidra e GhidraMCP ficam fixos de propósito).

## Estrutura do kit

```
build.sh                         gera a ISO (container debian:trixie)
auto/config                      opções do live-build
config/package-lists/            pacotes Debian
config/hooks/normal/             downloads no build (Ghidra, uv, Node/REA, Ollama/JADX, ajustes)
config/includes.chroot/          arquivos copiados para o sistema (serviços, painel, scripts, skel)
config/includes.installer/       respostas padrão do instalador
```

Uso permitido: análise de software seu ou que você tem autorização para examinar
(mesma regra do REA).
