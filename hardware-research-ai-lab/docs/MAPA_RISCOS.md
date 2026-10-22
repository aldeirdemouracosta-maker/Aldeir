# Mapa de risco

| Nível | Descrição | Fase 0 |
|---|---|---|
| A | análise offline, sem executar código de hardware | **habilitado** |
| B | diagnóstico e benchmark leve em espaço de usuário | **habilitado** |
| C | experimento isolado com código de GPU | desativado |
| D | alteração de driver em ambiente controlado | desativado |
| E | kernel, firmware ou alteração persistente | desativado |

Campos de `experiments.Experiment`: id, descrição, fonte da hipótese, hardware aplicável, evidências favoráveis e
contrárias (com URL), pré-requisitos, impacto potencial, risco operacional (baixo/medio/alto), reversibilidade
(total/parcial/irreversivel), confiança (nenhuma/baixa/media/alta), necessidade de validação física, nível, origem.

## Estado de evidência

| Estado | Significado |
|---|---|
| `sem_evidencia` | nada encontrado. **Não** é incompatibilidade; é desconhecimento |
| `evidencia_favoravel` | só evidências a favor |
| `evidencia_de_incompatibilidade` | há evidência contrária registrada |
| `evidencia_conflitante` | ambas existem |

## Regras aplicadas em código

- C/D/E: `config.Validate` recusa habilitar; `Classify`/`Save` devolvem `ErrNivelDesativado`.
- Risco alto ou reversibilidade irreversível são incoerentes com A/B.
- Confiança "alta" exige evidência favorável.
- Melhoria só pode ser declarada com `benchmark.ClaimImprovement`: ≥3 amostras `measured` por grupo, mesma métrica/unidade,
  fora de testes de infraestrutura.
- IA: `agents.Approve` sempre falha; `agents.Review` exige humano para ações privilegiadas e medições para alegações.
