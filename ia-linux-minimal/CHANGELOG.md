# Changelog — IA Linux Minimal

## install-to-device.sh: confirmação chegava vazia (causa não isolada)

`disk.img` gerado com sucesso pela primeira vez nesta sessão. Na
gravação (`install-to-device.sh`), a confirmação exigida (digitar o
caminho do dispositivo de novo) falhava repetidamente com
`confirmação não bateu`, mesmo com o usuário digitando `/dev/sdd`
manualmente, isolando o comando (sem colar blocos com múltiplos
comandos) e com `read -r CONFIRM < /dev/tty` (tentativa de correção
anterior, que não resolveu).

Um teste de depuração instrumentado confirmou: `CONFIRM=[]` (vazio,
0 bytes) chegava ao script, enquanto `DEVICE=[/dev/sdd]` (8 bytes)
estava correto — ou seja, o `read` de fato recebia uma linha vazia
antes da linha digitada pelo usuário, não um texto diferente. `set -e`
não abortava o script nesse ponto, confirmando que o `read` retornou
com sucesso (uma linha vazia real chegou), não um EOF de verdade.

**Não conseguimos isolar a causa raiz remotamente** — testes
equivalentes (`read -r x` isolado, com e sem `sudo`, direto no
terminal do usuário) sempre funcionaram perfeitamente, byte a byte,
fora do contexto do script real. A hipótese mais provável (colar
blocos de comando com uma linha em branco sobrando) foi descartada
depois que o usuário isolou o comando e digitou manualmente e o
problema persistiu.

**Mitigação aplicada** (sem enfraquecer a segurança): em vez de
abortar na primeira leitura vazia, o script agora tenta de novo até 3
vezes, continuando a exigir o caminho exato do dispositivo em alguma
das tentativas. Testado com um teste funcional simulando entradas
vazias seguidas da entrada correta — confirma que o loop aceita a
confirmação certa depois de descartar as vazias, e continuaria
recusando qualquer coisa que não seja exatamente o caminho do
dispositivo.

## post-build.sh e post-image.sh: 2 bugs reais na reta final do build

O build real do usuário (mesma sessão dos bugs de Kconfig abaixo)
passou de toda a compilação (toolchain, kernel, llama.cpp, Vulkan) e
travou em duas etapas finais:

1. **`post-build.sh` calculava a raiz do repositório com um nível de
   menos.** `IA_LINUX_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"` —
   mas o script vive em `buildroot/board/ia-linux/`, 3 níveis abaixo
   da raiz (onde está `hardware/detect.sh`, que o script instala), não
   2. Resolvia para `buildroot/` em vez da raiz, e o `install` falhava
   por arquivo inexistente. Corrigido para `../../../`.

2. **`post-image.sh` lia o modo (`bios`/`uefi`) do argumento errado.**
   O Buildroot sempre invoca scripts de `BR2_ROOTFS_POST_IMAGE_SCRIPT`
   como `<script> <BINARIES_DIR> <BR2_ROOTFS_POST_IMAGE_SCRIPT_ARGS...>`
   — o primeiro argumento é **sempre** `BINARIES_DIR`, nunca o que
   configuramos em `BR2_ROOTFS_POST_IMAGE_SCRIPT_ARGS`. O script lia
   `MODE="${1:-bios}"` (pegando o caminho de `BINARIES_DIR` como se
   fosse o modo) em vez de `MODE="${2:-bios}"`. Corrigido.

**Retificação importante sobre validação anterior**: a seção
"Correções pós-0.9" abaixo descreve testes de `post-image.sh`
chamando-o como `post-image.sh bios` (um argumento). Isso replicava
nosso próprio entendimento errado da convenção de chamada do
Buildroot, não a convenção real — por isso aquele teste nunca
detectou o bug 2 acima, mesmo sendo descrito como "validação de
verdade". Os testes foram re-executados agora chamando o script com a
convenção real (`post-image.sh <BINARIES_DIR> bios`, dois argumentos)
e confirmam a correção. Fica como lição registrada: reproduzir a
própria suposição sobre uma interface externa, em vez da interface
documentada/real, não é validação — só descobrimos isso ao ler o
comportamento real do Buildroot depois que o build de verdade expôs o
bug.

## Bugs reais de Kconfig encontrados no primeiro build de verdade (fora do sandbox)

Continuação da sessão de depuração ao vivo com o usuário rodando
`./build.sh bios` numa máquina real com acesso ao buildroot.org —
depois da correção do `BR2_EXTERNAL` (ver seção abaixo), mais 3 bugs
reais apareceram, todos do mesmo tipo já avisado em `docs/build.md`:
nomes de opção `BR2_*` nunca confirmados símbolo-a-símbolo contra a
árvore 2026.08 real.

1. **`BR2_PACKAGE_UTIL_LINUX_LSBLK` não existe.** Usado nos três
   defconfigs e em `package/ai-shell/Config.in`. Confirmado inspecionando
   `package/util-linux/Config.in` real: `lsblk` não tem opção
   individual nessa árvore — faz parte do "basic set"
   (`BR2_PACKAGE_UTIL_LINUX_BINARIES`, que já inclui blkid, findmnt,
   lscpu etc. e seleciona as libs necessárias). Corrigido nos três
   defconfigs e no `select`.

2. **`BR2_x86_cortina=n` no defconfig `qemu`** — símbolo que nunca
   existiu em nenhuma versão do Buildroot ("Cortina" é uma família de
   SoC ARM/MIPS sem relação com x86_64); aparentemente uma sobra sem
   função. Removido.

3. **`BR2_TARGET_GRUB2_BUILTIN_MODULES`/`BR2_TARGET_GRUB2_BUILTIN_CONFIG`
   foram divididas em variantes `_PC` (BIOS) e `_EFI` (UEFI) no
   Buildroot 2021.08+.** Essa foi a causa real do erro fatal
   `"You have legacy configuration in your .config!"` que travava o
   build (`Makefile.legacy`) — as duas opções antigas ainda existem
   como stubs de compatibilidade que disparam `BR2_LEGACY=y`, mas o
   Buildroot trata isso como erro duro, não aviso. Diagnosticado
   cruzando programaticamente (script Python descartável) a lista de
   símbolos com `select BR2_LEGACY` em `Config.in.legacy` contra o
   `.config` real gerado — nem `validate-buildroot-configs.sh` (que só
   detecta símbolo inexistente, não símbolo legado-mas-ainda-aceito)
   nem `make oldconfig` (que não reproduziu o erro) apontavam isso
   diretamente. Corrigido: `ia_linux_bios_x86_64_defconfig` agora usa
   `BR2_TARGET_GRUB2_BUILTIN_MODULES_PC`/`_CONFIG_PC`;
   `ia_linux_uefi_x86_64_defconfig` usa `_MODULES_EFI`/`_CONFIG_EFI`.

Também corrigido `scripts/validate-buildroot-configs.sh`: ele buscava
o nome do símbolo **sem** o prefixo `BR2_` (`short="${symbol#BR2_}"`),
mas o Buildroot mantém esse prefixo literal na linha `config` dos
`Config.in` (diferente do Kconfig do kernel Linux) — por isso o script
acusava até símbolos básicos e certamente reais
(`BR2_x86_64`, `BR2_ROOTFS_OVERLAY`) como "não encontrados" na primeira
rodada. Corrigido e testado com uma árvore Buildroot fake neste
sandbox antes de pedir pro usuário rodar de novo.

Nenhum desses 4 bugs (BR2_EXTERNAL, UTIL_LINUX_LSBLK, x86_cortina,
GRUB2_BUILTIN_*) apareceu em nenhum teste rodado neste sandbox — só um
build real, numa árvore Buildroot 2026.08 de verdade, expunha cada um.
Ainda não confirmado neste ponto: se o build passa da etapa de
configuração para a compilação de fato (kernel, toolchain, llama.cpp).

## Correção crítica — BR2_EXTERNAL apontava para o diretório errado

Primeira vez que `./build.sh` rodou de verdade fora deste sandbox (numa
máquina do usuário com acesso à internet real ao buildroot.org) — e
travou imediatamente em:

```
buildroot/Config.in:1: can't open file
  ".../buildroot/package/ai-core/Config.in"
make[1]: *** [Makefile:1050: ia_linux_bios_x86_64_defconfig] Erro 1
```

**Causa raiz**: `scripts/configure.sh`/`compile.sh`/`make-release.sh`
passavam `BR2_EXTERNAL="${IA_LINUX_ROOT}/buildroot"` (o subdiretório
`buildroot/`) para o `make` do Buildroot. Mas os defconfigs
(`buildroot/configs/*_defconfig`) sempre assumiram, de forma
inconsistente com isso, que `$(BR2_EXTERNAL_IA_LINUX_PATH)` era a
**raiz do repositório** — por exemplo
`BR2_ROOTFS_OVERLAY="$(BR2_EXTERNAL_IA_LINUX_PATH)/rootfs-overlay"`
(sem prefixo `buildroot/`, e `rootfs-overlay/` só existe na raiz) e
`BR2_TARGET_GRUB2_BUILTIN_CONFIG="$(BR2_EXTERNAL_IA_LINUX_PATH)/buildroot/board/ia-linux/grub.cfg"`
(com prefixo `buildroot/` explícito, porque os arquivos de board *sim*
vivem num subdiretório). Os arquivos que definem a raiz do
BR2_EXTERNAL de verdade para o Buildroot (`Config.in`, `external.desc`,
`external.mk`) estavam fisicamente dentro de `buildroot/`, um nível
abaixo de onde os próprios defconfigs esperavam — por isso o Kconfig
não achava `package/ai-core/Config.in` (que sempre esteve, correto, na
raiz do repositório).

Esse bug nunca apareceu nas 102 execuções de `cargo test` nem nos
testes manuais de `post-image.sh`/`genimage` feitos neste ambiente,
porque nenhum dos dois invoca o `make` do Buildroot com Kconfig de
verdade — só um build real, fora do sandbox, expunha isso.

**Corrigido**: `Config.in`, `external.desc` e `external.mk` movidos
para a raiz do repositório (onde já viviam `package/`, `ai-core/`,
`kernel/`, `rootfs-overlay/` — nunca precisaram mudar de lugar, pois
os defconfigs sempre os referenciaram corretamente a partir daí).
`buildroot/` continua existindo, mas agora só guarda o que os
defconfigs esperam dele: os `*_defconfig` (copiados manualmente por
`configure.sh`, sem depender de descoberta automática do Buildroot) e
`board/ia-linux/` (genimage, grub.cfg, post-image.sh, post-build.sh —
referenciados com o prefixo `buildroot/` explícito nos defconfigs, que
nunca mudou). `configure.sh`, `compile.sh` e `make-release.sh` agora
passam `BR2_EXTERNAL="${IA_LINUX_ROOT}"` (raiz do repo), consistente
com o que os defconfigs sempre esperaram.

**Validação**: sem uma árvore Buildroot real disponível neste sandbox
(ver nota de rede em `docs/build.md`), a correção foi verificada
resolvendo manualmente, no sistema de arquivos, cada caminho que os
três defconfigs referenciam via `$(BR2_EXTERNAL_IA_LINUX_PATH)/...`
com a raiz do repositório como base — todos os 13 caminhos existem
exatamente onde esperado (`package/ai-core/Config.in`,
`package/ai-shell/Config.in`, `ai-core/`, `package/ai-shell/src`,
`kernel/config/*`, `rootfs-overlay/`, `buildroot/board/ia-linux/*`).
`bash -n`/`shellcheck -S warning` limpos nos três scripts alterados.
O que isso **não** confirma: se o Kconfig do Buildroot 2026.08 real
aceita a sintaxe dos `Config.in` de `ai-core`/`ai-shell` sem outros
erros — só o teste do usuário, na máquina real, vai confirmar o
próximo passo da cadeia de build.

## Correções pós-0.9 — bugs reais de boot físico encontrados por revisão + teste de verdade

Depois do fechamento da série 0.1–0.9, uma revisão de código dedicada
(`/code-review` em toda a árvore) e testes manuais de ponta a ponta do
pipeline `post-image.sh` + `genimage` (não executados antes — ver
"Encerramento da série 0.x" abaixo) encontraram e corrigiram **3 bugs
reais que teriam impedido o boot físico** e 1 falha de segurança
silenciosa, nenhum deles pego por `shellcheck`/`bash -n`/`cargo test`:

1. **`buildroot/board/ia-linux/grub.cfg` tinha um placeholder nunca
   substituído.** `search --fs-uuid --set=root __SYSTEM_PARTUUID__` e
   `root=PARTUUID=__SYSTEM_PARTUUID__` continham o texto literal
   `__SYSTEM_PARTUUID__` — nenhum script em nenhum lugar da árvore
   jamais substituía isso por um valor real. Pior: mesmo substituído,
   `--fs-uuid` busca por UUID de **sistema de arquivos**, não por
   PARTUUID — são dois espaços de UUID diferentes que nunca colidem.
   O GRUB teria caído no prompt de resgate em todo boot físico.
   **Corrigido**: `grub.cfg` agora usa um UUID de sistema de arquivos
   fixo (`11111111-1111-4111-8111-111111111111`, escolhido por nós,
   não gerado aleatoriamente), e `post-image.sh` grava esse mesmo UUID
   no `system.ext4` via `tune2fs -U` antes de montar o disco — sem
   precisar de nenhum passo de template.
2. **`genimage-bios.cfg`/`genimage-uefi.cfg` esperavam um arquivo
   `system.ext4` que nada criava com esse nome.** O Buildroot
   (`BR2_TARGET_ROOTFS_EXT2`) produz `rootfs.ext2`/`rootfs.ext4`, não
   `system.ext4` — `genimage` teria falhado por arquivo não encontrado
   assim que alguém tentasse compilar de verdade. **Corrigido**:
   `post-image.sh` agora procura por `rootfs.ext*` em `$BINARIES_DIR`
   (sem depender de adivinhar o nome exato, que varia entre versões do
   Buildroot — ver nota de honestidade em `docs/build.md`) e copia para
   `system.ext4` antes de aplicar o UUID fixo.
3. **`genimage-uefi.cfg` esperava um `efi.vfat` que nenhum passo do
   pipeline jamais construía.** Não existia nem um bloco `image
   efi.vfat { vfat {...} }` no próprio `.cfg`, nem um passo que
   montasse o conteúdo da partição EFI em algum lugar. **Corrigido**:
   `post-image.sh` localiza o binário EFI do GRUB
   (`bootx64.efi`, produzido por `BR2_TARGET_GRUB2_X86_64_EFI` +
   `BR2_TARGET_GRUB2_BUILTIN_CONFIG`) e o copia para
   `$BINARIES_DIR/EFI/BOOT/BOOTX64.EFI` — o caminho de fallback padrão
   da especificação UEFI, reconhecido por qualquer firmware sem
   precisar de entrada prévia na NVRAM — e `genimage-uefi.cfg` ganhou
   o bloco `image efi.vfat` que faltava.
4. **`scripts/install-to-device.sh` pulava a checagem "não é o disco
   do host" em silêncio** quando `findmnt`/`lsblk` estavam ausentes ou
   falhavam, sem avisar o operador — quem lesse só a saída do script
   não teria como saber que essa proteção específica não rodou.
   **Corrigido**: agora imprime um aviso explícito nesse caso, em vez
   de simplesmente seguir em frente como se a checagem tivesse passado.

**Validação de verdade, não só leitura de código**: os bugs 1-3 foram
confirmados reproduzindo o pipeline completo neste ambiente —
`genimage`, `dosfstools` (`mkdosfs`) e `mtools` (`mcopy`) foram
instalados (essas duas últimas eram dependências de host que também
faltavam na documentação — corrigido em `docs/build.md`), e
`post-image.sh` foi rodado de ponta a ponta com um `rootfs.ext2` e um
`bootx64.efi` de mentira no lugar dos artefatos reais do Buildroot.
Depois da correção, o `disk.img` gerado foi inspecionado byte a byte
(parsing manual de tabela de partição MBR/GPT em Python + `mtools`):
o UUID do `system.ext4` embutido bate exatamente com o que `grub.cfg`
busca, e `EFI/BOOT/BOOTX64.EFI` está no lugar certo dentro da partição
EFI. O bug 4 foi confirmado simulando `findmnt` ausente/falhando e
comparando a saída antes/depois da correção.

O que continua **não** validado (e não seria honesto alegar que foi):
o Buildroot de fato compilando o kernel/GRUB/rootfs reais — só a
integração `genimage` em torno desses artefatos foi exercitada aqui,
com substitutos. Ver `docs/build.md` para o estado atualizado.

## Encerramento da série 0.x (0.1–0.9)

Esta é a marca de fechamento desta fase de desenvolvimento. Resumo do
que existe nesta árvore, honestamente:

**Implementado e testado neste ambiente:**
- `ai-core` (Rust): hardware, modelos, backend CPU/Vulkan, multiagente,
  memória (DAMON_RECLAIM + cgroup v2), scheduler (cgroup v2 cpu.weight)
  e scheduler adaptativo (telemetria real de `/proc`) — 102 testes
  unitários, `clippy -D warnings` limpo, `cargo fmt` aplicado.
- Todos os scripts shell (`ia-shell` e os `ia-*`, `scripts/*.sh`,
  `buildroot/board/*`) — `shellcheck -S warning` limpo, `bash -n` limpo.
- Um instalador com salvaguardas reais (`install-to-device.sh`, com um
  bug de segurança de verdade encontrado e corrigido durante o teste) e
  um gate de release reprodutível (`make-release.sh`), ambos exercitados
  de ponta a ponta neste ambiente.
- Três smoke tests manuais ponta a ponta contra o daemon real rodando
  (multiagente, memória+scheduler compartilhando cgroup, scheduler
  adaptativo com telemetria real + tokens/s de um `llama-server` de
  mentira).

**Não implementado e explicitamente não fingido como implementado:**
- A compilação completa do Buildroot nunca rodou aqui (sem acesso a
  `buildroot.org` neste sandbox) — as opções `BR2_*` seguem a convenção
  de nomes da versão 2026.08 mas não foram confirmadas símbolo-a-símbolo
  contra a árvore real.
- `damon_reclaim` e cgroup v2 não existem neste ambiente — validados com
  diretórios temporários simulando a mesma estrutura de arquivos, não
  contra o kernel real.
- `bpftool`/`sched_ext` não existem neste ambiente — por isso a etapa
  0.7 entregou `cpu.weight` de cgroup v2 em vez de um scheduler BPF de
  verdade (decisão documentada, não escondida).
- Nenhuma imagem foi de fato gravada num disco nem testada em hardware
  físico. O modo `RECOVERY` existe desde a 0.1.1 mas nunca foi
  verificado num boot real.

**1.0 fica bloqueada** em rodar o pipeline completo
(`fetch-buildroot.sh` → `configure.sh` → `compile.sh` →
`make-release.sh`) contra a árvore Buildroot real — algo que exige
acesso à internet que este ambiente não tem. Até lá, esta é uma árvore
de código completa e testada em tudo que dava para testar sem
Buildroot/kernel real, não uma imagem que alguém rodou. Ver
`docs/roadmap.md` para os detalhes de cada etapa.

## 0.9.0-alpha10 — Instalador + release reprodutível

- Novo `scripts/install-to-device.sh`: grava `disk.img` num SSD/pendrive
  com salvaguardas — recusa se o destino não for um dispositivo de
  bloco de verdade, recusa se a imagem for maior que o destino, exige
  digitar de novo o caminho exato do dispositivo como confirmação (sem
  atalho `--yes`), e recusa gravar sobre o disco onde a raiz do host
  está montada.
  - **Bug real encontrado e corrigido durante o teste manual**: a
    heurística de "não é o disco do host" usava só `lsblk -no PKNAME`,
    que retorna vazio quando a raiz está montada direto num disco
    inteiro sem partição (exatamente o caso deste próprio sandbox de
    desenvolvimento — `/dev/vda` montado direto em `/`). Sem correção,
    o script teria deixado passar exatamente o caso mais perigoso.
    Corrigido com um fallback para o nome base do próprio dispositivo
    quando `PKNAME` vem vazio, e reconfirmado testando contra `/dev/vda`
    (recusa corretamente) e `/dev/loop0` (passa a checagem, mas aborta
    antes do `dd` porque a confirmação não bateu — nenhuma escrita real
    foi feita em nenhum teste).
- Novo `scripts/make-release.sh`: roda os 4 gates de qualidade usados
  manualmente em cada etapa deste projeto (`cargo test`, `cargo clippy
  -- -D warnings`, `cargo fmt --check`, `shellcheck` em todos os
  scripts), lê a versão de `ai-core/Cargo.toml`, e — quando a árvore
  Buildroot está presente — roda `make legal-info` e gera checksums
  SHA-256 das imagens produzidas. Testado de ponta a ponta neste
  ambiente (sem Buildroot): os 4 gates passam e o script degrada
  graciosamente com um aviso claro em vez de falhar.
- Nota honesta de escopo: **"validar o modo RECOVERY em hardware real"**
  (parte do que a 0.9 originalmente previa) **não é algo que este
  ambiente de desenvolvimento consegue fazer** — não há uma máquina
  física disponível aqui. Isso continua sendo um passo manual explícito
  para quem for gravar a imagem numa máquina real — ver
  `docs/roadmap.md`.
- `ai-core` não mudou nesta etapa (nenhum código Rust novo — 0.9 é sobre
  empacotamento/distribuição); versão sincronizada para 0.9.0 mesmo
  assim, mantendo o número de versão único em todo o projeto. 102 testes
  continuam passando.

## 0.8.0-alpha9 — Scheduler adaptativo (telemetria real, regra determinística)

- Novo módulo `ai-core/src/telemetry.rs`: lê `/proc/loadavg` e
  `/proc/meminfo` diretamente — ao contrário de `memory.rs`/
  `scheduler.rs`, essas leituras **não** precisam de caminho
  parametrizável, porque `/proc` existe de verdade neste ambiente de
  desenvolvimento (mesmo padrão que `hardware.rs` já usa desde a 0.4).
- `telemetry::adapt_weight` é uma **regra determinística se-então**, não
  aprendizado por reforço nem qualquer forma de ML: se o throughput
  recente (tokens/s) caiu bem abaixo do melhor já observado nesta sessão,
  E há contenção real de CPU (carga por núcleo > 1.0), E a memória
  disponível não está criticamente baixa, aumenta `cpu.weight` em 50%
  (capado em 2000); se o throughput está bom e sobra CPU, relaxa de
  volta ao peso base do perfil; caso contrário mantém o peso atual
  (nunca abaixo do peso base).
- `llama_client::complete` passa a retornar `CompletionResult{content,
  tokens_per_second}`, extraindo `timings.predicted_per_second` da
  resposta do llama-server (`json::extract_number_field`, novo,
  encontra campos numéricos em qualquer nível de aninhamento).
- `agent::Task` ganha o campo `tokens_per_second`;
  `AgentManager::tokens_per_second_stats(recent_n)` calcula a média das
  últimas `recent_n` tarefas concluídas e o melhor valor já observado em
  toda a sessão (não persiste — reinicia com o daemon).
- Novo subcomando IPC `SCHED ADAPT` (além de `STATUS`/`APPLY` da 0.7) e
  `ia-scheduler adapt` / `scheduler adapt` no `ia-shell`. Diferente de
  `SCHED APPLY` (peso fixo do perfil), pode subir, manter ou relaxar o
  peso conforme telemetria observada.
- `scheduler::apply_weight` refatorado sobre um novo
  `apply_weight_value(cgroup_root, peso)`, reutilizado por `SCHED ADAPT`
  para aplicar um peso calculado (não apenas o peso fixo do perfil).
- Smoke test manual ponta a ponta: telemetria real do `/proc` deste
  sandbox (`load1=0.25`, `mem_disponivel_pct=96.2`) combinada com
  histórico real de tokens/s de um `llama-server` de mentira (valores
  50.0/8.0/7.5 → média recente 21.8, melhor 50.0, ambos calculados
  corretamente) — a regra manteve o peso porque não havia contenção real
  de CPU neste ambiente, exatamente o comportamento esperado.
- 102 testes unitários (eram 73 na 0.7).

## 0.7.0-alpha8 — AI Scheduler (escopo reduzido: cgroup v2 cpu.weight)

- Novo módulo `ai-core/src/scheduler.rs`: prioriza CPU para o
  processo do modelo/llama-server via o controlador `cpu` de cgroup v2
  (`cpu.weight`, 1-10000, padrão 100), no **mesmo cgroup** que
  `memory.rs` já protege com `memory.low` (0.6). Peso escalado por
  perfil de hardware — TINY 800, LOW 600, MEDIUM 400, LARGE 200.
- Novo comando IPC `SCHED` (`STATUS`, `APPLY`) e utilitário
  `ia-scheduler`, mais o comando `scheduler` em `ia-shell`.
- `ia-server start` agora chama `ia-memory apply` **e**
  `ia-scheduler apply` (ambos melhor esforço, nunca derrubam o início
  do servidor).
- `STATUS` ganha a linha `scheduler_peso`.
- **Decisão de escopo, documentada em detalhe em
  `kernel/patches/README.md`**: o plano original da 0.7 era um
  scheduler `sched_ext`/eBPF completo (programa BPF + agente Rust,
  carregado/removido dinamicamente). Ao chegar nesta etapa, verificamos
  que este ambiente de desenvolvimento tem `clang`, mas não tem
  `bpftool`, não tem `/sys/kernel/sched_ext` nem cgroup v2 — não havia
  como compilar, carregar ou testar um scheduler BPF de verdade aqui.
  Em vez de fingir essa validação, reduzimos a etapa ao controlador
  `cpu` de cgroup v2 (mecanismo padrão do kernel, testável com
  diretórios simulando cgroupfs), mesmo raciocínio já aplicado à AI
  Memory (0.6: DAMON memcg filters → `memory.low`). Um scheduler
  `sched_ext` de verdade continua sendo trabalho futuro explícito, não
  descartado — `kernel/config/sched-ext.fragment` já prepara a opção de
  kernel necessária.
- `kernel/config/ia_linux_x86_64.config` ganha `CONFIG_FAIR_GROUP_SCHED`
  (necessário para `cpu.weight` de cgroup v2 funcionar).
- 73 testes unitários (eram 65 na 0.6).

## 0.6.0-alpha7 — AI Memory

- Novo módulo `ai-core/src/memory.rs` com duas responsabilidades
  separadas: (1) ajustar os parâmetros do módulo `damon_reclaim`
  (`enabled`, `min_age`, `quota_ms`, `quota_sz`) por perfil de hardware
  (TINY/LOW/MEDIUM/LARGE — perfis com menos RAM reclamam páginas frias
  mais cedo); (2) proteger a memória do modelo ativo/KV cache via cgroup
  v2 `memory.low`, calculado como tamanho do arquivo `.gguf` × um fator
  configurável (`IA_MEM_FLOOR_PERCENT` em `runtime.conf`, padrão 150%).
- Novo comando IPC `MEMORY` (`STATUS`, `APPLY`, `PROTECT <bytes>`) e
  utilitário `ia-memory`, mais o comando `memory` em `ia-shell`.
- `ia-server start` chama `ia-memory apply` automaticamente (melhor
  esforço, nunca derruba o início do servidor) depois de escrever
  `/run/ia-server.pid`.
- `model.rs` ganha `active_model_entry()` (nome + tamanho do modelo
  ativo, usado para calcular o piso de proteção).
- `STATUS` ganha duas linhas: `memoria_damon` (disponível/indisponível)
  e `memoria_protegida` (true/false).
- Nota honesta de escopo: este ambiente de desenvolvimento não tem
  `/sys/module/damon_reclaim` nem cgroup v2 montados — não foi possível
  testar contra o kernel real. Por isso os caminhos sysfs/cgroupfs são
  parametrizáveis (`IA_DAMON_SYSFS`, `IA_CGROUP_ROOT`, `IA_RUN_DIR`), e a
  validação foi feita com diretórios temporários simulando a mesma
  estrutura de arquivos simples do kernel, incluindo um smoke test
  manual ponta a ponta. A implementação usa apenas os parâmetros planos
  de `damon_reclaim`, não a hierarquia sysfs completa de
  kdamonds/contexts/schemes (mais complexa e fora do escopo validável
  aqui) — ver `ai-core/src/memory.rs` para a justificativa completa.
- `kernel/config/ia_linux_x86_64.config` já tinha `CONFIG_MEMCG` e
  `CONFIG_DAMON_RECLAIM` habilitados desde a 0.1 (preparação antecipada);
  comentários atualizados para refletir o uso real.
- 65 testes unitários (eram 47 na 0.5).

## 0.5.0-alpha6 — Multiagente

- `ai-core` ganha `AgentManager` (`ai-core/src/agent.rs`): fila de
  tarefas + um único worker thread, processando sequencialmente contra
  `llama-server` — vários papéis (planejador, programador, pesquisador,
  crítico, executor) compartilham o mesmo modelo carregado, em vez de um
  modelo por agente.
- Novos módulos `json.rs` (utilitários JSON mínimos, escritos à mão para
  não adicionar dependências externas) e `llama_client.rs` (cliente HTTP
  mínimo sobre `std::net::TcpStream` para `POST /completion` do
  llama-server).
- Novo comando IPC `AGENT` (`ROLES`, `TASK <papel> <texto>`,
  `STATUS <id>`, `LIST`) e utilitário `ia-agent` (mais o comando `agent`
  em `ia-shell`).
- `STATUS` deixa de reportar "multiagente: não implementado" e passa a
  reportar a fila real (tarefas em fila/executando/concluídas/com erro).
- Bug encontrado e corrigido durante o smoke test manual: o parser JSON
  exigia `"campo":"valor"` sem espaço após `:`; um servidor de teste
  escrito com `json.dumps` do Python (que insere um espaço por padrão)
  quebrava a extração. Corrigido para tolerar espaço em branco entre `:`
  e a string, como o JSON padrão permite — ver `ai-core/src/json.rs`.
- 47 testes unitários (eram 24 na 0.4), incluindo testes de ponta a
  ponta do `AgentManager` contra um `llama-server` de mentira (socket
  TCP local).

## 0.4.0-alpha5 — AI Core (Rust)

- Novo daemon `ai-core` em Rust, substituindo os scripts shell como
  coordenador central de hardware, modelos e backend.
- IPC via socket Unix (`/run/ia-core.sock`), protocolo texto linha-a-linha
  (`STATUS`, `HW`, `MODEL LIST`, `MODEL SELECT <n>`, `BACKEND <auto|cpu|vulkan>`).
- `ia-shell` (BusyBox ash) passa a ser um cliente fino que fala com o
  `ai-core` em vez de reimplementar a lógica em shell.
- Detecção de hardware (CPU/RAM/GPU) movida de `hardware/detect.sh` para o
  módulo `hardware.rs`, mantendo o script shell como fallback de
  recuperação (modo `RECOVERY`).
- Pacote Buildroot `package/ai-core` (Config.in + .mk) para compilar o
  daemon via `cargo` cross-compilado durante o build do Buildroot.
- Testes unitários Rust para parsing de `/proc/cpuinfo`, `/proc/meminfo` e
  seleção de perfil (TINY/LOW/MEDIUM/LARGE).

## 0.3.0-alpha4 — Vulkan/RADV

- Mesa RADV + Vulkan Loader + `vulkaninfo` habilitados no Buildroot.
- `llama.cpp` compilado com backend Vulkan além de CPU.
- Comando `ia-gpu` (status/list/vulkaninfo) e seleção de backend
  `auto|cpu|vulkan` com fallback automático para CPU.
- `ia-benchmark` ganha `cpu`, `vulkan`, `compare`.
- Firmware AMDGPU (`linux-firmware`) habilitado; QEMU permanece CPU-only
  intencionalmente (sem GPU virtual).

## 0.2.0-alpha3 — Inferência em CPU

- Integração do pacote oficial Buildroot `llama.cpp` (`llama-cli`,
  `llama-server`, `llama-bench`).
- Comandos `ia-model` (list/select/active/recommend), `ia-chat`,
  `ia-benchmark`, `ia-server` (start/status/stop, bind em `127.0.0.1:8080`).
- Perfis automáticos por RAM: TINY (<6GB), LOW (6–12GB), MEDIUM (12–24GB),
  LARGE (24GB+), com threads/contexto/batch calculados.
- `/data/config/runtime.conf` para overrides manuais.
- Modelos GGUF mantidos fora da imagem do sistema, em `/data/models`.

## 0.1.1-alpha2 — Hardware físico

- Perfis BIOS (legado) e UEFI 64-bit com GRUB 2.
- Particionamento SYSTEM/RECOVERY/DATA (+ EFI no perfil UEFI).
- Boot por `PARTUUID` em vez de `/dev/sdaN` fixo.
- Drivers SATA/AHCI, NVMe, USB, teclado, rede Intel/Realtek, AMDGPU/Radeon.
- Modo de boot seguro `nomodeset`; RECOVERY montada somente leitura.

## 0.1.0-alpha1 — Boot mínimo

- BR2_EXTERNAL inicial, alvo QEMU x86_64.
- BusyBox + glibc, kernel Linux 6.18.52 LTS fixado.
- cgroups v2, BPF/eBPF e zram habilitados; fragmento `sched_ext`
  preparado, porém desligado por padrão.
- Console somente texto, prompt `IA>`.
- `/data/{models,rag,agents,workspace,sessions,logs}` como área persistente
  separada do sistema.
