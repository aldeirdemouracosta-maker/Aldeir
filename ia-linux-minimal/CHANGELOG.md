# Changelog — IA Linux Minimal

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
