# Busca semântica de código local (nome provisório — batizamos depois)

Ferramenta opcional do orquestrador: dado um projeto e uma pergunta em
linguagem natural, devolve os trechos de código mais relevantes
(arquivo + linhas), sem o agente precisar ler arquivo por arquivo pra
achar onde procurar.

## Como funciona

Sobe um `llama-server` temporário com um modelo de **embeddings**
pequeno em modo `--embeddings` (recomendado:
[CodeRankEmbed](https://huggingface.co/nomic-ai/CodeRankEmbed) —
137M parâmetros, MIT, treinado especificamente pra recuperação de
código, GGUF já disponível em
`awhiteside/CodeRankEmbed-Q8_0-GGUF`), indexa os arquivos de código do
projeto em pedaços de ~60 linhas, calcula a similaridade de cosseno
entre a pergunta e cada pedaço, devolve os `top_k` mais parecidos, e
desliga o servidor — mesmo padrão de "agente reduzido, sobe sob
demanda" usado em `visao_mockup/interpretar_mockup.py`.

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

- Chunking por linha, não por função/classe (Tree-sitter melhoraria
  isso, mas é dependência nova — fica pra depois).
- Sem suporte a busca por palavra-chave (BM25) — só semântica.
- Cache por projeto é um JSON simples, não um banco vetorial de
  verdade — adequado pra projetos pequenos/médios, não escala pra
  bases de código enormes.
