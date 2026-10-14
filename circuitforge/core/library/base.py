"""
Infraestrutura da biblioteca de circuitos.

Cada circuito é descrito por um ``CircuitDef``: parâmetros editáveis, função que
gera o netlist SPICE, análises sugeridas, fórmulas teóricas e uma lição para o
modo Instrutor (funciona 100% offline, sem IA).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

PI = math.pi

CATEGORIES: Dict[str, str] = {
    "basicos": "🔌 Fundamentos",
    "fontes": "🔋 Fontes de alimentação",
    "computador": "💻 Placas de computador",
    "ia": "🧠 Placas e circuitos de IA",
    "audio": "🔊 Amplificadores de som",
    "guitarra": "🎸 Pedais de guitarra",
    "solar": "☀️ Energia solar",
    "veiculos": "🚗 Circuitos veiculares",
    "radio_tv": "📻 Rádio, TV e som",
    "antenas": "📡 Antenas e RF",
}

# Subcircuitos auxiliares disponíveis para qualquer circuito (inclusive os da IA)
HELPERS = """\
* ---- Subcircuitos auxiliares do CircuitForge ----
* Amp-op comportamental: GBW ~1 MHz, ganho DC 1e5, saturação a 1 V dos trilhos
.subckt OPAMP inp inn out vcc vee
Rin inp inn 1e9
Eg x 0 inp inn 1e5
Rp x y 1k
Cp y 0 1.59e-5
Bo o 0 V=(V(vcc)+V(vee))/2+((V(vcc)-V(vee))/2-1)*tanh((V(y)-(V(vcc)+V(vee))/2)/((V(vcc)-V(vee))/2-1))
Ro o out 50
.ends OPAMP
.model SWM SW(Vt=0.5 Vh=0.05 Ron=0.01 Roff=1e8)
.model SWPWR SW(Vt=0.5 Vh=0.05 Ron=0.002 Roff=1e8)
.model SWCMP SW(Vt=0 Vh=0.02 Ron=10 Roff=1e9)
.model DSCH D(Is=1e-8 N=1.05 Rs=0.05 Cjo=100p Bv=40 Ibv=1e-3)
.model D1N4148 D(Is=2.5e-9 N=1.75 Rs=0.6 Cjo=4p Bv=100 Ibv=1e-4)
.model DSI D(Is=1e-14 N=1.0 Rs=0.05)
.model DLED D(Is=1e-18 N=2.0 Rs=2 Cjo=30p)
.model QN2222 NPN(Is=1e-14 Bf=200 Vaf=100 Cje=22p Cjc=8p Tf=0.4n Rb=10 Rc=1 Re=0.2)
.model QP2907 PNP(Is=1e-14 Bf=150 Vaf=100 Cje=20p Cjc=8p Tf=0.5n Rb=10 Rc=1 Re=0.2)
.model QPOWN NPN(Is=1e-13 Bf=80 Vaf=100 Rb=1 Rc=0.2 Re=0.05 Cje=100p Cjc=50p)
.model QPOWP PNP(Is=1e-13 Bf=80 Vaf=100 Rb=1 Rc=0.2 Re=0.05 Cje=100p Cjc=50p)
.model NMOSP NMOS(Level=1 Vto=2.0 Kp=5 Lambda=0.01 Rd=0.01 Rs=0.01 Cgso=1n Cgdo=0.3n)
.model PMOSP PMOS(Level=1 Vto=-2.0 Kp=5 Lambda=0.01 Rd=0.01 Rs=0.01 Cgso=1n Cgdo=0.3n)
.model NMLOG NMOS(Level=1 Vto=0.6 Kp=200u Lambda=0.02)
.model PMLOG PMOS(Level=1 Vto=-0.6 Kp=80u Lambda=0.02)
"""


@dataclass
class Param:
    key: str
    label: str
    default: float
    unit: str = ""
    min: Optional[float] = None
    max: Optional[float] = None

    def clamp(self, v: float) -> float:
        v = float(v)
        if self.min is not None:
            v = max(self.min, v)
        if self.max is not None:
            v = min(self.max, v)
        return v


@dataclass
class Lesson:
    objetivo: str = ""
    teoria: List[str] = field(default_factory=list)
    observe: List[str] = field(default_factory=list)
    experimentos: List[str] = field(default_factory=list)
    cuidados: List[str] = field(default_factory=list)


Theory = Callable[[Dict[str, float]], Dict[str, Tuple[float, str]]]


@dataclass
class CircuitDef:
    id: str
    name: str
    category: str
    summary: str
    params: List[Param]
    build: Callable[[Dict[str, float]], str]
    analyses: Callable[[Dict[str, float]], Dict[str, Dict]]
    probes: List[str] = field(default_factory=list)
    theory: Optional[Theory] = None
    lesson: Lesson = field(default_factory=Lesson)
    sweepable: bool = True

    # ------------------------------------------------------------------
    def defaults(self) -> Dict[str, float]:
        return {p.key: p.default for p in self.params}

    def resolve(self, overrides: Optional[Dict[str, float]] = None) -> Dict[str, float]:
        vals = self.defaults()
        for p in self.params:
            if overrides and p.key in overrides and overrides[p.key] is not None:
                vals[p.key] = p.clamp(overrides[p.key])
        return vals

    def netlist(self, overrides: Optional[Dict[str, float]] = None, with_helpers: bool = True) -> str:
        p = self.resolve(overrides)
        body = self.build(p).strip("\n")
        head = f"{self.name}\n"
        return head + (HELPERS if with_helpers else "") + body + "\n"

    def analysis_options(self, overrides: Optional[Dict[str, float]] = None) -> Dict[str, Dict]:
        return self.analyses(self.resolve(overrides))

    def default_analysis(self, overrides: Optional[Dict[str, float]] = None) -> Dict:
        opts = self.analysis_options(overrides)
        return next(iter(opts.values()))

    def theory_values(self, overrides: Optional[Dict[str, float]] = None):
        if not self.theory:
            return {}
        return self.theory(self.resolve(overrides))


REGISTRY: Dict[str, CircuitDef] = {}


def register(cdef: CircuitDef) -> CircuitDef:
    if cdef.id in REGISTRY:
        raise ValueError(f"Circuito duplicado: {cdef.id}")
    if cdef.category not in CATEGORIES:
        raise ValueError(f"Categoria inválida: {cdef.category}")
    REGISTRY[cdef.id] = cdef
    return cdef


def circuit(
    *, id: str, name: str, category: str, summary: str, params: List[Param],
    analyses, probes: Optional[List[str]] = None, theory: Optional[Theory] = None,
    lesson: Optional[Lesson] = None, sweepable: bool = True,
):
    """Decorador: registra a função ``build(p) -> str`` como circuito."""
    def deco(fn):
        register(CircuitDef(
            id=id, name=name, category=category, summary=summary, params=params,
            build=fn, analyses=analyses, probes=probes or [], theory=theory,
            lesson=lesson or Lesson(), sweepable=sweepable,
        ))
        return fn
    return deco


# --- helpers de análise ----------------------------------------------------

def tran(freq: float, cycles: float = 5, ppc: int = 200, settle: float = 0.0) -> Dict:
    period = 1.0 / freq
    stop = cycles * period + settle
    return {"kind": "tran", "step": period / ppc, "stop": stop, "maxstep": period / ppc}


def tran_time(stop: float, points: int = 4000) -> Dict:
    return {"kind": "tran", "step": stop / points, "stop": stop, "maxstep": stop / points}


def ac(start: float, stop: float, points: int = 40) -> Dict:
    return {"kind": "ac", "start": start, "stop": stop, "points": points}


def dc(source: str, start: float, stop: float, step: float) -> Dict:
    return {"kind": "dc", "source": source, "start": start, "stop": stop, "step": step}


OP = {"kind": "op"}


def get(circuit_id: str) -> CircuitDef:
    if circuit_id not in REGISTRY:
        raise KeyError(f"Circuito desconhecido: {circuit_id}")
    return REGISTRY[circuit_id]


def by_category() -> Dict[str, List[CircuitDef]]:
    out: Dict[str, List[CircuitDef]] = {k: [] for k in CATEGORIES}
    for c in REGISTRY.values():
        out[c.category].append(c)
    return out
