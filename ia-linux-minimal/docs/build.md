# Build

## Pré-requisitos (host)

- Linux x86_64 com as dependências usuais de build do Buildroot (gcc,
  make, perl, python3, bc, rsync, wget/curl, cpio, unzip, etc. — ver
  https://buildroot.org/downloads/manual/manual.html#requirement).
- `genimage` (para gerar `disk.img` particionado nos alvos `bios`/`uefi`
  — ver `buildroot/board/ia-linux/post-image.sh`).
- `qemu-system-x86_64` (para testar o alvo `qemu`).
- Acesso à internet para baixar o Buildroot e os pacotes que ele por sua
  vez baixa (kernel, llama.cpp, Mesa etc.).

## Fluxo

```sh
cd ia-linux-minimal
./build.sh qemu     # ou: bios | uefi
```

Equivalente, passo a passo:

```sh
./scripts/fetch-buildroot.sh          # baixa Buildroot 2026.08 em .build/
./scripts/configure.sh qemu           # aplica buildroot/configs/ia_linux_qemu_x86_64_defconfig
./scripts/compile.sh                  # make (pode levar bastante tempo na 1ª vez)
./scripts/run-qemu.sh                 # sobe a imagem no QEMU (alvo qemu)
```

Antes de compilar um defconfig pela primeira vez com uma árvore Buildroot
real, rode a checagem best-effort de nomes de opção:

```sh
./scripts/validate-buildroot-configs.sh .build/buildroot-2026.08
```

## Estado deste ambiente de desenvolvimento

Esta árvore foi escrita e testada **sem** acesso a `buildroot.org` (o
sandbox onde o projeto foi montado não tem esse acesso de rede). Por
isso:

- `ai-core` foi compilado, testado (`cargo test`, 65 testes) e verificado
  com `cargo clippy -- -D warnings` diretamente — isso não depende do
  Buildroot.
- Todos os scripts shell (`rootfs-overlay/`, `scripts/`, `buildroot/board/`)
  passaram por `bash -n` e `shellcheck -S warning`.
- As opções `BR2_*` nos defconfigs seguem a convenção de nomes do
  Buildroot e foram escritas com cuidado, mas **não foram confirmadas
  símbolo-a-símbolo** contra a árvore 2026.08 real. Rode
  `scripts/validate-buildroot-configs.sh` no seu host antes do primeiro
  build, e espere ajustar 1-2 nomes de opção via `make menuconfig` se
  algo tiver mudado entre versões.
- A compilação completa (download do kernel/llama.cpp/Mesa pelo
  Buildroot, cross-compilação, geração de `disk.img`) **não foi
  executada** neste ambiente.
- Este ambiente também não tem `/sys/module/damon_reclaim` nem cgroup v2
  montados — a AI Memory (0.6, `ai-core/src/memory.rs`) foi validada com
  diretórios temporários simulando a mesma estrutura de arquivos simples
  do kernel (ver `IA_DAMON_SYSFS`/`IA_CGROUP_ROOT` abaixo), não contra o
  kernel real.

## Desenvolvendo apenas o `ai-core` (sem Buildroot/QEMU)

```sh
cd ai-core
cargo test              # 65 testes unitários (a maioria sem dependências externas; alguns usam sockets TCP/Unix locais)
cargo clippy -- -D warnings
cargo run                # roda como servidor; Ctrl+C para parar
IA_DATA_DIR=/tmp/data IA_CORE_SOCKET=/tmp/ai-core.sock cargo run &
ai-core STATUS            # (após 'cargo build', use target/debug/ai-core como cliente)
```

`IA_DATA_DIR` e `IA_CORE_SOCKET` (variáveis de ambiente) sobrepõem os
padrões `/data` e `/run/ai-core.sock` — é assim que os testes de
integração e o smoke test manual deste projeto rodam sem precisar de
root nem de um sistema de arquivos real montado em `/data`. Da mesma
forma, `IA_LLAMA_ADDR` sobrepõe `127.0.0.1:8080` (endereço do
llama-server), e `IA_DAMON_SYSFS`/`IA_CGROUP_ROOT`/`IA_RUN_DIR`
sobrepõem `/sys/module/damon_reclaim/parameters`,
`/sys/fs/cgroup/ia-linux` e `/run` respectivamente (ver
`ai-core/src/memory.rs`) — em produção usam os caminhos reais do
kernel; em desenvolvimento, apontam para diretórios temporários.

## Instalação física (`bios`/`uefi`)

1. `./build.sh bios` (ou `uefi`).
2. `disk.img` aparece em `.build/buildroot-2026.08/output/images/`.
3. Grave em um SSD/pendrive: `sudo dd if=disk.img of=/dev/sdX bs=4M status=progress conv=fsync`
   (confira o dispositivo de destino com cuidado — `dd` sobrescreve sem
   confirmação).
4. Copie modelos `.gguf` para a partição DATA (rótulo `IA_DATA`) antes ou
   depois do primeiro boot — ver `models/README.md`.
