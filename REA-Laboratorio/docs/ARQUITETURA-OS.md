# Arquitetura do REA-Laboratorio OS

Status: **projeto**. Nada aqui foi construído ou testado; afirmações de compatibilidade são hipóteses com teste de aceite.

## 1. Escolha da base: Debian Live (live-build), release estável atual (trixie, confirmar na hora do build)

| Critério | Alpine (mkimage) | Debian Live (live-build) |
|---|---|---|
| Libc | musl | glibc |
| Tamanho base | menor (dezenas de MB de rootfs) | maior (rootfs mínimo com Xorg+Fluxbox, sem *recommends*, tende a centenas de MB — **medir**) |
| BIOS + UEFI em ISO híbrida | suportado | suportado (isohybrid, syslinux + grub-efi) |
| Persistência no pendrive | via `lbu`/overlay manual, pouco padronizada | nativa no `live-boot` (partição/arquivo rotulado `persistence`) |
| Binários de terceiros (Ghidra/JDK, Ollama, llama.cpp pré-compilado, wheels Python) | frequentes incompatibilidades com musl | glibc: o caso comum e mais bem suportado |
| Pacotes de RE/forense/rede/disco (binwalk, radare2, qemu-utils, nmap, sleuthkit, p7zip...) | cobertura menor | ampla (a **disponibilidade exata de cada um deve ser verificada**) |
| x86-64 sem AVX2 | linha de base x86-64 | linha de base x86-64 (pacotes genéricos) |

**Decisão:** Debian Live. Motivo principal: o produto depende de ferramentas externas (JVM/Ghidra, runtimes de IA, wheels Python)
distribuídas para glibc, e a persistência de projetos é requisito; o custo é tamanho, que é a principal **incerteza**.

**Gate de tamanho (G1):** se a ISO mínima medida passar de 700 MB mesmo com `--apt-recommends false`, xz, sem firmware
não-livre e sem localizações extras, abrir um *spike* de Alpine (apenas a base + Fluxbox + UI) e comparar tamanho **e**
funcionamento do REA Core antes de decidir. Não se assume que Alpine resolverá: as ferramentas teriam de ser testadas sob musl.

**Sem AVX2:** não depende do kernel/distro (baseline x86-64) e sim do que for compilado/baixado. llama.cpp deve ser
compilado sem `-march=native` (variantes CPU com seleção em tempo de execução ou build SSE4.2/AVX). Teste: boot no QEMU com
`-cpu Nehalem` (sem AVX) e execução do módulo de IA.

## 2. Camadas
```
Hardware (BIOS/UEFI, x86-64)
└─ Kernel Debian + live-boot (squashfs xz, overlay em RAM, disco do host NÃO montado)
   └─ Fluxbox + REA Shell (GTK3, Python)  ──  terminal acessível
      └─ Serviços REA (usuário 'rea', sem root; ver §3)
         └─ Módulos (manifesto) ── núcleo na ISO; pesados em pasta/partição externa REA-MODULES
```
- **ISO principal (≤ 700 MB, meta):** base, Fluxbox, REA Shell, REA Core/Guardian/Evidence/Projects, ferramentas leves e
  universais (hash, file, unzip/7z, xxd, strings), documentação offline.
- **Externo (REA-MODULES, no pendrive ou rede, assinado por hash):** JDK + Ghidra, runtimes/modelos de IA, QEMU completo,
  laboratórios grandes. Instalação **somente mediante autorização** (ver SEGURANCA.md).
- **Persistência (futuro):** partição `persistence` (ext4, rótulo exato) + `REA-DATA` com projetos/evidências. Criada pelo
  usuário com ferramenta explícita; o boot **nunca** cria nem altera partições.

## 3. Serviços (processos locais, comunicação por sockets Unix; nenhum escuta em rede por padrão)
| Serviço | Responsabilidade | Dependências |
|---|---|---|
| **REA Core** | registro de módulos, leitura de manifestos, filas de tarefas, API local, estado de disponibilidade | — |
| **REA AutoLab** | roteia um artefato ao laboratório adequado (detecta tipo por assinatura, nunca executa), monta o pipeline | Core, Guardian |
| **REA Guardian** | aplica a política: somente leitura, bloqueio de execução de amostras, de gravação de firmware e de rede; autorizações | Core |
| **REA Evidence** | SHA-256, cadeia de custódia, proveniência, relatórios (JSON + Markdown/HTML) | Core |
| **REA Projects** | projetos, cópias de trabalho (modo Oficina), persistência | Core, Evidence |
| **REA AI Bridge** | adaptadores de motores de IA (llama.cpp, Ollama, LM Studio, OpenAI-compatível), detecção de CPU/Vulkan/CUDA | Core, Guardian |
| **REA Chat** | conversa com o motor escolhido; chamadas de ferramentas passam por Guardian | AI Bridge |
| **REA Full** | orquestra análise completa: AutoLab → laboratórios → Evidence → relatório; botão "Full REA" | todos |

Princípios: (1) o sistema inicia e é útil **sem** IA; (2) todo "disponível" na UI vem de um verificador real (arquivo
presente + hash + teste de fumaça), nunca de um valor fixo; (3) toda ação que não é leitura passa pelo Guardian.

## 4. Integração com REA/Ghidra existentes
Via MCP/CLI sem alterar o código original do REA. A configuração real (`codex mcp get rea`) ainda precisa ser auditada
(ver relatório). Ghidra roda em módulo externo (JDK + Ghidra); a compatibilidade em Debian Live é **hipótese a testar**.
