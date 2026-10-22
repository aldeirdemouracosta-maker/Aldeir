# Validação da Fase 1

Data: 2026-10-22 · `./scripts/validar.sh`: gofmt, vet, **67 testes, 0 falhas**, build ok.

## Critérios de conclusão (ROADMAP)
| Critério | Estado |
|---|---|
| `verification` das fontes preenchida (hash/data/licença) | **parcial**: 5 de 8 verificadas (github.com). Mesa (GitLab), gem5.org e docs.mesa3d.org **bloqueados** pelo proxy → seguem `nao_verificado` |
| Clones rasos com tamanho limitado em `data/` | sim (profundidade, `--filter=blob:none`, `--no-checkout`; ~3 MB para 5 repositórios) |
| Consultas em commits/reversões/issues gravando evidências com URL | sim (`historico`, `commits`, `evidencia`); issues: só a referência no texto, sem API |
| Testes com repositório Git local fictício | sim (`gitscan`, `research/verify`, e2e) |

## Testes novos
- `gitscan`: reversões e commit revertido, palavras-chave, issues, `--max/--desde/--caminhos`, entradas inválidas, repositório inexistente,
  **hooks/fsmonitor maliciosos não executam**, persistência/upsert, falsos positivos (squash, "Fixes a bug").
- `research/verify`: clone raso (e fetch na 2ª vez, sem checkout), licença divergente/desconhecida, só `ls-remote` → `parcial`, remoto inexistente → `inacessivel`, web 200/404/recusa, detecção de licença, sobreposição sem alterar o catálogo.
- `experiments`: `AddEvidence` atualiza estado e tabela de forma consistente.
- e2e: fluxo `init → verificar (offline) → historico → commits → experimento → evidencia → experiment list`.

## Defeitos achados pela execução real e corrigidos
1. Commits de squash-merge (Vulkan-Samples) eram marcados como reversão por conterem "This reverts commit" no meio do corpo → agora só vale a 1ª linha do corpo ou assunto `Revert…`.
2. "Fixes a bug…" gerava a issue "a" → agora só referências `#N`, `!N`, `owner/repo#N` ou URL.

## Não validado / limites
- Mesa/GitLab e sites: sem acesso; rode `scripts/verificar-fontes.sh` em rede liberada.
- Licença do gem5 (`COPYING`) não reconhecida automaticamente; BSD-3-Clause do catálogo **não confirmada**.
- Dono oficial das fontes não é confirmado automaticamente.
- Nenhuma validação em GPU real continua pendente (RX 580 2048SP); no Windows use `scripts/coletar-windows.ps1` (não testado em Windows real).
- Fase 2 **não** foi iniciada.
