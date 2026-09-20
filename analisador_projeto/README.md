# Analisador de completude — "o que existe / o que falta"

Implementa a tela "Projeto detectado" do modo "Terminar projeto"
(`ARQUITETURA_FABRICA_LOCAL_IA.md`, seção 2):

```
Projeto detectado
────────────────────────
Python
3 arquivos de código
1 TODO
3 funções incompletas
1 módulo-esqueleto
1 teste falhando de 2

Estado estimado: 24%
```

Roda **antes** de qualquer agente tocar no projeto — é o insumo que o
`orquestrador` (ou um humano) usa para decidir o que fazer, não uma
ferramenta de correção.

## O que é detectado

- **Linguagem principal**: por contagem de extensão de arquivo.
- **TODOs/FIXMEs/XXX**: varredura de comentários `#`/`//`.
- **Funções incompletas (Python)**: via `ast`, não regex — uma função
  cujo corpo é só `pass`, só `...`, só `raise NotImplementedError` ou
  só docstring conta como incompleta. Uma função com qualquer lógica
  real, mesmo trivial, não é marcada.
- **Módulos-esqueleto (Python)**: arquivos `.py` com poucas linhas de
  código de verdade (excluindo `__init__.py`).
- **Testes**: se detectar `pytest.ini`/`pyproject.toml`/arquivos
  `test_*.py` ou um script `test` em `package.json`, roda a suíte via
  `sandbox_execucao` (isolado, sem rede) e conta passou/falhou.

Detecção de função/módulo incompleto só está implementada para Python
por enquanto — para outras linguagens, o relatório inclui essa
limitação explicitamente em `observacoes` em vez de fingir cobertura
que não existe.

## Uso

```bash
python3 -m analisador_projeto.analisar_completude /caminho/do/projeto
```

`--sem-testes` pula a tentativa de rodar a suíte de testes do projeto
(útil para diagnóstico rápido ou quando não se quer aguardar um
build/test longo).

## Integração com o portão de segurança

Testes só rodam automaticamente se o chamador não passar um
`relatorio_seguranca` do `importador_zip`, ou se esse relatório disser
`pode_auto_prosseguir: true`. Um projeto reprovado no scan de segurança
tem seus testes pulados, com o motivo registrado em `observacoes` —
nunca executa código não revisado só para calcular uma porcentagem:

```python
from pathlib import Path
from dataclasses import asdict
from importador_zip.inspecionar_zip import analisar_projeto
from analisador_projeto.analisar_completude import analisar_completude

relatorio_seguranca = asdict(analisar_projeto(Path("projeto.zip"), Path("/tmp/analise")))
relatorio_completude = analisar_completude(
    Path(relatorio_seguranca["diretorio_extraido"]),
    relatorio_seguranca=relatorio_seguranca,
)
print(relatorio_completude.estado_estimado_percentual)
```

## Sobre o "estado estimado"

É uma heurística (pontuação de 0 a 100 partindo de 100 e descontando
por função incompleta, módulo-esqueleto, TODO e proporção de testes
falhando), documentada e determinística — não uma métrica de
qualidade de software validada. Serve para dar uma primeira noção de
prioridade; cada achado que a compõe é reportado separadamente para
quem quiser julgar por conta própria.
