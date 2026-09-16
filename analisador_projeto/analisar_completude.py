#!/usr/bin/env python3
"""Diagnóstico de completude de um projeto — a tela "Projeto detectado"
do modo "Terminar projeto" descrito em ARQUITETURA_FABRICA_LOCAL_IA.md
(seção 2).

Responde "o que existe / o que falta" antes de qualquer agente tocar
no código: linguagem principal, TODOs, funções incompletas (Python,
via `ast` — não regex), módulos-esqueleto, e opcionalmente a
contagem de testes passando/falhando (reaproveitando o portão de
`importador_zip` e a execução isolada de `sandbox_execucao`).

O "estado estimado" é uma heurística para orientar o agente e o
usuário, não uma métrica de engenharia de software validada — cada
achado que a compõe também é reportado individualmente para quem
quiser julgar por si.

Uso:
    python3 analisar_completude.py <diretorio_do_projeto>
"""

import argparse
import ast
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

EXTENSAO_PARA_LINGUAGEM = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".jsx": "JavaScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".kt": "Kotlin",
    ".go": "Go",
    ".rs": "Rust",
    ".c": "C",
    ".cpp": "C++",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".dart": "Dart",
}

PADRAO_TODO = re.compile(rb"#.*\b(TODO|FIXME|XXX)\b|//.*\b(TODO|FIXME|XXX)\b", re.IGNORECASE)

LIMITE_LINHAS_MODULO_STUB = 3  # linhas de código (sem contar comentários/em branco)


@dataclass
class Achado:
    arquivo: str
    linha: int
    detalhe: str


@dataclass
class RelatorioTestes:
    comando: list
    total: Optional[int]
    passaram: Optional[int]
    falharam: Optional[int]
    saida_bruta: str


@dataclass
class RelatorioCompletude:
    linguagem_principal: str
    total_arquivos_codigo: int
    todos_encontrados: list = field(default_factory=list)
    funcoes_incompletas: list = field(default_factory=list)
    modulos_stub: list = field(default_factory=list)
    testes: Optional[dict] = None
    estado_estimado_percentual: int = 0
    observacoes: list = field(default_factory=list)


def detectar_linguagem_principal(raiz: Path) -> str:
    contagem = {}
    for caminho in raiz.rglob("*"):
        if caminho.is_file():
            linguagem = EXTENSAO_PARA_LINGUAGEM.get(caminho.suffix.lower())
            if linguagem:
                contagem[linguagem] = contagem.get(linguagem, 0) + 1

    if not contagem:
        return "desconhecida"
    return max(contagem, key=contagem.get)


def _arquivos_de_codigo(raiz: Path):
    for caminho in raiz.rglob("*"):
        if caminho.is_file() and caminho.suffix.lower() in EXTENSAO_PARA_LINGUAGEM:
            yield caminho


def encontrar_todos(raiz: Path) -> list:
    achados = []
    for caminho in _arquivos_de_codigo(raiz):
        try:
            conteudo = caminho.read_bytes()
        except OSError:
            continue
        for numero, linha in enumerate(conteudo.splitlines(), start=1):
            if PADRAO_TODO.search(linha):
                achados.append(
                    Achado(
                        arquivo=str(caminho.relative_to(raiz)),
                        linha=numero,
                        detalhe=linha.decode("utf-8", errors="replace").strip()[:200],
                    )
                )
    return achados


def _corpo_e_trivial(nos_corpo: list) -> bool:
    """True se o corpo de uma função Python não faz nada de fato:
    só `pass`, só `...`, só `raise NotImplementedError(...)`, ou só
    docstring (com qualquer combinação de um desses três + docstring)."""
    relevantes = []
    for no in nos_corpo:
        if isinstance(no, ast.Expr) and isinstance(no.value, ast.Constant) and isinstance(no.value.value, str):
            continue  # docstring, não conta como implementação
        relevantes.append(no)

    if not relevantes:
        return True  # só tinha docstring (ou nada)

    if len(relevantes) != 1:
        return False

    no = relevantes[0]
    if isinstance(no, ast.Pass):
        return True
    if isinstance(no, ast.Expr) and isinstance(no.value, ast.Constant) and no.value.value is Ellipsis:
        return True
    if isinstance(no, ast.Raise) and isinstance(no.exc, ast.Call):
        nome_excecao = getattr(no.exc.func, "id", None)
        if nome_excecao == "NotImplementedError":
            return True
    if isinstance(no, ast.Raise) and isinstance(no.exc, ast.Name) and no.exc.id == "NotImplementedError":
        return True

    return False


def encontrar_funcoes_incompletas_python(raiz: Path) -> list:
    achados = []
    for caminho in raiz.rglob("*.py"):
        try:
            arvore = ast.parse(caminho.read_text(errors="replace"))
        except (SyntaxError, OSError):
            continue

        for no in ast.walk(arvore):
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) and _corpo_e_trivial(no.body):
                achados.append(
                    Achado(
                        arquivo=str(caminho.relative_to(raiz)),
                        linha=no.lineno,
                        detalhe=f"função '{no.name}' sem implementação",
                    )
                )
    return achados


_PADRAO_DEFINICAO = re.compile(r"^\s*(def|class)\s")


def _e_arquivo_de_teste(caminho_relativo: Path) -> bool:
    return (
        caminho_relativo.name.startswith("test_")
        or caminho_relativo.name.endswith("_test.py")
        or "tests" in caminho_relativo.parts
        or "test" in caminho_relativo.parts
    )


def encontrar_modulos_stub(raiz: Path) -> list:
    """Um módulo é 'esqueleto' quando tem poucas linhas de código *e*
    não define nenhuma função/classe — ou seja, é só import/constante,
    sinal de que ainda não foi escrito. Um módulo curto mas com uma
    função completa não é esqueleto só por ser pequeno; arquivos de
    teste são ignorados aqui (brevidade é normal para eles)."""
    achados = []
    for caminho in raiz.rglob("*.py"):
        if caminho.name == "__init__.py":
            continue
        relativo = caminho.relative_to(raiz)
        if _e_arquivo_de_teste(relativo):
            continue
        try:
            linhas = caminho.read_text(errors="replace").splitlines()
        except OSError:
            continue
        linhas_de_codigo = [
            l for l in linhas if l.strip() and not l.strip().startswith("#") and not l.strip().startswith('"""')
        ]
        tem_definicao = any(_PADRAO_DEFINICAO.match(l) for l in linhas)
        if 0 < len(linhas_de_codigo) <= LIMITE_LINHAS_MODULO_STUB and not tem_definicao:
            achados.append(
                Achado(
                    arquivo=str(relativo),
                    linha=1,
                    detalhe=f"módulo com apenas {len(linhas_de_codigo)} linha(s) de código e nenhuma função/classe",
                )
            )
    return achados


def detectar_comando_de_teste(raiz: Path) -> Optional[list]:
    if (raiz / "pytest.ini").exists() or (raiz / "pyproject.toml").exists() or any(raiz.rglob("test_*.py")):
        return ["python3", "-m", "pytest", "--tb=no", "-q"]
    if (raiz / "package.json").exists():
        return ["npm", "test", "--", "--watchAll=false"]
    return None


def _parsear_resumo_pytest(saida: str) -> tuple:
    """Procura, na última linha de resumo do pytest, contagens de
    'passed'/'failed'/'error' — em qualquer ordem, já que o pytest lista
    'failed' antes de 'passed' quando há falhas (ex.: '1 failed, 1 passed
    in 0.01s')."""
    for linha in reversed(saida.strip().splitlines()):
        passou = re.search(r"(\d+) passed", linha)
        falhou = re.search(r"(\d+) failed", linha)
        erro = re.search(r"(\d+) error", linha)
        if passou or falhou or erro:
            passaram = int(passou.group(1)) if passou else 0
            falharam = (int(falhou.group(1)) if falhou else 0) + (int(erro.group(1)) if erro else 0)
            return passaram, falharam
    return None, None


def rodar_testes(raiz: Path, config_sandbox=None) -> Optional[RelatorioTestes]:
    comando = detectar_comando_de_teste(raiz)
    if comando is None:
        return None

    from sandbox_execucao.executar_sandbox import ConfiguracaoSandbox, executar_comando_sandbox

    config_sandbox = config_sandbox or ConfiguracaoSandbox(timeout_segundos=180)
    resultado = executar_comando_sandbox(raiz, comando, config_sandbox)
    saida = resultado.stdout + "\n" + resultado.stderr

    passaram, falharam = (None, None)
    if comando[:3] == ["python3", "-m", "pytest"]:
        passaram, falharam = _parsear_resumo_pytest(saida)

    total = None if passaram is None else passaram + falharam
    return RelatorioTestes(comando=comando, total=total, passaram=passaram, falharam=falharam, saida_bruta=saida[-4000:])


def estimar_percentual_completo(
    total_arquivos_codigo: int,
    n_funcoes_incompletas: int,
    n_modulos_stub: int,
    n_todos: int,
    testes: Optional[RelatorioTestes],
) -> int:
    """Heurística simples e explícita, não uma métrica cientificamente
    validada. Começa em 100 e desconta por sinal de trabalho pendente;
    cada termo é limitado para que um único fator não domine o placar.
    """
    pontuacao = 100.0

    if total_arquivos_codigo > 0:
        pontuacao -= min(40, (n_funcoes_incompletas / total_arquivos_codigo) * 100)
        pontuacao -= min(20, (n_modulos_stub / total_arquivos_codigo) * 100)
    pontuacao -= min(15, n_todos * 1.5)

    if testes is not None and testes.total:
        proporcao_falha = testes.falharam / testes.total
        pontuacao -= proporcao_falha * 30
    elif testes is None:
        pontuacao -= 5  # sem forma de verificar nada por teste automatizado

    return max(0, min(100, round(pontuacao)))


def analisar_completude(
    raiz: Path,
    relatorio_seguranca: Optional[dict] = None,
    rodar_testes_automaticos: bool = True,
    config_sandbox=None,
) -> RelatorioCompletude:
    observacoes = []

    linguagem = detectar_linguagem_principal(raiz)
    total_arquivos_codigo = sum(1 for _ in _arquivos_de_codigo(raiz))
    todos = encontrar_todos(raiz)

    funcoes_incompletas = []
    modulos_stub = []
    if linguagem == "Python":
        funcoes_incompletas = encontrar_funcoes_incompletas_python(raiz)
        modulos_stub = encontrar_modulos_stub(raiz)
    else:
        observacoes.append(
            f"detecção de função/módulo incompleto só está implementada para Python; "
            f"linguagem principal detectada foi {linguagem!r}"
        )

    testes = None
    pode_rodar_testes = relatorio_seguranca is None or relatorio_seguranca.get("pode_auto_prosseguir")
    if rodar_testes_automaticos and pode_rodar_testes:
        try:
            testes = rodar_testes(raiz, config_sandbox)
            if testes is None:
                observacoes.append("nenhum comando de teste reconhecido (pytest/npm) foi detectado")
        except Exception as erro:  # noqa: BLE001 — reportar qualquer falha de execução como observação, não interromper o diagnóstico
            observacoes.append(f"falha ao rodar testes automaticamente: {erro}")
    elif rodar_testes_automaticos and not pode_rodar_testes:
        observacoes.append(
            "testes não foram rodados: o relatório de segurança do importador_zip não liberou "
            "execução automática (pode_auto_prosseguir=False)"
        )

    estado = estimar_percentual_completo(
        total_arquivos_codigo,
        len(funcoes_incompletas),
        len(modulos_stub),
        len(todos),
        testes,
    )

    return RelatorioCompletude(
        linguagem_principal=linguagem,
        total_arquivos_codigo=total_arquivos_codigo,
        todos_encontrados=[asdict(a) for a in todos],
        funcoes_incompletas=[asdict(a) for a in funcoes_incompletas],
        modulos_stub=[asdict(a) for a in modulos_stub],
        testes=asdict(testes) if testes else None,
        estado_estimado_percentual=estado,
        observacoes=observacoes,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("diretorio_projeto", type=Path)
    parser.add_argument("--sem-testes", action="store_true", help="não tenta rodar a suíte de testes do projeto")
    args = parser.parse_args()

    relatorio = analisar_completude(args.diretorio_projeto, rodar_testes_automaticos=not args.sem_testes)
    print(json.dumps(asdict(relatorio), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
