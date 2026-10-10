---
name: aether-quality-gates
description: "Compara verificações iniciais e finais, separando PASS, FAIL, BLOCKED e N/A com evidência real."
---

# Quality gates locais do Aether

Adaptação original de procedimentos inspirados no contrato LVCP do usuário.
Não é uma engine LVCP instalada e não presume executáveis LVQA ou VHQA.

1. Registre estado inicial, objetivo, artefatos e verificações pertinentes. Localize
   os comandos reais no projeto; não invente executáveis ou etapas de validação.
2. Quando pertinente e autorizado, execute verificações antes da mudança com
   run_terminal, phase=before e artifact apontando ao artefato correto.
3. Mostre um plano antes de alterar. Preserve falhas preexistentes como baseline;
   não as apresente como regressões causadas pela tarefa sem comparação.
4. Repita verificações pertinentes depois da mudança com phase=after, mantendo
   comando, ambiente e escopo comparáveis. Compare falhas novas, persistentes e
   resolvidas. Uma verificação só executada depois não prova o estado anterior.
5. Classifique cada gate: PASS exige execução e saída zero observadas; FAIL indica
   falha observada; BLOCKED indica que a execução não ocorreu; N/A exige motivo
   de inaplicabilidade. Registre BLOCKED ou N/A via record_evidence.
6. Se o terminal estiver desabilitado, não o habilite. Informe a limitação e registre
   o comando previsto como BLOCKED. Timeout não é sandbox nem validação aprovada.
7. Entregue comparação antes/depois e pendências. Nunca alegue revisão ou aprovação
   humana sem registro humano real e identificável.
