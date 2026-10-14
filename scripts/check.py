#!/usr/bin/env python3
"""Verificação antes de cada push: testes, arquivos grandes, segredos, pesos e .env versionados.

Uso: python scripts/check.py        (sai com código 1 se algo bloqueante for encontrado)
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OWN = ("app/", "tests/", "docs/", "scripts/", "README.md", "pyproject.toml", ".env.example")
SELF = {"scripts/check.py", "tests/test_check_script.py"}
MAX_BYTES = 1_000_000
BLOCKED_EXT = {".keystore", ".jks", ".p12", ".gguf", ".onnx", ".safetensors", ".pt", ".bin", ".db", ".sqlite", ".sqlite3", ".wav", ".pem", ".key"}
TEXT_EXT = {".py", ".md", ".yaml", ".yml", ".toml", ".json", ".txt", ".js", ".html", ".cjs", ".css", ""}
SECRETS = {
    "chave privada": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "token GitHub": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{30,}\b"),
    "chave AWS": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "chave sk-": re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"),
    "atribuição de segredo": re.compile(
        r"(?i)\b(password|passwd|secret|api[_-]?key|token)\b\s*[:=]\s*['\"][^'\"\s]{8,}['\"]"),
}


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line]


def scan_text(rel: str, text: str) -> list[str]:
    return [f"{rel}: possível segredo ({label})" for label, rx in SECRETS.items() if rx.search(text)]


def scan(files: list[str]) -> tuple[list[str], list[str]]:
    """(erros bloqueantes nos arquivos do SWARM, avisos sobre o resto do repositório)."""
    errors, warnings = [], []
    for rel in files:
        p = ROOT / rel
        if not p.is_file():
            continue
        name, ext = p.name.lower(), p.suffix.lower()
        if rel.startswith(OWN):
            if p.stat().st_size > MAX_BYTES:
                errors.append(f"{rel}: arquivo grande ({p.stat().st_size // 1024} KB)")
            if ext in BLOCKED_EXT:
                errors.append(f"{rel}: tipo que não deve ser versionado ({ext})")
            if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
                errors.append(f"{rel}: .env versionado")
            if ext in TEXT_EXT and rel not in SELF:  # estes arquivos contêm exemplos dos próprios padrões
                errors += scan_text(rel, p.read_text(encoding="utf-8", errors="replace"))
        elif ext in {".keystore", ".jks", ".p12", ".pem", ".key"} or name == ".env":
            warnings.append(f"{rel}: material de assinatura/segredo versionado (fora do SWARM; revisar)")
    return errors, warnings


def run(cmd: list[str]) -> bool:
    print("$", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT).returncode == 0


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from app.stdio import utf8_stdio
    utf8_stdio()
    errors, warnings = scan(tracked())
    for w in warnings:
        print("AVISO:", w)
    for e in errors:
        print("ERRO:", e)
    ok = not errors
    ruff_bin = Path(sys.executable).parent
    if shutil.which("ruff") or (ruff_bin / "ruff").exists() or (ruff_bin / "ruff.exe").exists():
        ok &= run([sys.executable, "-m", "ruff", "check", "app", "tests", "scripts"])
    else:
        print("AVISO: ruff não encontrado (pip install -e '.[dev]'); lint NÃO foi executado")
    ok &= run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
    if shutil.which("node"):
        ok &= run(["node", "--test", "tests/js/lib.test.cjs"])
    else:
        print("AVISO: node não encontrado; testes JavaScript NÃO foram executados")
    print("OK: pronto para push" if ok else "FALHOU: não faça push")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
