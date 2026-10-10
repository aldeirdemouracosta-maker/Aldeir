#!/usr/bin/env python3
"""Portao de seguranca para projetos recebidos em ZIP.

Implementa a primeira metade do fluxo obrigatorio antes de qualquer
build/test automatico:

    ZIP -> EXTRACAO SEGURA -> LEITURA ESTATICA -> INVENTARIO -> SCAN -> SNAPSHOT

A segunda metade (SANDBOX -> BUILD/TEST) exige isolamento em nivel de
SO (namespaces, seccomp, container) e fica fora deste modulo de
proposito: nao ha isolamento real possivel em Python puro, e fingir
que ha seria pior do que nao ter nada. O relatorio gerado aqui e o
contrato de entrada para esse executor de sandbox (ver `README.md`).

Uso:
    python3 inspecionar_zip.py caminho/para/projeto.zip
"""

import argparse
import hashlib
import json
import re
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

# Tamanho maximo total apos extracao (protege contra zip bomb).
LIMITE_TOTAL_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB
# Razao maxima descomprimido/comprimido por arquivo (protege contra zip bomb).
LIMITE_RAZAO_COMPRESSAO = 100
# Arquivos maiores que isso nao sao escaneados por padrao (texto/binario).
LIMITE_BYTES_PARA_SCAN = 5 * 1024 * 1024  # 5 MiB

NOMES_DE_RISCO = {
    "install.sh", "setup.py", "setup.sh", "makefile", "gnumakefile",
    "postinstall.js", "preinstall.js",
}
EXTENSOES_DE_RISCO = {
    ".exe", ".dll", ".so", ".dylib", ".ps1", ".bat", ".cmd", ".vbs", ".scr",
    ".msi", ".jar",
}
ARQUIVOS_DE_DEPENDENCIA = {
    "requirements.txt", "pyproject.toml", "pipfile", "package.json",
    "gemfile", "go.mod", "cargo.toml", "pom.xml", "build.gradle",
}

PADROES_SUSPEITOS = [
    (re.compile(rb"os\.system\s*\("), "os.system() chamando shell"),
    (re.compile(rb"subprocess\.\w+\([^)]*shell\s*=\s*True"), "subprocess com shell=True"),
    (re.compile(rb"\beval\s*\("), "uso de eval()"),
    (re.compile(rb"\bexec\s*\("), "uso de exec()"),
    (re.compile(rb"curl[^\n]{0,80}\|\s*(sh|bash)"), "pipe de curl para shell"),
    (re.compile(rb"wget[^\n]{0,80}\|\s*(sh|bash)"), "pipe de wget para shell"),
    (re.compile(rb"rm\s+-rf\s+/"), "rm -rf / (ou caminho perigoso)"),
    (re.compile(rb"base64\.b64decode\("), "payload codificado em base64"),
    (re.compile(rb"powershell[^\n]{0,80}-enc"), "PowerShell com payload codificado"),
]


@dataclass
class AchadoRisco:
    arquivo: str
    motivo: str


@dataclass
class RelatorioProjeto:
    origem_zip: str
    diretorio_extraido: str
    total_arquivos: int
    total_bytes: int
    dependencias_detectadas: list = field(default_factory=list)
    arquivos_de_risco: list = field(default_factory=list)
    padroes_suspeitos: list = field(default_factory=list)
    snapshot_path: Optional[str] = None
    pode_auto_prosseguir: bool = False


class ZipInseguroError(Exception):
    """Levantado quando o ZIP tenta escapar do diretorio de destino ou
    explodir em tamanho na extracao (zip slip / zip bomb)."""


def extrair_seguro(caminho_zip: Path, destino: Path) -> None:
    """Extrai um ZIP validando cada entrada antes de gravar no disco.

    Rejeita: caminhos absolutos, `..` (zip slip), links simbolicos, e
    qualquer coisa que ultrapasse os limites de tamanho/razao de
    compressao (zip bomb). Nada e escrito fora de `destino`.
    """
    destino = destino.resolve()
    destino.mkdir(parents=True, exist_ok=True)
    total_extraido = 0

    with zipfile.ZipFile(caminho_zip) as zf:
        for info in zf.infolist():
            nome = info.filename
            if nome.startswith("/") or ".." in Path(nome).parts:
                raise ZipInseguroError(f"entrada com caminho inseguro: {nome!r}")

            modo_link_simbolico = (info.external_attr >> 16) & 0o170000 == 0o120000
            if modo_link_simbolico:
                raise ZipInseguroError(f"entrada e um link simbolico: {nome!r}")

            destino_final = (destino / nome).resolve()
            if destino not in destino_final.parents and destino_final != destino:
                raise ZipInseguroError(f"entrada escapa do diretorio de destino: {nome!r}")

            if info.compress_size > 0:
                razao = info.file_size / max(info.compress_size, 1)
                if razao > LIMITE_RAZAO_COMPRESSAO:
                    raise ZipInseguroError(
                        f"razao de compressao suspeita em {nome!r}: {razao:.0f}x"
                    )

            total_extraido += info.file_size
            if total_extraido > LIMITE_TOTAL_BYTES:
                raise ZipInseguroError(
                    f"tamanho total descomprimido excede o limite de {LIMITE_TOTAL_BYTES} bytes"
                )

        zf.extractall(destino)


def montar_inventario(destino: Path) -> tuple:
    """Percorre a arvore extraida e classifica arquivos.

    Retorna (total_arquivos, total_bytes, dependencias, arquivos_de_risco).
    """
    total_arquivos = 0
    total_bytes = 0
    dependencias = set()
    riscos = []

    for caminho in destino.rglob("*"):
        if not caminho.is_file():
            continue
        total_arquivos += 1
        tamanho = caminho.stat().st_size
        total_bytes += tamanho

        nome_lower = caminho.name.lower()
        relativo = str(caminho.relative_to(destino))

        if nome_lower in ARQUIVOS_DE_DEPENDENCIA:
            dependencias.add(relativo)
        if nome_lower in NOMES_DE_RISCO:
            riscos.append(AchadoRisco(relativo, "nome de arquivo associado a instalacao/execucao"))
        if caminho.suffix.lower() in EXTENSOES_DE_RISCO:
            riscos.append(AchadoRisco(relativo, f"extensao de risco ({caminho.suffix})"))

    return total_arquivos, total_bytes, sorted(dependencias), riscos


def escanear_padroes_suspeitos(destino: Path) -> list:
    """Varre arquivos de texto em busca de padroes de comando perigosos.

    Heuristica, nao e um antivirus: falsos positivos e falsos negativos
    sao esperados. Serve para decidir se o projeto precisa de revisao
    humana antes do modo automatico.
    """
    achados = []
    for caminho in destino.rglob("*"):
        if not caminho.is_file():
            continue
        if caminho.stat().st_size > LIMITE_BYTES_PARA_SCAN:
            continue
        try:
            conteudo = caminho.read_bytes()
        except OSError:
            continue
        if b"\x00" in conteudo[:1024]:
            continue  # provavelmente binario, pula

        relativo = str(caminho.relative_to(destino))
        for padrao, motivo in PADROES_SUSPEITOS:
            if padrao.search(conteudo):
                achados.append(AchadoRisco(relativo, motivo))

    return achados


def gerar_snapshot(destino: Path, saida: Path) -> Path:
    """Grava um manifesto (caminho, tamanho, sha256) de cada arquivo.

    Esse manifesto e o checkpoint anterior a qualquer alteracao feita
    por um agente: permite diff e rollback exatos depois.
    """
    manifesto = []
    for caminho in sorted(destino.rglob("*")):
        if not caminho.is_file():
            continue
        conteudo = caminho.read_bytes()
        manifesto.append(
            {
                "caminho": str(caminho.relative_to(destino)),
                "bytes": len(conteudo),
                "sha256": hashlib.sha256(conteudo).hexdigest(),
            }
        )

    saida.write_text(json.dumps(manifesto, indent=2, ensure_ascii=False))
    return saida


def analisar_projeto(caminho_zip: Path, diretorio_trabalho: Path) -> RelatorioProjeto:
    """Executa o fluxo completo: extracao segura, inventario, scan e snapshot."""
    destino = diretorio_trabalho / "extraido"
    extrair_seguro(caminho_zip, destino)

    total_arquivos, total_bytes, dependencias, riscos_inventario = montar_inventario(destino)
    riscos_scan = escanear_padroes_suspeitos(destino)

    snapshot_path = gerar_snapshot(destino, diretorio_trabalho / "snapshot.json")

    todos_riscos = riscos_inventario + riscos_scan
    pode_auto_prosseguir = len(todos_riscos) == 0

    return RelatorioProjeto(
        origem_zip=str(caminho_zip),
        diretorio_extraido=str(destino),
        total_arquivos=total_arquivos,
        total_bytes=total_bytes,
        dependencias_detectadas=dependencias,
        arquivos_de_risco=[asdict(r) for r in riscos_inventario],
        padroes_suspeitos=[asdict(r) for r in riscos_scan],
        snapshot_path=str(snapshot_path),
        pode_auto_prosseguir=pode_auto_prosseguir,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zip", type=Path, help="Caminho do ZIP do projeto recebido")
    parser.add_argument(
        "--saida",
        type=Path,
        default=None,
        help="Diretorio de trabalho para extracao/snapshot (padrao: <zip>_analise)",
    )
    args = parser.parse_args()

    diretorio_trabalho = args.saida or args.zip.with_name(args.zip.stem + "_analise")
    diretorio_trabalho.mkdir(parents=True, exist_ok=True)

    try:
        relatorio = analisar_projeto(args.zip, diretorio_trabalho)
    except ZipInseguroError as erro:
        print(json.dumps({"erro": str(erro), "pode_auto_prosseguir": False}, indent=2, ensure_ascii=False))
        raise SystemExit(1)

    print(json.dumps(asdict(relatorio), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
