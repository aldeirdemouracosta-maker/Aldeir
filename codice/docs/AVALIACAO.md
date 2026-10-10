# Avaliação das alternativas (passo 1) — limitada

A rede do ambiente bloqueou opencode.ai, openalternative.co e github.com; só houve buscas.
- **sage:** não encontrei o projeto pelo nome; license/agentes NÃO confirmados.
- **OpenCode:** fontes de terceiros indicam provedor openai-compatible (llama-server), bloco
  `permission` (ask/deny) e licença MIT em anomalyco/opencode. Nada sobre sandbox nem `opencode run`.
  Modelo local precisa de tool-calling e contexto grande (o 1º turno passa de 7.500 tokens).
- **Outros orquestradores citados:** opentree (Go, MIT), ORCH, Composio agent-orchestrator,
  Vibe Kanban, Crystal, Orchestra. Licenças/estado a confirmar.

**Decisão provisória:** manter `codice/orquestra` (tem sandbox bwrap, escopo por pasta, testes).
Revisitar com acesso aos repositórios. OpenCode entra no perfil `completo` só depois de testado.
