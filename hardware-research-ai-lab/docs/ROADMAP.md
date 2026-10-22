# Roadmap

Fases futuras só começam por decisão explícita; **a Fase 0 não avança automaticamente para a 1.**

## Fase 0 — Fundação e diagnóstico (CONCLUÍDA, ver `reports/VALIDACAO_FASE_0.md`)
CLI, descoberta somente leitura, catálogos, SQLite com migrações, risco A/B, autoteste, testes.

## Fase 1 — Analisador de histórico Git e evidências
- **Entrada:** Fase 0 validada; acesso à rede autorizado; lista de repositórios aprovada.
- **Conclusão:** `verification` das 8 fontes preenchida (hash/data do último commit, licença lida do arquivo LICENSE); clones rasos em `data/` com tamanho limitado; consultas por palavra-chave em commits/reversões/issues gravando `evidences` com URL; testes com repositório Git local fictício.
- **Dependências:** `git`; módulo `research`; tabela `evidences`.
- **Riscos:** download volumoso; licenças ambíguas; rate limit; confundir correlação de commits com causalidade. Mitigação: shallow clone, limites, evidência sempre com URL e estado `sem_evidencia` ≠ incompatível.

## Fase 2 — Integração inicial MGPUSim
- **Entrada:** Fase 1 concluída; MGPUSim verificado; autorização para baixar dependências Go.
- **Conclusão:** build isolado em `data/`; execução de um exemplo mínimo com timeout; resultados gravados com `origin=simulated`; documento do que o modelo GCN3 cobre e não cobre.
- **Dependências:** Go, adaptador `mgpusim`, `benchmark`.
- **Riscos:** custo de CPU; falsa equivalência com Polaris; código de terceiros não verificado. Mitigação: revisão do código, sandbox, `ClaimEquivalence`.

## Fase 3 — Compiladores Mesa/NIR/ACO
- **Entrada:** Fase 1; espaço em disco; autorização para clonar Mesa.
- **Conclusão:** Mesa só em diretório isolado (nunca instalado sobre o sistema); análises offline GLSL→SPIR-V→(ACO/NIR dumps) reproduzíveis; inventário de versões.
- **Dependências:** glslang/shaderc, SPIRV-Tools, toolchain de build do Mesa.
- **Riscos:** build pesado; divergência entre Mesa de estudo e do sistema. Mitigação: containers/diretórios isolados, versões registradas.

## Fase 4 — Benchmarks Vulkan na RX 580
- **Entrada:** hardware **real** detectado (`hardware list`); `vulkaninfo` e driver RADV funcionais; nível C avaliado e habilitado explicitamente pelo usuário (compute shaders são código de GPU).
- **Conclusão:** microbenchmarks compute (largura de banda, ALU) com ≥N repetições, temperatura/clock registrados somente por leitura, resultados `measured` com metadados completos.
- **Dependências:** Vulkan-Samples ou código próprio; GLSL→SPIR-V.
- **Riscos:** travamento de GPU, térmica, variância. Mitigação: cargas curtas, timeouts, sem alterar clock/tensão, estatística com ≥3 amostras.

## Fase 5 — Simulação e calibração de modelos de hardware
- **Entrada:** Fases 2 e 4.
- **Conclusão:** erro simulado × medido quantificado por métrica; limites de validade documentados; modelos separados por arquitetura.
- **Dependências:** dados `measured` e `simulated` na mesma métrica.
- **Riscos:** overfitting; extrapolar GCN3→Polaris. Mitigação: validação cruzada, relatórios com `origin`.

## Fase 6 — Agentes de IA para geração e avaliação de hipóteses
- **Entrada:** Fase 1 (evidências) e provedor local verificado (Ollama/llama.cpp).
- **Conclusão:** agente gera hipóteses com citações a `evidences`; `agents.Review` aplicado; toda alegação de melhoria referencia resultados `measured`; auditoria de prompts sem dados pessoais.
- **Dependências:** `agents`, `experiments`.
- **Riscos:** alucinação; vazamento de dados; automação de ações. Mitigação: IA só sugere, humano aprova, endpoints apenas loopback.

## Fase 7 — Validação de otimizações reais
- **Entrada:** hipóteses priorizadas; plano de reversão; nível D/E **somente com aprovação humana explícita** e ambiente isolado.
- **Conclusão:** A/B com baseline e candidato `measured` (≥3 amostras), `ClaimImprovement` aprovado, reversão testada.
- **Dependências:** Fases 4–6.
- **Riscos:** instabilidade do sistema, perda de dados, garantia. Mitigação: máquina/partição de teste, snapshots, nunca em produção.

## Fase 8 — Expansão para outras GPUs e componentes
- **Entrada:** Fase 7 estável.
- **Conclusão:** perfis NVIDIA/Intel/NPU/CPU; tabelas de PCI ID versionadas; adaptadores novos pelo contrato `tools.Adapter`.
- **Dependências:** hardware de referência adicional.
- **Riscos:** generalização indevida. Mitigação: nenhuma equivalência sem evidência por componente.
