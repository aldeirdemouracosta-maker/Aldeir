# Importador de ZIP — portão de segurança

Implementa a primeira metade do fluxo obrigatório do modo "Terminar
projeto" descrito em `ARQUITETURA_FABRICA_LOCAL_IA.md` (seção 3):

```
ZIP
 ↓
EXTRAÇÃO SEGURA        ← inspecionar_zip.py: extrair_seguro()
 ↓
LEITURA ESTÁTICA       ← inspecionar_zip.py: montar_inventario()
 ↓
INVENTÁRIO             ← inspecionar_zip.py: montar_inventario()
 ↓
SCAN                   ← inspecionar_zip.py: escanear_padroes_suspeitos()
 ↓
SNAPSHOT               ← inspecionar_zip.py: gerar_snapshot()
 ↓
SANDBOX                ← fora deste módulo, ver "Limite deliberado" abaixo
 ↓
só então BUILD/TEST
```

Nenhum código do projeto recebido é executado por este módulo. Ele só
lê, classifica e copia arquivos — a decisão de rodar build/test fica
para uma camada de sandbox separada, que só deve receber luz verde
quando `pode_auto_prosseguir` for `true`.

## O que cada etapa cobre

- **Extração segura** (`extrair_seguro`): rejeita zip-slip (`../`,
  caminhos absolutos), links simbólicos, e zip bombs (limite de
  tamanho total descomprimido e de razão de compressão por arquivo).
  Nada é gravado fora do diretório de destino — testado com um ZIP
  malicioso real (`../../../../tmp/evil_escaped.txt`), que é
  rejeitado antes de qualquer escrita em disco.
- **Inventário** (`montar_inventario`): conta arquivos, soma bytes,
  identifica manifestos de dependência (`requirements.txt`,
  `package.json`, `pyproject.toml`, `go.mod`, etc.) e sinaliza nomes/
  extensões associados a instalação ou execução (`install.sh`,
  `setup.py`, `Makefile`, `.exe`, `.dll`, `.ps1`, `.bat`, ...).
- **Scan** (`escanear_padroes_suspeitos`): heurística de texto —
  `os.system`, `subprocess(..., shell=True)`, `eval`/`exec`, pipe de
  `curl`/`wget` para shell, `rm -rf /`, payloads em base64. Não é um
  antivírus; existe para decidir se o projeto precisa de revisão
  humana antes do modo automático.
- **Snapshot** (`gerar_snapshot`): manifesto com caminho, tamanho e
  SHA-256 de cada arquivo extraído. É o checkpoint anterior a qualquer
  alteração de um agente — a base para diff e rollback exatos depois.

## Uso

```bash
python3 inspecionar_zip.py caminho/para/projeto.zip
```

Saída: um JSON (`RelatorioProjeto`) com o inventário, os achados de
risco e a flag `pode_auto_prosseguir`. `--saida DIR` escolhe onde
extrair e gravar o snapshot (padrão: `<zip>_analise/` ao lado do ZIP).

Como biblioteca:

```python
from importador_zip.inspecionar_zip import analisar_projeto, ZipInseguroError
from pathlib import Path

try:
    relatorio = analisar_projeto(Path("projeto.zip"), Path("/tmp/analise"))
except ZipInseguroError as erro:
    # ZIP rejeitado antes de qualquer extração — nunca chega a tocar disco.
    ...

if relatorio.pode_auto_prosseguir:
    # ok para o executor de sandbox prosseguir para build/test
    ...
else:
    # relatorio.arquivos_de_risco / padroes_suspeitos explicam o motivo;
    # exigir confirmação humana antes de continuar.
    ...
```

## Isolamento de execução: `sandbox_execucao/`

Este módulo não roda build nem testes do projeto recebido — só analisa
estaticamente. A execução isolada (build/test de verdade, via
`bubblewrap`) é o módulo irmão `sandbox_execucao/`, que consome o
`RelatorioProjeto` gerado aqui (principalmente `pode_auto_prosseguir`
e `diretorio_extraido`) como portão de entrada — ver
`sandbox_execucao/README.md`.
