# Build

## Pré-requisitos (host)

- Linux x86_64 com as dependências usuais de build do Buildroot (gcc,
  make, perl, python3, bc, rsync, wget/curl, cpio, unzip, etc. — ver
  https://buildroot.org/downloads/manual/manual.html#requirement).
- `genimage` (para gerar `disk.img` particionado nos alvos `bios`/`uefi`
  — ver `buildroot/board/ia-linux/post-image.sh`).
- `dosfstools` (`mkdosfs`) e `mtools` (`mcopy`) — usados por `genimage`
  para montar a partição `efi.vfat` no alvo `uefi`. Faltavam desta
  lista até serem descobertos rodando `post-image.sh` de ponta a ponta
  de verdade (ver `CHANGELOG.md`, seção de correções de bugs).
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

- `ai-core` foi compilado, testado (`cargo test`, 102 testes) e verificado
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
  Buildroot, cross-compilação) **não foi executada** neste ambiente —
  mas a montagem do disco final (`buildroot/board/ia-linux/post-image.sh`
  + `genimage-bios.cfg`/`genimage-uefi.cfg`) **foi**, com `genimage`
  instalado e um `system.ext4`/`bzImage`/`bootx64.efi` de mentira no
  lugar dos artefatos reais do Buildroot. Isso pegou 3 bugs reais que
  `bash -n`/`shellcheck` nunca pegariam (ver `CHANGELOG.md`): o
  `grub.cfg` tinha um placeholder de PARTUUID que nada substituía, e os
  dois `genimage-*.cfg` esperavam arquivos (`system.ext4`, `efi.vfat`)
  que nenhum passo criava com esses nomes exatos. Depois da correção,
  `disk.img` foi gerado com sucesso nos dois alvos, e a UEFI foi
  verificada byte a byte (parsing manual de MBR/GPT + `mtools`): o
  `BOOTX64.EFI` está no caminho de fallback correto da especificação
  UEFI, e o `system.ext4` embutido tem exatamente o UUID que `grub.cfg`
  busca. O que ainda não foi testado é o Buildroot produzindo esses
  artefatos de verdade (kernel, GRUB, rootfs reais) — só a integração
  genimage em torno deles.
- Este ambiente também não tem `/sys/module/damon_reclaim` nem cgroup v2
  montados — a AI Memory (0.6, `ai-core/src/memory.rs`) foi validada com
  diretórios temporários simulando a mesma estrutura de arquivos simples
  do kernel (ver `IA_DAMON_SYSFS`/`IA_CGROUP_ROOT` abaixo), não contra o
  kernel real.
- Tem `clang`, mas não tem `bpftool` nem `/sys/kernel/sched_ext` — por
  isso a AI Scheduler (0.7, `ai-core/src/scheduler.rs`) usa o
  controlador `cpu` de cgroup v2 (`cpu.weight`) em vez de um scheduler
  `sched_ext`/eBPF de verdade, pela mesma razão de validação. Ver
  `kernel/patches/README.md` para a decisão completa.
- Diferente do DAMON/cgroup v2, `/proc/loadavg` e `/proc/meminfo`
  existem e são legíveis neste ambiente — a telemetria da 0.8
  (`ai-core/src/telemetry.rs`) foi validada contra o `/proc` real deste
  sandbox, não simulada. Só o efeito da decisão (escrever `cpu.weight`)
  continua testado contra diretórios simulando cgroupfs, pela mesma
  razão da 0.7.

## Desenvolvendo apenas o `ai-core` (sem Buildroot/QEMU)

```sh
cd ai-core
cargo test              # 102 testes unitários (a maioria sem dependências externas; alguns usam sockets TCP/Unix locais)
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
3. Grave em um SSD/pendrive com o instalador (recomendado — ver nota
   abaixo sobre suas salvaguardas):
   ```sh
   sudo ./scripts/install-to-device.sh \
       .build/buildroot-2026.08/output/images/disk.img /dev/sdX
   ```
   Ou manualmente: `sudo dd if=disk.img of=/dev/sdX bs=4M status=progress conv=fsync`
   (confira o dispositivo de destino com cuidado — `dd` sobrescreve sem
   confirmação; é exatamente esse risco que `install-to-device.sh`
   reduz, sem eliminar).
4. Copie modelos `.gguf` para a partição DATA (rótulo `IA_DATA`) antes ou
   depois do primeiro boot — ver `models/README.md`.

`scripts/install-to-device.sh` (etapa 0.9) recusa gravar se o destino
não for um dispositivo de bloco de verdade, se a imagem for maior que o
destino, ou se o destino parecer ser o disco onde a raiz do host está
montada — e exige digitar o caminho do dispositivo de novo como
confirmação. É um script real, testado neste ambiente (incluindo um bug
de verdade encontrado e corrigido — ver `CHANGELOG.md`), mas as
salvaguardas são best-effort: confira o dispositivo de destino sempre,
mesmo usando o script.

**O que este ambiente de desenvolvimento não pode validar**: se o modo
`RECOVERY` (menu de boot definido desde a 0.1.1, ver
`buildroot/board/ia-linux/grub.cfg`) realmente funciona num PC físico.
Isso exige hardware real e fica como passo manual explícito para quem
gravar a imagem de verdade — ver `docs/roadmap.md`.

## Release reprodutível

```sh
./scripts/make-release.sh            # versão lida de ai-core/Cargo.toml
./scripts/make-release.sh 1.2.3      # ou versão explícita
```

Roda os mesmos 4 gates de qualidade usados manualmente em cada etapa
deste projeto (`cargo test`, `cargo clippy -- -D warnings`, `cargo fmt
--check`, `shellcheck` em todos os scripts) e, quando
`.build/buildroot-<versão>/` existe, roda `make legal-info` (ver
`docs/licenses.md`) e gera `SHA256SUMS` das imagens em `.release/`.
Sem a árvore Buildroot (como neste ambiente de desenvolvimento), os
gates ainda rodam e passam — o script avisa e pula a parte que depende
do Buildroot, em vez de falhar.
