# Orquestrador — loop de agente sobre um projeto local

Liga as três peças já construídas:

```
motor_ia/            → escolhe o endpoint do modelo (OpenAI-compatible)
importador_zip/       → (opcional) valida e extrai um ZIP recebido
sandbox_execucao/      → executa comandos com isolamento
        │
        ▼
orquestrador/orquestrador.py
```

O modelo recebe uma instrução em linguagem natural e um conjunto
pequeno de ferramentas. A cada rodada ele pode chamar uma ferramenta;
o orquestrador executa e devolve o resultado como mensagem `tool`,
repetindo até o modelo chamar `finalizar` ou estourar
`max_iteracoes`.

## Ferramentas expostas ao modelo

- `ler_arquivo(caminho)` — leitura confinada à raiz do projeto.
- `escrever_arquivo(caminho, conteudo)` — escrita confinada à raiz do projeto.
- `listar_arquivos(caminho)` — lista o conteúdo direto (não recursivo) de
  uma pasta do projeto (raiz se `caminho` vazio/omitido). Sempre
  disponível (diferente de `buscar_codigo`, não depende de nada
  configurado). Existe como alternativa nativa a
  `executar_comando(["ls", ...])`: não passa pelo sandbox (sem
  subprocesso, mais barato) e devolve uma lista estruturada
  `[{"nome": ..., "tipo": "arquivo"|"pasta"}, ...]` em vez de texto
  solto pro modelo interpretar.
- `executar_comando(comando)` — roda via `sandbox_execucao` (sem rede, timeout).
- `buscar_codigo(pergunta)` — **opcional**: busca semântica no código via
  `busca_codigo/buscar_codigo.py` (embeddings, ver README daquele
  módulo). Só entra na lista de ferramentas anunciada ao modelo
  (`montar_ferramentas`) se `caminho_binario_busca`/`caminho_modelo_busca`
  forem passados ao `Orquestrador` — sem isso configurado, a ferramenta
  simplesmente não existe pro modelo, em vez de existir e sempre falhar.
- `delegar_tarefa(instrucao, contexto)` — **opcional**, mesmo padrão de
  `buscar_codigo` (só existe se `caminho_binario_microagente`/
  `caminho_modelo_microagente` forem passados). Delega uma sub-tarefa
  pequena e autocontida a um modelo dedicado, menor e mais rápido (ex.:
  Qwen2.5-Coder-0.5B) — sem acesso a ferramentas, sem histórico da
  conversa, só a instrução e um contexto opcional. Ver
  `microagentes/README.md`.
- `analisar_erro(erro, contexto)` — **opcional**, mesmo padrão (só
  existe se `caminho_binario_analise`/`caminho_modelo_analise` forem
  passados). Delega o diagnóstico de um erro a um modelo de
  **raciocínio** dedicado (ex.: MiniCPM5-1B) — papel oposto ao de
  `delegar_tarefa`: mais lento de propósito, prioriza precisão sobre
  velocidade. Ver `microagentes/README.md`.
- `finalizar(resumo, sucesso)` — encerra o loop.

`ler_arquivo`/`escrever_arquivo` usam a mesma defesa contra path
traversal do `importador_zip`: qualquer caminho que resolva para fora
da raiz do projeto é rejeitado (`CaminhoForaDoProjetoError`) e o
modelo recebe uma mensagem de erro em vez de um caminho para escapar
do projeto.

`PROMPT_SISTEMA` e as descrições das ferramentas avisam o modelo que a
sandbox não tem rede e não mantém estado entre chamadas — mas um
modelo pequeno pode ignorar isso e insistir em `pip install`/`git
clone`/etc. mesmo assim (visto na prática). Por isso `executar_comando`
também acrescenta um campo `"aviso"` no próprio resultado JSON sempre
que o comando começa com um binário de `COMANDOS_DE_REDE` (`pip`,
`curl`, `git`, `npm`, `apt`...) e falha — reforço no ponto exato da
falha, não só no início da conversa.

Note também: `bwrap: execvp <comando>: No such file or directory`
(binário não instalado) não é falha de infraestrutura do bwrap — o
sandbox montou certo, só o comando pedido não existe. `sandbox_execucao`
distingue isso de uma falha real de `bwrap` (que levanta
`SandboxIndisponivelError`) e devolve como `ResultadoExecucao` normal,
com código de saída != 0.

## Tool calling: nativo com fallback de texto

`chamar_llm` pede `tool_choice: "required"` ao motor, mas nem todo
motor/modelo obedece isso de verdade — testado numa máquina real,
llama-server + Qwen2.5-Coder ignoravam esse parâmetro e devolviam a
chamada como JSON dentro de `message.content` (às vezes em bloco
markdown, às vezes com texto ao redor) em vez de `tool_calls`
estruturado. `extrair_chamada_de_texto` varre o conteúdo e extrai o
primeiro objeto `{"name": ..., "arguments": {...}}` válido nesses
casos, então o orquestrador funciona independente de o motor
implementar tool calling OpenAI-compatible corretamente — ver
`TESTE_LOCAL.md` para os detalhes da investigação.

## Uso

`orquestrador.py` importa `motor_ia` e `sandbox_execucao` (pacotes irmãos
na raiz do repositório), então precisa rodar como módulo — a partir da
raiz do repositório, não com o caminho direto do arquivo:

```bash
python3 -m orquestrador.orquestrador /caminho/do/projeto "adicione um teste para a função X"
```

(`python3 orquestrador/orquestrador.py ...` falha com
`ModuleNotFoundError: No module named 'motor_ia'` — sem o `-m`, o
Python só coloca o diretório do próprio arquivo no import path, não a
raiz do repositório.)

Com `--diagnostico`, o `analisador_projeto` roda primeiro e o agente já
começa sabendo o que falta (TODOs, funções incompletas, testes
falhando), em vez de descobrir por tentativa e erro:

```bash
python3 -m orquestrador.orquestrador --diagnostico /caminho/do/projeto "termine a implementação pendente"
```

Como biblioteca:

```python
from pathlib import Path
from orquestrador.orquestrador import Orquestrador, MotorIndisponivelError

try:
    resultado = Orquestrador(Path("/caminho/do/projeto")).rodar(
        "corrija o teste que está falhando em test_app.py"
    )
except MotorIndisponivelError:
    # nenhum motor de IA respondendo — ver motor_ia/README.md
    ...

print(resultado)  # {"resumo": "...", "sucesso": true}
```

Combinado com o portão de ZIP:

```python
from dataclasses import asdict
from importador_zip.inspecionar_zip import analisar_projeto

relatorio = asdict(analisar_projeto(Path("projeto.zip"), Path("/tmp/analise")))
if not relatorio["pode_auto_prosseguir"]:
    raise SystemExit("projeto sinalizado como risco — revisão humana necessária")

Orquestrador(Path(relatorio["diretorio_extraido"])).rodar("termine a implementação pendente")
```

## Como foi testado (sem um motor de IA real disponível)

Este ambiente de desenvolvimento não tem `llama.cpp`/Ollama/LM Studio
rodando, então o loop foi validado com um servidor HTTP falso
compatível com a API OpenAI (script de teste, fora do repositório)
que devolve uma sequência fixa de `tool_calls`. Isso comprovou, de
ponta a ponta e com execução real (não simulada):

1. `escrever_arquivo` grava de verdade dentro da raiz do projeto.
2. `executar_comando` roda de verdade dentro do `sandbox_execucao`
   (bubblewrap) e o resultado volta correto para o loop.
3. O loop encerra ao receber `finalizar`.
4. Tentativa de `escrever_arquivo`/`ler_arquivo` fora da raiz do
   projeto (`../../etc/passwd_falso`, `/etc/passwd`) é bloqueada sem
   exceção não tratada — o modelo recebe um erro, nada vaza.
5. Sem `finalizar`, o loop estoura `max_iteracoes` e levanta
   `LimiteDeIteracoesError` em vez de rodar para sempre.
6. Sem nenhum motor de IA respondendo (`motor_ia` real, sem mock),
   `rodar()` levanta `MotorIndisponivelError` imediatamente — nunca
   trava esperando um endpoint que não existe.

O que ainda não foi testado, por depender de hardware real: o
comportamento de um modelo de verdade (qualidade das decisões,
prompt engineering do `PROMPT_SISTEMA`, ajuste fino do formato de
`tool_calls` para cada motor específico — LM Studio, Ollama e
llama.cpp podem ter pequenas diferenças na resposta de function
calling que só aparecem na integração real).

## Limites atuais (deliberados, não descuido)

- **Um agente, não dez.** A arquitetura descrita em
  `ARQUITETURA_FABRICA_LOCAL_IA.md` prevê papéis especializados
  (Arquiteto, Debugger, Test Engineer, Security Reviewer...). Este
  módulo implementa um agente genérico único porque dividir em dez
  papéis sem lógica realmente distinta entre eles seria andaime vazio.
  Quando houver comportamento que justifique um papel separado (ex.:
  um Security Reviewer com sua própria varredura, não só um prompt
  diferente), ele entra como próxima peça.
- **Sem paralelismo.** Uma instrução por vez, um projeto por vez.
- **Sem memória entre execuções.** Cada `rodar()` começa do zero; não
  há histórico persistido entre chamadas.
