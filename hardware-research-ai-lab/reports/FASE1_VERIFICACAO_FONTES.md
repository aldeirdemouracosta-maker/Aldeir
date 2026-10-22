# Verificação online das fontes — execução de 2026-10-22

Comando: `hrail research verificar --online --clonar --profundidade 50` (somente leitura; sem checkout).
Ambiente: VM de nuvem com proxy que **permite git em github.com** e **bloqueia** gitlab.freedesktop.org, www.gem5.org e docs.mesa3d.org.

| Fonte | Resultado | Último commit visto | Licença detectada × catálogo |
|---|---|---|---|
| mgpusim | verificado | `62a691424fe3` · 2026-10-15 | MIT × MIT ✔ |
| gem5-repo | verificado | `fed0e07e930f` · 2026-10-21 | `COPYING` presente, **não reconhecida automaticamente** → revisão humana (catálogo diz BSD-3-Clause; **não confirmado**) |
| vulkan-samples | verificado | `b69afa54965d` · 2026-10-20 | Apache-2.0 × Apache-2.0 ✔ |
| llama-cpp | verificado | `a37cc46104eb` · 2026-10-21 | MIT × MIT ✔ |
| ps5-vulkan | **existe** (verificado) | `f410e67a0241` · 2026-10-12 | **GPL-3.0** detectada (catálogo dizia "desconhecida") |
| mesa (GitLab) | **inacessível** (proxy 403) | — | — |
| gem5-site | **inacessível** (403) | — | — |
| radv-docs | **inacessível** (403) | — | — |

## Leituras e ressalvas
- "Verificado" = o repositório existe, responde e tem histórico. **Não** prova que o dono é o oficial; confira manualmente.
- `ps5-vulkan` existe e tem atividade recente, mas **conteúdo e legalidade não foram avaliados**; continua sem execução.
  A licença GPL-3.0 do arquivo LICENSE não resolve a questão de origem do material.
- Mesa e os dois sites seguem **não verificados**; rode `scripts/verificar-fontes.sh` numa rede com acesso.
- Manutenção ("ativo/possivelmente inativo") é heurística pela data do último commit.

## Achados de histórico (profundidade 50, ~56 commits do mgpusim; amostra, não conclusão)
- **mgpusim — pista relevante para a RX 580, ainda NÃO validada:** os commits `9c3f4ca` (2026-07-08, #290/#293) e `7d8578f` (2026-06-15, #262)
  descrevem o modelo como "GCN3 (**gfx803**)", e o primeiro recompila os kernels de teste para **gfx803** com ROCm 7 (observando que
  gfx803 "não está no ROCm moderno"). Como a Polaris (RX 580) é tratada como gfx803 pelas toolchains, há **uma pista a favor de
  compatibilidade em nível de ISA/emulação**. Isso **não** estabelece equivalência de microarquitetura nem de temporização
  (CUs, caches, memória, clocks da variante 2048SP): o HRAIL continua recusando `GCN3 ≡ Polaris` sem calibração medida.
  A palavra `polaris` não aparece em nenhum dos 56 commits (`gfx803`: 2 commits). Conferir os dois commits na fonte antes de usá-los.
  Quando houver um experimento, registre a evidência (decisão humana) com `hrail research evidencia --fonte mgpusim --commit 9c3f4ca ...`.
- gem5 e Vulkan-Samples têm reversões no período, sem relação com Polaris/RX 580.
- llama.cpp: nenhum achado para as palavras pesquisadas nos 50 commits.
- "Sem achados" continua sendo ausência de evidência, não de compatibilidade.
