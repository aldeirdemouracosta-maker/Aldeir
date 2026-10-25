# Plano de fases

| Fase | Entrega | Critério de aceite |
|---|---|---|
| **0** (esta) | Auditoria, escolha de base, documentação, scripts não destrutivos | auditoria local executada e anexada (pendente); documentos revisados |
| **1** | ISO mínima Debian Live (Fluxbox, terminal) reproduzível | Gate G1 (BIOS, UEFI, sem AVX2, offline, tamanho, disco intocado) |
| **2** | REA Core + Guardian + Evidence; formato de manifesto; verificador de disponibilidade | testes unitários; relatório SHA-256 de um arquivo de exemplo; Guardian bloqueia operação proibida |
| **3** | REA Shell (GTK) com mascote, botões ligados a verificadores reais | teste de teclado; nenhum botão habilitado sem módulo disponível; RAM medida |
| **4** | AI Bridge: Ollama e OpenAI-compatível primeiro, depois llama.cpp e LM Studio | adaptadores contra servidores simulados; detecção CPU/Vulkan/CUDA real; sistema inicia sem modelo |
| **5** | Labs núcleo: formatos binários (PE/ELF), ZIP, documentos, ISO | amostras inofensivas versionadas; proteção zip-bomb; só leitura comprovada |
| **6** | REA Projects, persistência no pendrive, modo Oficina | cópia de trabalho com hash; original inalterado; persistência sobrevive a reboot |
| **7** | Módulos externos: JDK + Ghidra, integração REA (MCP) | `tools/list` real do REA; ferramentas só marcadas suportadas após teste |
| **8** | REA Full + REA Chat | pipeline ponta a ponta com relatório; resultado registra motor/modelo |
| **9+** | Labs restantes (TV Box, BIOS, ROMs, vídeo, mobile, redes, discos, links...) em lotes | cada um com manifesto, testes e fumaça |

Regras: não avançar de fase sem o critério de aceite registrado; cada fase termina com commit local e relatório; riscos
vigentes: tamanho da ISO, compatibilidade de Ghidra/IA sem AVX2, acessibilidade da shell, drivers sem firmware não-livre.
