"""
Executor ngspice via linha de comando (modo batch) + leitor de rawfile.

Usado no lugar do backend de biblioteca compartilhada do PySpice, que não é
compatível com versões recentes do ngspice (ex.: 42+).
"""

from __future__ import annotations
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Tuple

import numpy as np


class NgSpiceError(RuntimeError):
    pass


def find_ngspice() -> str | None:
    return shutil.which("ngspice")


def _clean_deck(netlist: str) -> list[str]:
    """Remove .end e cartões de análise/controle já presentes."""
    lines = []
    for raw in netlist.splitlines():
        s = raw.strip()
        low = s.lower()
        if not s:
            continue
        if re.match(r"\.(end|tran|ac|dc|op)\b", low):
            continue
        lines.append(s)
    return lines


def run_ngspice(netlist: str, analysis_card: str, timeout: float = 120.0) -> Dict[str, np.ndarray]:
    """Roda `analysis_card` (ex.: '.tran 1u 1m') sobre o netlist e devolve as variáveis."""
    exe = find_ngspice()
    if exe is None:
        raise NgSpiceError(
            "ngspice não encontrado no PATH. Instale com: sudo apt install ngspice"
        )
    lines = _clean_deck(netlist)
    if not lines:
        raise NgSpiceError("Netlist vazio.")
    if not lines[0].startswith("."):
        pass  # primeira linha é o título
    else:
        # PySpice emite '.title X' como 1ª linha; ngspice aceita, mas garantimos um título real
        lines[0] = re.sub(r"^\.title\s*", "", lines[0], flags=re.I) or "CircuitForge"
    deck = "\n".join(lines + [analysis_card, ".end", ""])

    with tempfile.TemporaryDirectory(prefix="cforge_") as tmp:
        cir = Path(tmp) / "deck.cir"
        raw = Path(tmp) / "out.raw"
        cir.write_text(deck)
        try:
            proc = subprocess.run(
                [exe, "-b", "-r", str(raw), str(cir)],
                capture_output=True, text=True, timeout=timeout, cwd=tmp,
            )
        except subprocess.TimeoutExpired as exc:
            raise NgSpiceError(f"ngspice excedeu o tempo limite ({timeout}s).") from exc
        out = proc.stdout + proc.stderr
        if proc.returncode != 0 or not raw.exists() or raw.stat().st_size == 0:
            tail = "\n".join(out.strip().splitlines()[-15:])
            raise NgSpiceError(f"Falha na simulação ngspice:\n{tail}")
        # Erros de convergência/netlist podem sair com código 0 mas sem dados úteis
        try:
            return parse_rawfile(raw.read_bytes())
        except Exception as exc:  # noqa: BLE001
            tail = "\n".join(out.strip().splitlines()[-15:])
            raise NgSpiceError(f"Rawfile inválido ({exc}):\n{tail}") from exc


def parse_rawfile(data: bytes) -> Dict[str, np.ndarray]:
    """Lê rawfile do ngspice (binário ou ASCII, real ou complexo)."""
    marker_b, marker_a = b"Binary:\n", b"Values:\n"
    ib, ia = data.find(marker_b), data.find(marker_a)
    if ib < 0 and ia < 0:
        raise ValueError("cabeçalho sem Binary/Values")
    binary = ib >= 0 and (ia < 0 or ib < ia)
    idx = ib if binary else ia
    marker = marker_b if binary else marker_a
    header = data[:idx].decode("utf-8", "replace")
    body = data[idx + len(marker):]

    n_vars = n_points = None
    complex_ = False
    names: list[str] = []
    in_vars = False
    for line in header.splitlines():
        if line.startswith("Flags:"):
            complex_ = "complex" in line
        elif line.startswith("No. Variables:"):
            n_vars = int(line.split(":")[1])
        elif line.startswith("No. Points:"):
            n_points = int(line.split(":")[1])
        elif line.startswith("Variables:"):
            in_vars = True
            rest = line.split(":", 1)[1].strip()
            if rest:
                names.append(rest.split()[1])
        elif in_vars and line.strip():
            names.append(line.split()[1])
    if not n_vars or not n_points or len(names) != n_vars:
        raise ValueError("cabeçalho incompleto")

    per = 2 if complex_ else 1
    if binary:
        arr = np.frombuffer(body, dtype="<f8", count=n_vars * n_points * per)
        arr = arr.reshape(n_points, n_vars * per)
        if complex_:
            mat = arr[:, 0::2] + 1j * arr[:, 1::2]
        else:
            mat = arr
    else:
        vals = []
        for tok in body.decode().replace("\t", " ").split("\n"):
            tok = tok.strip()
            if not tok:
                continue
            parts = tok.split()
            if len(parts) == 2 and parts[0].isdigit() and "," not in parts[1]:
                tok = parts[1]  # início de ponto: "<idx> <valor>"
            elif len(parts) == 1:
                tok = parts[0]
            else:
                tok = parts[-1]
            if complex_:
                re_, im_ = tok.split(",")
                vals.append(complex(float(re_), float(im_)))
            else:
                vals.append(float(tok))
        mat = np.array(vals).reshape(n_points, n_vars)

    result: Dict[str, np.ndarray] = {}
    for i, name in enumerate(names):
        result[name] = np.array(mat[:, i])
    return result


def normalize_names(raw: Dict[str, np.ndarray]) -> Tuple[Dict[str, np.ndarray], Dict[str, np.ndarray]]:
    """Separa (nós, ramos). 'v(x)'→'x'; 'vsrc#branch'→'vsrc'; 'i(vsrc)'→'vsrc'."""
    nodes: Dict[str, np.ndarray] = {}
    branches: Dict[str, np.ndarray] = {}
    for name, arr in raw.items():
        low = name.lower()
        if low in ("time", "frequency") or low.endswith("-sweep"):
            continue
        m = re.fullmatch(r"v\((.+)\)", low)
        if m:
            nodes[m.group(1)] = arr
        elif low.endswith("#branch"):
            branches[low[: -len("#branch")]] = arr
        else:
            m = re.fullmatch(r"i\((.+)\)", low)
            if m:
                branches[m.group(1)] = arr
            else:
                nodes[low] = arr
    return nodes, branches
