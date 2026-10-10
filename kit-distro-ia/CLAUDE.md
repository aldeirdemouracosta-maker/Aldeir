# CLAUDE.md — Distro enxuta para IA local (ISO instalável em SSD)

## Objetivo
Gerar uma **ISO instalável** (Debian 13 "trixie", via `live-build`) enxuta, voltada a **IA local**
(llama.cpp + Vulkan na RX 580), para instalar num **SSD de 120 GB**. Foco: pouco uso de RAM em repouso,
nada de bagagem (sem snap, sem apps desnecessários), simplicidade acima de estética.

## Hardware alvo (máquina de IA)
- Placa HUANANZHI X79 (v3.1), Xeon E5-2630L v2 (Ivy Bridge-E, 6 núcleos, **SEM AVX2 e SEM FMA**; tem AVX e F16C)
- 16 GB RAM quad channel
- GPU de IA: AMD RX 580 8 GB (Polaris/gfx803) -> **Vulkan (Mesa RADV)**; ROCm oficial não suporta gfx803
- GPU de vídeo: NVIDIA GT 210 1 GB, só para dar imagem (driver **nouveau**; NÃO usar driver NVIDIA 340)
- Disco do sistema: SSD 120 GB (alvo da instalação). Há Windows em OUTRO disco e um NVMe de 500 GB.

## Decisões já tomadas
1. Base: Debian 13 (trixie), `live-build`, ISO híbrida com instalador (`--debian-installer live`).
2. Kernel: **XanMod LTS x64v2** (`linux-xanmod-lts-x64v2`) + kernel padrão do Debian mantido no menu como reserva.
   **NUNCA x64v3/x64v4**: exigem AVX2/AVX-512 e não inicializam nesta CPU.
3. llama.cpp compilado no build com Vulkan e SEM AVX2/FMA (ver `build/config/hooks/live/0100-llama-cpp.hook.chroot`).
4. zram (zstd) em vez de swap em disco; governor de CPU em `performance`; `amdgpu.ppfeaturemask=0xffffffff`.
5. Desktop: variável `DESKTOP` (padrão `minimal` = Openbox + terminal + navegador; `none` = só terminal).
   (O usuário ainda pode trocar; se não houver resposta, manter `minimal`.)
6. Modelos GGUF em partição separada `/models` (sobrevive a reinstalações do sistema).
7. `mitigations=off` fica DESLIGADO por padrão; apenas documentar como opção.
8. macOS/Hackintosh NÃO entra na ISO (licença da Apple + instalador só via macrecovery). Está só como estudo em `docs/`.

## Tarefas (em ordem)
1. Ler `build/build-iso.sh` e toda a pasta `build/config/`; revisar e corrigir o que estiver errado.
   O kit foi escrito SEM ser testado: trate tudo como rascunho a validar.
2. **Pesquisar versões atuais** (data de hoje: out/2026) e confirmar: nome dos pacotes XanMod no Debian 13,
   tag estável do llama.cpp, pacotes `glslc`/`libvulkan-dev`/`mesa-vulkan-drivers` no trixie,
   caminho correto dos hooks do `live-build` instalado.
3. Rodar `sudo ./build/build-iso.sh` (host Debian/Ubuntu com root) e corrigir erros até gerar `build/work/*.iso`.
4. Testar a ISO em VM antes de qualquer disco real:
   `qemu-system-x86_64 -enable-kvm -m 4G -cdrom build/work/*.iso -boot d`
   Checar: boot live, instalador, XanMod no menu do GRUB, `llama-cli --version`, `vulkaninfo --summary`.
5. Medir RAM em repouso (`free -m`) e tamanho da ISO; registrar em `docs/RESULTADOS.md`.
6. Gerar `docs/INSTALAR.md` com passo a passo de gravação em pendrive e instalação no SSD de 120 GB.

## Regras de segurança (IMPORTANTE)
- **Jamais escrever em discos reais** sem o usuário pedir. Não rodar `dd`, `mkfs`, `parted`, `wipefs` em /dev/sdX ou /dev/nvme*.
- Na instalação real, o usuário deve **escolher apenas o SSD de 120 GB**; recomende desconectar os discos
  com Windows e NVMe durante a instalação, ou conferir o modelo/tamanho no particionador.
- Não inventar URLs, versões ou nomes de pacotes: confirmar por busca ou `apt-cache policy`.
- Não adicionar nada que exija AVX2 (kernels x64v3, binários pré-compilados "avx2", imagens com `-march=native` de outra máquina).

## Definição de pronto
ISO gera sem erro, boota em VM, instala, XanMod é o kernel padrão com fallback do Debian no GRUB,
llama.cpp (Vulkan, sem AVX2) presente, RAM em repouso medida e documentada.
