# Integrações e fontes

Catálogo completo em `catalog/sources.json` (`hrail research sources`). **Nenhuma fonte foi verificada online**: o ambiente
de criação bloqueou o acesso a GitHub/GitLab. Por isso `verification.status = nao_verificado` e
`last_commit_consulted = null` em todas — deliberadamente. Licenças listadas são dicas (`license_verified=false`).

| Fonte | URL | Papel | Cuidados |
|---|---|---|---|
| MGPUSim | https://github.com/sarchlab/mgpusim | simulador de GPU (Go; modelo GCN3 segundo o projeto) | GCN3 ≠ Polaris/gfx9 sem evidência |
| gem5 | https://github.com/gem5/gem5 · https://www.gem5.org/ | simulador de CPU/sistema | build pesado; suporte a GPU AMD a verificar |
| Mesa | https://gitlab.freedesktop.org/mesa/mesa | RADV, NIR, ACO | nunca instalar Mesa experimental sobre o do sistema |
| Docs RADV | https://docs.mesa3d.org/drivers/radv.html | documentação | reflete a versão atual, não a instalada |
| Vulkan-Samples | https://github.com/KhronosGroup/Vulkan-Samples | base de microbenchmarks | exige SDK; não baixar sem autorização |
| PS5_Vulkan | https://github.com/mihawk-99/PS5_Vulkan | referência de terceiros | **não verificada**; sem execução, sem chaves/firmware/código proprietário |
| llama.cpp | https://github.com/ggml-org/llama.cpp | IA local | não presumir AVX2; backend Vulkan a medir |

## Contrato dos adaptadores

`tools.Adapter`: `ID()`, `Metadata()` (inclui `equivalence_claims`, sempre vazio, e `executes_workloads=false`) e
`Detect(ctx, registry)`. Na Fase 0, adaptadores não executam cargas.

## Verificação futura (Fase 1, com rede e autorização)

Confirmar existência, dono esperado, licença (arquivo LICENSE), último commit (hash + data), arquivamento e issues abertas;
só então `verification.status = verificado` com `checked_at` e `last_commit_consulted`. `research.Validate` já recusa
fonte "verificada" sem esses campos.
