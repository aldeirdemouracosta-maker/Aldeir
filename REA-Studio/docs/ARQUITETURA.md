# Arquitetura

```
ReaStudio.App (WPF, MVVM, net10.0-windows)
  └─ ReaStudio.Core (net10.0, sem UI, testável)
       Ai/         IAiProvider, OpenAI API, Anthropic API, sonda CLI (Codex/Claude Code), Ollama
       Fallback/   ProviderRouter (Manual/Automático/Somente local), FallbackPolicy, CheckpointStore, ToolAuthorizer
       Security/   DPAPI (CurrentUser), StructuredLog JSONL com redação
       Mcp/        McpClient (JSON-RPC stdio), leitor somente-leitura do registro MCP
       Binary/     detecção PE/ELF pelo cabeçalho
       Diagnostics/ REA(registro) / Ghidra / Ollama
tests/ReaStudio.Tests (xunit; provedores e HTTP simulados)
```

## Fluxo de troca automática
1. Provedor escolhido executa. 2. Erro classificado (`QuotaExceeded` = HTTP 429, `Temporary` = 5xx/529/408,
`Network`, `Authentication` = 401/403, `Policy`). 3. Se a política permitir: **checkpoint salvo primeiro**
(mensagens, operações concluídas, caminhos + SHA-256 das evidências); se o checkpoint falhar, a troca é cancelada.
4. Ollama retoma com a lista de operações já executadas ("não repetir"). 5. `MutationsNeedConfirmation = true`:
`ToolAuthorizer` exige confirmação do usuário para toda operação que altere arquivos; ferramentas desconhecidas
contam como "altera"; operação já executada nunca é repetida.

Política padrão: troca em quota/temporário/rede. Autenticação só se `OnRecoverableAuth` for ligado explicitamente.
Política de segurança e erro desconhecido nunca trocam. Modo Manual nunca troca. Somente local nunca chama provedor externo.

## Limitações reais dos provedores
- Detecta-se apenas o que a integração **expõe** (ex.: HTTP 429). Os limites internos de assinatura ChatGPT/Claude
  **não são legíveis**; não há detecção de "créditos restantes" (não simulada).
- Assinatura ChatGPT não equivale a créditos da API OpenAI; são cobranças separadas.
- Nenhum token é extraído de apps ou navegadores. Codex/Claude Code mantêm sua autenticação oficial.
- Trocar de modelo **não preserva o raciocínio interno** do anterior; só o checkpoint (mensagens, tarefas, evidências).
- Modelos Ollama: suporte a ferramentas é só o que o Ollama *declara* (`capabilities`); não é garantia de que MCP funcione.
  Memória exibida é **estimativa** (tamanho em disco × 1,2).

## Não implementado nesta fase
Execução via Codex CLI e Claude Code CLI (apenas detecção no PATH); uso do `McpClient` contra o REA real e teste
das ferramentas REA; integração Ghidra (apenas detecção da instalação); painel de funções/pseudocódigo;
tela de cadastro de chaves de API (o `DpapiCredentialStore` existe, sem UI); gerenciador de projetos; execução de
ferramentas pelo chat; consoles (PS1, Saturn, SNES, Mega Drive...); persistência de configurações do usuário;
retomada de tarefa a partir do checkpoint pela UI (o `CheckpointStore.Load/Verify` existe e é testado).
