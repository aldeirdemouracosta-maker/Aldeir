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
| 3 | Loop `write_file → run_command → write_file…` | Para quando a mesma ação, com o mesmo resultado, se repete 2 vezes, ou passa de 30 ações num pedido |
| 4 | Termina com "0 tokens" e nenhuma mensagem | Mantém a conexão viva enquanto o modelo carrega e mostra o erro do Ollama na tela |

Só usa a biblioteca padrão do Python 3.8+. Não precisa de `pip install`.

## Instalar no Windows 10/11

Não precisa de administrador. Precisa do Python (python.org, marcando "Add python.exe to PATH").

1. Ligue o servidor de IA: **LM Studio** (aba Developer, porta 1234; com a RX 580 use o
   runtime Vulkan) ou **Ollama**.
2. Dê **dois cliques em `instalar-windows.cmd`**.

O instalador:

- detecta sozinho o LM Studio (porta 1234) ou o Ollama (porta 11434) e o modelo qwen3 carregado;
- copia o proxy para `%LOCALAPPDATA%\fabrica-correcoes`;
- liga o proxy agora e cria um atalho na pasta Inicializar, para ele subir com o Windows;
- **Fábrica App com janela** (`FabricaApp.exe`): troca o endereço da IA local no
  `configuracoes.json` do aplicativo para o proxy, guardando uma cópia
  `configuracoes.json.antes-do-proxy`; o proxy repassa para o servidor que o aplicativo usava;
- **Fábrica de terminal** (`fabrica.exe`): cria o comando `fabrica-segura` (abra um terminal **novo** depois).

Opções, pelo PowerShell:

```powershell
.\instalar-windows.ps1 -Servidor http://127.0.0.1:1234 -Modelo qwen/qwen3-8b -SemPensar
```

Uso:

```powershell
cd C:\caminho\do\projeto
fabrica-segura
fabrica-segura exec 'Crie calc.py com somar e dividir' --auto
Get-Content $env:LOCALAPPDATA\fabrica-correcoes\proxy.log -Wait     # ver as correções
```

No Windows PowerShell 5.1, evite aspas duplas dentro do pedido; prefira aspas simples.

Para remover: dois cliques em `desinstalar-windows.cmd` (devolve também a configuração original do aplicativo).

## Instalar no Linux (sudo)

```bash
sudo bash instalar.sh
```

Para opções do serviço, passe variáveis antes do comando:

```bash
sudo PROXY_OPCOES="--sem-pensar" bash instalar.sh          # qwen3 sem raciocínio (sem GPU)
sudo OLLAMA_URL=http://127.0.0.1:8080 bash instalar.sh     # usar llama.cpp com Vulkan
```

Isso instala:

- o programa em `/usr/local/lib/fabrica-correcoes/`;
- o serviço `fabrica-proxy`, que inicia sozinho com o Linux (porta 11435);
- o comando `fabrica-segura`, que é a Fábrica já usando o proxy e o `qwen3:8b`.

```bash
cd ~/meu-projeto
fabrica-segura                                   # conversa
fabrica-segura exec 'Crie ...' --auto            # não interativo
FABRICA_MODELO=qwen2.5:7b fabrica-segura         # outro modelo
journalctl -u fabrica-proxy -f                   # ver as correções ao vivo
systemctl status fabrica-proxy                   # estado do serviço
sudo bash /usr/local/lib/fabrica-correcoes/desinstalar.sh   # remover
```

O comando `fabrica` original continua igual. Com `--nuvem` ou `--claude`, o
`fabrica-segura` não passa pelo proxy.

## Usar sem instalar (para testar)

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
--sem-pensar             qwen3: desliga o raciocínio (/no_think); bem mais rápido sem GPU
```

## Testes

```bash
python3 -m unittest -v test_fabrica_proxy
```

Usam um servidor falso que imita o Ollama; não precisam de modelo nem de GPU.

## Limitações

- A correção 2 só age quando o pedido do usuário é de ação (crie, altere, rode...) e
  a resposta afirma "criado", "salvo", "rodado", "✓" junto de um nome de arquivo.
  Uma resposta mentirosa escrita de outro jeito pode passar.
- A correção 1 ignora JSON de ferramenta no meio de um texto longo (mais de 300
  caracteres), para não executar exemplos que aparecem numa explicação.
- A proteção contra loop considera loop só a mesma ação, com os mesmos argumentos,
  que já deu o mesmo resultado 2 vezes. Rodar os testes de novo depois de mudar o
  código continua permitido.
- Com o proxy, a resposta aparece de uma vez no fim, em vez de ir surgindo aos poucos.
- Se a própria Fábrica tiver um tempo limite curto no modo sem streaming, o sinal
  de vida não ajuda; nesse caso o erro aparece no log do proxy.
