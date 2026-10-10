# Fábrica Livre (rascunho)

Assistente de programação de terminal com IA local, em preparação. Ainda não está
decidido se o projeto parte do zero ou do código do Fábrica App (depende da licença
e de o código estar legível).

Por enquanto só existe o contrato entre as duas partes do programa:

- `fabrica_livre/contrato.py`: `Config`, `Evento`, `Acao`, o protocolo `Agente` e um
  `AgenteFalso` que produz eventos roteirizados, para desenvolver a interface sem IA.

Divisão prevista:

- **núcleo** (`nucleo.py`): conversa com o servidor compatível com OpenAI (Ollama,
  LM Studio ou o proxy de `../fabrica-correcoes`), executa as ferramentas e aplica as
  proteções contra loop e alucinação;
- **interface** (`interface.py`, `__main__.py`): só consome os `Evento`s e responde aos
  pedidos de aprovação.

Só biblioteca padrão, Python 3.10+.
