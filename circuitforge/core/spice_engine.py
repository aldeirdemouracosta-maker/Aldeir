"""
Motor SPICE baseado em ngspice (modo batch, sem PySpice).

- Sanitiza netlists (importante para netlists gerados por IA).
- Executa ``ngspice -b`` e lê o arquivo .raw ASCII.
- Devolve dicionários {nome: np.ndarray}.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

NGSPICE_BIN = os.environ.get("NGSPICE_BIN") or shutil.which("ngspice") or "ngspice"


class SpiceError(RuntimeError):
    """Erro de sintaxe, convergência ou execução do ngspice."""


def ngspice_available() -> bool:
    return shutil.which(NGSPICE_BIN) is not None or os.path.exists(NGSPICE_BIN)


# ---------------------------------------------------------------------------
# Sanitização
# ---------------------------------------------------------------------------

# Cartões que o usuário/IA pode usar. O resto é descartado (ou recusado).
_ALLOWED_DOT = {
    ".model", ".subckt", ".ends", ".param", ".ic", ".nodeset", ".options",
    ".option", ".func", ".global", ".temp", ".end",
}
_ANALYSIS_DOT = {".tran", ".ac", ".dc", ".op"}
_FORBIDDEN_DOT = {".include", ".inc", ".lib", ".csparam", ".control", ".endc"}
_FORBIDDEN_TOKENS = re.compile(
    r"(\bfile\s*=|\bshell\b|\bsystem\b|\bsource\b\s+\S|\bwrite\b|\bcodemodel\b|"
    r"\bpython\b|\bdevaluate\b|/etc/|\.\./)",
    re.IGNORECASE,
)


@dataclass
class SanitizedNetlist:
    title: str
    body: str                       # sem título, sem .end, sem análises
    analyses: List[str] = field(default_factory=list)  # cartões de análise vistos
    warnings: List[str] = field(default_factory=list)

    def text(self) -> str:
        return f"{self.title}\n{self.body}\n"


def _looks_like_element(line: str) -> bool:
    toks = line.split()
    if len(toks) < 3:
        return False
    name = toks[0]
    if not re.fullmatch(r"[RCLVIDQMEFGHBSTKXJUrclvidqmefghbstkxju][A-Za-z0-9_]*", name):
        return False
    return bool(re.search(r"\d", name)) or len(name) <= 2


def sanitize_netlist(text: str, default_title: str = "CircuitForge",
                     has_title: Optional[bool] = None) -> SanitizedNetlist:
    """
    Remove blocos .control, cartões de análise/print e qualquer coisa que
    leia/escreva arquivos ou execute comandos. Levanta SpiceError se o
    netlist tentar algo proibido.
    """
    lines = [ln.rstrip() for ln in text.replace("\r", "").split("\n")]
    # remove cercas markdown acidentais
    lines = [ln for ln in lines if not ln.strip().startswith("```")]

    if not any(ln.strip() for ln in lines):
        raise SpiceError("Netlist vazio.")

    first = lines[0].strip()
    # A primeira linha é título se não parecer um elemento/cartão SPICE
    if has_title is None:
        has_title = bool(first) and not first.startswith((".", "*")) and not _looks_like_element(first)
    if has_title and first.startswith("*"):
        has_title = False
    if has_title:
        title = first.lstrip("* ").strip() or default_title
        lines = lines[1:]
    else:
        title = default_title

    out: List[str] = []
    analyses: List[str] = []
    warnings: List[str] = []
    in_control = False
    subckt_depth = 0

    for raw in lines:
        ln = raw.strip()
        if not ln:
            continue
        low = ln.lower()
        if low.startswith(".control"):
            in_control = True
            warnings.append("Bloco .control removido por segurança.")
            continue
        if low.startswith(".endc"):
            in_control = False
            continue
        if in_control:
            continue
        if ln.startswith("*"):
            out.append(ln)
            continue
        if _FORBIDDEN_TOKENS.search(ln):
            raise SpiceError(f"Linha não permitida no netlist: {ln!r}")
        if ln.startswith("+"):
            out.append(ln)
            continue
        if ln.startswith("."):
            card = low.split()[0]
            if card in _FORBIDDEN_DOT:
                raise SpiceError(f"Cartão {card} não é permitido (use apenas componentes inline).")
            if card in _ANALYSIS_DOT:
                analyses.append(ln)
                continue
            if card in (".print", ".plot", ".probe", ".save", ".meas", ".measure",
                        ".four", ".noise", ".tf", ".sens", ".disto", ".pz", ".width",
                        ".alter", ".step", ".end"):
                continue
            if card == ".subckt":
                subckt_depth += 1
            elif card == ".ends":
                subckt_depth = max(0, subckt_depth - 1)
            if card not in _ALLOWED_DOT:
                warnings.append(f"Cartão {card} ignorado.")
                continue
        out.append(ln)

    if subckt_depth:
        raise SpiceError(".subckt sem .ends correspondente.")
    if not any(not l.startswith("*") for l in out):
        raise SpiceError("Netlist sem componentes.")
    return SanitizedNetlist(title=title, body="\n".join(out), analyses=analyses, warnings=warnings)


# ---------------------------------------------------------------------------
# Cartões de análise
# ---------------------------------------------------------------------------

def analysis_card(spec: Dict) -> str:
    kind = spec["kind"]
    if kind == "tran":
        step, stop = spec["step"], spec["stop"]
        maxstep = spec.get("maxstep", step)
        uic = " uic" if spec.get("uic") else ""
        return f".tran {step:.6g} {stop:.6g} 0 {maxstep:.6g}{uic}"
    if kind == "ac":
        return f".ac dec {int(spec.get('points', 20))} {spec['start']:.6g} {spec['stop']:.6g}"
    if kind == "dc":
        return f".dc {spec['source']} {spec['start']:.6g} {spec['stop']:.6g} {spec['step']:.6g}"
    if kind == "op":
        return ".op"
    raise SpiceError(f"Análise desconhecida: {kind}")


# ---------------------------------------------------------------------------
# Execução e leitura do .raw
# ---------------------------------------------------------------------------

def _normalize(name: str) -> str:
    n = name.strip().lower()
    m = re.fullmatch(r"v\((.+)\)", n)
    if m:
        return m.group(1)
    m = re.fullmatch(r"(.+)#branch", n)
    if m:
        return f"i({m.group(1)})"
    m = re.fullmatch(r"i\((.+)\)", n)
    if m:
        return f"i({m.group(1)})"
    return n


def parse_ascii_raw(path: str) -> Dict[str, np.ndarray]:
    with open(path, "r", errors="replace") as fh:
        content = fh.read()
    head, sep, values = content.partition("\nValues:")
    if not sep:
        raise SpiceError("Arquivo .raw sem seção Values.")
    flags = re.search(r"^Flags:\s*(.*)$", head, re.M)
    is_complex = bool(flags and "complex" in flags.group(1).lower())
    nvars = int(re.search(r"No\. Variables:\s*(\d+)", head).group(1))
    npts = int(re.search(r"No\. Points:\s*(\d+)", head).group(1))
    vars_block = head.split("\nVariables:", 1)[1]
    names = []
    for ln in vars_block.strip().split("\n")[:nvars]:
        parts = ln.split()
        names.append(parts[1])

    if is_complex:
        toks = values.replace(",", " ").split()
        arr = np.array(toks, dtype=float)
        per = 1 + 2 * nvars
        arr = arr[: npts * per].reshape(npts, per)[:, 1:]
        data = arr[:, 0::2] + 1j * arr[:, 1::2]
    else:
        arr = np.array(values.split(), dtype=float)
        per = 1 + nvars
        data = arr[: npts * per].reshape(npts, per)[:, 1:]

    out: Dict[str, np.ndarray] = {}
    for i, n in enumerate(names):
        out[_normalize(n)] = data[:, i]
    return out


_ERR_RE = re.compile(r"(error|fatal|singular|no such|unknown|too many|timestep too small|"
                     r"doAnalyses|convergence|could not find|undefined)", re.I)


def run_netlist(
    text: str,
    analysis: Dict,
    timeout: float = 120.0,
) -> Dict[str, np.ndarray]:
    """Executa ``text`` (já sanitizado, com título) com a análise indicada."""
    if not ngspice_available():
        raise SpiceError(
            "ngspice não encontrado. Instale com `sudo apt install ngspice` "
            "ou defina a variável NGSPICE_BIN."
        )
    with tempfile.TemporaryDirectory(prefix="cforge_") as tmp:
        raw = os.path.join(tmp, "out.raw")
        cir = os.path.join(tmp, "circuit.cir")
        deck = (
            f"{text.rstrip()}\n{analysis_card(analysis)}\n"
            ".control\nset filetype=ascii\nset noaskquit\nrun\n"
            f"write {raw} all\n.endc\n.end\n"
        )
        with open(cir, "w") as fh:
            fh.write(deck)
        try:
            proc = subprocess.run(
                [NGSPICE_BIN, "-b", cir],
                capture_output=True, text=True, timeout=timeout, cwd=tmp,
            )
        except subprocess.TimeoutExpired:
            raise SpiceError(f"Simulação excedeu {timeout:.0f}s (reduza o tempo ou aumente o passo).")
        log = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if not os.path.exists(raw) or os.path.getsize(raw) == 0:
            errs = [l.strip() for l in log.split("\n") if _ERR_RE.search(l)]
            msg = "; ".join(dict.fromkeys(errs))[:600] or log.strip()[-600:]
            raise SpiceError(f"ngspice falhou: {msg}")
        data = parse_ascii_raw(raw)
    if analysis["kind"] == "tran" and "time" not in data:
        raise SpiceError("Resultado transient sem eixo de tempo.")
    return data
