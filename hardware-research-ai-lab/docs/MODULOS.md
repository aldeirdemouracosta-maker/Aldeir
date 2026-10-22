# Módulos (estado na Fase 0)

| Módulo | Pacote | Implementado | Planejado |
|---|---|---|---|
| hardware-discovery | `internal/discovery` | CPU (flags SSE/AVX/AVX2…), RAM, blocos, PCI (vendor/device/rev/driver/link), perfil de GPU, parser de `vulkaninfo`, JSON | NVIDIA/Intel, sensores, ReBAR, mais tabelas de PCI ID |
| research-engine | `internal/research`, `internal/gitscan` | cadastro, consulta, validação; **Fase 1:** verificação online (`ls-remote`, clone raso sem checkout, HEAD HTTP), detecção de licença, sobreposição de verificações, analisador de histórico (reversões, issues, palavras-chave), evidências ancoradas em commit | issues via API (exigiria token), análise de diffs |
| tool-registry | `internal/tools` | catálogo (19 ferramentas), estados `disponivel/ausente/incompativel/nao_testado`, versão mínima, interface `Adapter` | verificação de licença real |
| simulation-engine | `internal/simulation` + `adapters/{mgpusim,gem5}` | detecção e metadados; `ClaimEquivalence` recusa equivalência sem evidência; **Fase 2:** preparo, revisão, aprovação, compilação e execução controlada do MGPUSim (amostra `fir`) com métricas simuladas | calibração (Fase 5), gem5 |
| compiler-lab | `internal/compiler` + `adapters/mesa` | inventário Mesa/RADV/NIR/ACO, glslang/shaderc/SPIRV-Tools, prontidão offline | análises offline (Fase 3) |
| benchmark-engine | `internal/benchmark` | autoteste SHA-256 determinístico, temperatura, origens, `ClaimImprovement` | benchmarks Vulkan (Fase 4) |
| experiment-database | `internal/storage`, `migrations/` | SQLite, 2 migrações, export JSON/CSV, log de comandos | consultas analíticas |
| ai-research-agent | `internal/agents` + `adapters/llama` | interface `Provider`, Ollama/llama.cpp (detecção; endpoint só loopback), política (`Review`, `Approve`) | geração e avaliação de hipóteses (Fase 6) |
| security | `internal/security` | `Runner`, `ConfinePath` | — |
| (novo) config / report | `internal/config`, `internal/report` | configuração validada; relatório MD/JSON | — |
