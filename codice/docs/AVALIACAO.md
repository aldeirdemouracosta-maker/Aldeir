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

## Fábrica Local de IA para Linux (recebida em 10/10/2026)
Pacote `fabrica-linux-ubuntu` (71 arquivos, checksum conferido, 0 divergências) em `fabrica-linux/`.
App Qt/PySide6 + proxy corrigido (39 testes passam aqui). Proxy diverge do `fabrica-correcoes/`
anterior (SHA-256 diferente; o do pacote é o mais novo): a ISO usa o do pacote.
Pendências do próprio pacote: sem teste em Ubuntu real, sem LICENSE (não publicar/distribuir
antes de definir), bubblewrap pode ser barrado por user namespaces/AppArmor.
Não testado por mim: a interface Qt (PySide6 não instalado aqui) nem a instalação na ISO.
Perfil `completo` precisa de área gráfica: use `DESKTOP=minimal PERFIL=completo`.
