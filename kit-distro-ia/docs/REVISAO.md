# Revisão estática dos scripts (tarefas 1 e 2)

**Não foi possível gerar nem testar a ISO neste ambiente**: a sessão em nuvem bloqueia
deb.debian.org, deb.xanmod.org/dl.xanmod.org e github.com (403/CONNECT recusado) e não tem /dev/kvm.
Tudo abaixo é revisão de leitura; nada foi executado de ponta a ponta.

## Corrigido
- `xanmod.list.binary` adicionado: arquivos `.chroot` só valem durante o build; sem o `.binary`
  o sistema instalado ficaria sem o repositório XanMod e não receberia atualizações do kernel.
- llama.cpp: tag agora obrigatória (`LLAMA_TAG=bNNNN`), em vez de clonar o `master`;
  `-DGGML_BMI2=OFF` (Ivy Bridge-E não tem BMI2); build estático e remoção de `/opt/llama.cpp`
  (os binários antes dependiam do diretório de build via RPATH; a cópia dos `.so` era frágil).
- `spirv-headers` adicionado aos pacotes de build (exigido por versões recentes do backend Vulkan).
- `cpu-performance.service`: não falha mais se algum `scaling_governor` não existir; ordena em `sysinit.target`.
- `build-iso.sh`: instala `debian-archive-keyring` (host Ubuntu precisa dele para trixie) e aplica `chmod +x` nos hooks.

## A confirmar em máquina com rede (não verificado)
1. Linha do repositório XanMod (`deb http://deb.xanmod.org trixie main`) e se a chave `archive.key` é aceita pelo `live-build`.
2. Nome do pacote `linux-xanmod-lts-x64v2` no trixie (o PDF cita LTS 6.18.53 em 21/09/2026).
3. Tag estável atual do llama.cpp.
4. `debootstrap` do host Ubuntu 24.04 conhece `trixie` (senão, usar host Debian 13 ou atualizar o debootstrap).
5. Nome do serviço `zramswap.service` e formato de `/etc/default/zramswap` no zram-tools do trixie.
6. Hooks em `config/hooks/live/` (convenção do live-build atual).
7. O XanMod fica como entrada padrão do GRUB por ter versão maior que o kernel do Debian; conferir no menu.

## Observação
`CLAUDE.md` cita RX 580 de 8 GB; o PDF cita RX 580 2048SP. Confirme o modelo exato (afeta a BIOS/Vulkan).
