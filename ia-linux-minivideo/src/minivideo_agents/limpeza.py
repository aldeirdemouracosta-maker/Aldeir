"""Limpeza de Jobs/: apaga arquivos intermediários de jobs antigos.

Fica o que permite entender e reproduzir o job: job.json e relatórios
pequenos (.json, .jsonl, .csv, .srt, .txt). Vão embora quadros, clipes
intermediários e áudio temporário. Por padrão só lista (dry-run).
"""

from __future__ import annotations

import os
import shutil
import time
from typing import Dict, List

MANTER = (".json", ".jsonl", ".csv", ".srt", ".txt", ".log")


def _tamanho(caminho: str) -> int:
    if os.path.isfile(caminho) or os.path.islink(caminho):
        return os.lstat(caminho).st_size
    total = 0
    for raiz, _, arquivos in os.walk(caminho):
        for a in arquivos:
            try:
                total += os.lstat(os.path.join(raiz, a)).st_size
            except OSError:
                pass
    return total


def _mais_recente(caminho: str) -> float:
    m = os.lstat(caminho).st_mtime
    for raiz, dirs, arquivos in os.walk(caminho):
        for n in dirs + arquivos:
            try:
                m = max(m, os.lstat(os.path.join(raiz, n)).st_mtime)
            except OSError:
                pass
    return m


def planejar(jobs_dir: str, dias: float) -> List[Dict]:
    """Lista o que seria apagado: jobs sem mudança há mais de ``dias``."""
    limite = time.time() - dias * 86400
    itens = []
    for nome in sorted(os.listdir(jobs_dir)):
        job = os.path.join(jobs_dir, nome)
        if not os.path.isdir(job) or os.path.islink(job) or _mais_recente(job) > limite:
            continue
        for raiz, dirs, arquivos in os.walk(job, topdown=True):
            for d in list(dirs):
                p = os.path.join(raiz, d)
                if os.path.islink(p):
                    dirs.remove(d)
            for a in arquivos:
                p = os.path.join(raiz, a)
                if not a.lower().endswith(MANTER):
                    itens.append({"job": nome, "caminho": p, "bytes": _tamanho(p)})
    return itens


def executar(jobs_dir: str, itens: List[Dict]) -> int:
    """Apaga os itens e as pastas que ficarem vazias. Devolve bytes liberados."""
    raiz_real = os.path.realpath(jobs_dir)
    liberado = 0
    for it in itens:
        p = it["caminho"]
        if not os.path.realpath(p).startswith(raiz_real + os.sep):
            continue  # nunca sai de Jobs/
        try:
            os.unlink(p)
            liberado += it["bytes"]
        except OSError:
            pass
    for nome in os.listdir(jobs_dir):
        job = os.path.join(jobs_dir, nome)
        if os.path.isdir(job) and not os.path.islink(job):
            for raiz, _, _ in sorted(os.walk(job, topdown=False), key=lambda t: -len(t[0])):
                try:
                    os.rmdir(raiz)  # só remove se vazia
                except OSError:
                    pass
    return liberado
