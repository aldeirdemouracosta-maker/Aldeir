---
name: aether-revisar-diff
description: "Revê arquivos alterados e alinhamento do diff ao objetivo, preservando mudanças anteriores."
---

# Revisar diff

1. Capture git_status no início para identificar mudanças anteriores do usuário.
   Leia os arquivos pertinentes antes de atribuir alterações à tarefa atual.
2. Capture git_status e git_diff ao revisar. Mostre arquivos alterados, escopo e
   objetivo. git_diff mostra mudanças não staged; alterações staged e arquivos
   não rastreados exigem inspeção adicional autorizada para uma revisão completa.
3. Compare cada alteração ao objetivo. Identifique mudanças inesperadas, efeitos
   colaterais e trechos que precisam de evidência ou decisão do usuário.
4. Preserve mudanças anteriores. Sem baseline confiável, declare a impossibilidade
   de atribuir autoria; não sobrescreva nem descarte arquivos para simplificar o diff.
5. Relate verificações observadas e limitações. Repositório ou ferramenta ausente
   é BLOCKED. Não trate worktree ou diretório de trabalho como sandbox.
6. Não faça commit, push, reset, checkout de descarte ou limpeza automática.

Esta habilidade apenas orienta uma revisão local dentro das permissões existentes.
