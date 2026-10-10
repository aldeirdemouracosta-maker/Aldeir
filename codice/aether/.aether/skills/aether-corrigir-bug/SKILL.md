---
name: aether-corrigir-bug
description: "Reproduz falhas quando possível e corrige a causa com mudança mínima e verificação pertinente."
---

# Corrigir bug

1. Identifique comportamento esperado, observado, entrada e código relevante.
   Pergunte quando o comportamento esperado estiver indefinido.
2. Registre o estado inicial e tente uma reprodução pequena com os comandos
   disponíveis e autorizados. Associe a evidência à tarefa e ao artefato afetado.
3. Quando não puder reproduzir, declare NÃO REPRODUZIDO e explique o impedimento.
   Uma hipótese de causa não é uma reprodução. Terminal desabilitado é BLOCKED.
4. Mostre um plano. Faça a menor correção adequada; preserve APIs e alterações
   anteriores do usuário. Prefira edit_file com trecho único conhecido.
5. Verifique a correção e regressões relacionadas quando a execução for permitida.
   Compare o mesmo cenário antes e depois. Não declare PASS sem execução observada.
6. Revise o diff contra o objetivo. Informe arquivos, causa sustentada por evidência,
   verificações executadas e limitações restantes.

Não instale modelos ou dependências, não altere permissões e não faça commit,
push ou descarte de mudanças automaticamente.
