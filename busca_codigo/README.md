# Busca semântica de código local (nome provisório — batizamos depois)

Ferramenta opcional do orquestrador: dado um projeto e uma pergunta em
linguagem natural, devolve os trechos de código mais relevantes
(arquivo + linhas), sem o agente precisar ler arquivo por arquivo pra
achar onde procurar.

## Como funciona

Busca **híbrida**: combina duas pontuações por pedaço de código,
ponderadas por `peso_bm25` (padrão 0.4):

- **Semântica** — sobe um `llama-server` temporário com um modelo de
  **embeddings** pequeno em modo `--embeddings` (recomendado:
  [CodeRankEmbed](https://huggingface.co/nomic-ai/CodeRankEmbed) —
  137M parâmetros, MIT, treinado especificamente pra recuperação de
  código, GGUF já disponível em `awhiteside/CodeRankEmbed-Q8_0-GGUF`)
  e calcula similaridade de cosseno entre a pergunta e cada pedaço.
- **Palavra-chave** — BM25 clássico, implementado direto em Python
  (sem dependência nova, o corpus é sempre pequeno). Importante pra
  quando a pergunta cita um nome exato de função/variável, que
  embeddings sozinhos às vezes deixam passar. O tokenizador separa
  `snake_case` e `camelCase` em sub-palavras — sem isso,
  `validar_login` nunca bateria com a pergunta "validar login".

Desliga o servidor de embeddings no final — mesmo padrão de "agente
reduzido, sobe sob demanda" usado em
`visao_mockup/interpretar_mockup.py`.

## Divisão em pedaços (chunking)

Arquivos **Python** são cortados por função/classe de nível superior
usando o módulo `ast` (mesmo já usado em `analisador_projeto`) — pedaço
= uma função inteira ou uma classe inteira, não uma janela de linhas
arbitrária. Cai pro chunking por linha (com sobreposição) se o arquivo
tiver erro de sintaxe ou não tiver nenhuma função/classe de nível
superior.

Outras linguagens ainda usam só o chunking por linha — um Tree-sitter
de verdade (chunking estrutural pra JS/Java/C/etc.) ficaria melhor,
mas exigiria uma dependência nativa nova por linguagem; adiado até
haver necessidade real comprovada.

Não depende de nenhuma ferramenta externa (Go, Docker, servidor à
parte): é só Python + o mesmo `llama.cpp` que já roda o modelo de
código/visão, com um binário GGUF diferente.

## Por que não usamos o `code-index`/`cix` de terceiros

Existe um projeto pronto (`dvcdsys/code-index`, MIT) que faz busca
híbrida (BM25 + embeddings) com Tree-sitter — mas descobrimos, ao
pesquisar antes de implementar, que o CLI dele (`cix search`) depende
de um servidor Go rodando por trás (`cix-server`, com banco próprio),
não é standalone. Isso é peso demais pra o que precisamos aqui:
preferimos construir uma versão pequena e específica em Python,
consistente com o resto do projeto, mesmo abrindo mão do Tree-sitter e
do BM25 por enquanto (chunking hoje é por linha, não por
função/classe).

## Cache de indexação

Fica em `<raiz_projeto>/.fabrica_indice_busca.json` — só reprocessa
(reembute) arquivos novos ou modificados desde a última indexação
(comparando mtime + tamanho), reaproveitando os pedaços já calculados
dos que não mudaram.

## Uso

```bash
python3 -m busca_codigo.buscar_codigo \
    --binario ./llama.cpp/build/bin/llama-server \
    --modelo ~/modelos/coderankembed-q8_0.gguf \
    --projeto ~/meu-projeto \
    --pergunta "onde fica a validação de login"
```

Na interface, o botão **"Configurar busca semântica…"** (ao lado de
"Executar"/"Parar") pede o executável `llama-server` e o GGUF do
modelo de embeddings uma vez (guardado em `QSettings`) — sem isso
configurado, "Executar" funciona normalmente, só sem a ferramenta
`buscar_codigo` disponível pro agente.

## Limites atuais

- Chunking estrutural (`ast`) só pra Python — outras linguagens ainda
  usam janela de linhas (ver acima).
- Cache por projeto é um JSON simples, não um banco vetorial de
  verdade — adequado pra projetos pequenos/médios, não escala pra
  bases de código enormes.
- BM25 recalcula o índice inteiro a cada busca (custo baixo pro
  tamanho de projeto que esperamos aqui, mas não incremental como o
  cache de embeddings).
