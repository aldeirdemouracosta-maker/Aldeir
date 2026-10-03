# Correções para a Fábrica App — terminal 3.4.3

O código-fonte da Fábrica não vem no pacote (só o executável), então as correções
ficam num **proxy** entre a Fábrica e o Ollama:

```
Fábrica ──► fabrica_proxy.py (porta 11435) ──► Ollama (porta 11434)
```

## O que ele corrige

| # | Defeito observado | O que o proxy faz |
|---|---|---|
| 1 | `qwen2.5-coder` manda a ferramenta como texto JSON e às vezes nada é executado | Converte o JSON do texto em `tool_call` de verdade |
| 2 | A IA diz "✓ arquivo criado" sem ter chamado nenhuma ferramenta | Cobra a IA até 2 vezes; se ela insistir, mostra um aviso `⚠️ [proxy]` |
| 3 | Loop `write_file → run_command → write_file…` | Para quando a mesma ação idêntica se repete 2 vezes ou passa de 30 ações num pedido |
| 4 | Termina com "0 tokens" e nenhuma mensagem | Mantém a conexão viva enquanto o modelo carrega e mostra o erro do Ollama na tela |

Só usa a biblioteca padrão do Python 3.8+. Não precisa de `pip install`.

## Como usar

Terminal 1, deixe o proxy rodando:

```bash
python3 fabrica_proxy.py --log ~/fabrica-proxy.log
```

Terminal 2, use a Fábrica apontando para o proxy:

```bash
fabrica --url http://127.0.0.1:11435/v1 -m qwen3:8b
# ou não interativo:
fabrica exec 'Crie calc.py ...' --url http://127.0.0.1:11435/v1 -m qwen3:8b --auto
```

O terminal 1 mostra cada correção aplicada (`correção 1`, `correção 2`...).

## Opções

```
--porta 11435            porta do proxy
--ollama URL             endereço do Ollama (padrão http://127.0.0.1:11434)
--max-repeticoes 2       quantas vezes a mesma ação idêntica é permitida
--max-etapas 30          máximo de ações por pedido
--log ARQUIVO            grava o registro das correções
```

## Limitações

- A correção 2 reconhece afirmações como "criado", "salvo", "rodado", "✓" junto de
  um nome de arquivo. Uma resposta mentirosa escrita de outro jeito pode passar.
- Com o proxy, a resposta aparece de uma vez no fim, em vez de ir surgindo aos poucos.
- Se a própria Fábrica tiver um tempo limite curto no modo sem streaming, o sinal
  de vida não ajuda; nesse caso o erro aparece no log do proxy.
