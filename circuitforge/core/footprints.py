"""
Gerador determinístico de footprints KiCad (.kicad_mod) para pacotes comuns.

A IA local NÃO inventa geometria: pads, passo e dimensões vêm daqui (reproduzíveis e
conferíveis); o LLM só descreve/explica ou ajuda a escolher o pacote.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class Pad:
    number: str
    x: float
    y: float
    w: float
    h: float
    kind: str = "smd"            # smd | thru
    drill: float = 0.0
    shape: str = "roundrect"     # roundrect | circle | rect


@dataclass
class FootprintSpec:
    name: str
    package_type: str            # SMD | THT
    pins: int
    pitch_mm: Optional[float]
    body_mm: Tuple[float, float]
    description: str
    pads: List[Pad] = field(default_factory=list)
    courtyard: Tuple[float, float] = (0.0, 0.0)
    tags: str = ""

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["body_size_mm"] = f"{self.body_mm[0]}x{self.body_mm[1]}"
        return d

    def to_kicad(self) -> str:
        """Texto .kicad_mod (formato KiCad 6/7/8)."""
        cw, ch = self.courtyard
        bw, bh = self.body_mm
        L = [f'(footprint "{self.name}" (version 20221018) (generator circuitforge) (layer "F.Cu")',
             f'  (descr "{self.description}")', f'  (tags "{self.tags}")',
             f'  (attr {"smd" if self.package_type == "SMD" else "through_hole"})',
             f'  (fp_text reference "REF**" (at 0 {-(ch / 2 + 0.8):.3f}) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))',
             f'  (fp_text value "{self.name}" (at 0 {ch / 2 + 0.8:.3f}) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))']
        # corpo (Fab) e silk
        L.append(f'  (fp_rect (start {-bw / 2:.3f} {-bh / 2:.3f}) (end {bw / 2:.3f} {bh / 2:.3f}) (stroke (width 0.1) (type solid)) (fill none) (layer "F.Fab"))')
        L.append(f'  (fp_rect (start {-cw / 2:.3f} {-ch / 2:.3f}) (end {cw / 2:.3f} {ch / 2:.3f}) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd"))')
        L.append(f'  (fp_line (start {-bw / 2:.3f} {-bh / 2 - 0.2:.3f}) (end {bw / 2:.3f} {-bh / 2 - 0.2:.3f}) (stroke (width 0.12) (type solid)) (layer "F.SilkS"))')
        if self.pads:
            p1 = self.pads[0]
            L.append(f'  (fp_circle (center {p1.x + math.copysign(max(p1.w, 0.6) / 2 + 0.5, p1.x or 1):.3f} {p1.y:.3f}) (end {p1.x + math.copysign(max(p1.w, 0.6) / 2 + 0.3, p1.x or 1):.3f} {p1.y:.3f}) (stroke (width 0.12) (type solid)) (fill none) (layer "F.SilkS"))')
        for p in self.pads:
            if p.kind == "smd":
                shape = "roundrect" if p.shape == "roundrect" else p.shape
                extra = " (roundrect_rratio 0.25)" if shape == "roundrect" else ""
                L.append(f'  (pad "{p.number}" smd {shape} (at {p.x:.3f} {p.y:.3f}) (size {p.w:.3f} {p.h:.3f}) (layers "F.Cu" "F.Paste" "F.Mask"){extra})')
            else:
                shape = "rect" if p.number == "1" else p.shape
                L.append(f'  (pad "{p.number}" thru_hole {shape} (at {p.x:.3f} {p.y:.3f}) (size {p.w:.3f} {p.h:.3f}) (drill {p.drill:.3f}) (layers "*.Cu" "*.Mask"))')
        L.append(")")
        return "\n".join(L) + "\n"


# --------------------------------------------------------------------------------------
# Famílias
# --------------------------------------------------------------------------------------

# (nome métrico IPC, corpo L×W, pad W×H, centro-a-centro)
CHIPS = {
    "0201": ((0.6, 0.3), (0.32, 0.36), 0.66), "0402": ((1.0, 0.5), (0.58, 0.62), 1.04),
    "0603": ((1.6, 0.8), (0.8, 0.95), 1.54), "0805": ((2.0, 1.25), (1.0, 1.45), 1.80),
    "1206": ((3.2, 1.6), (1.15, 1.8), 3.20), "1210": ((3.2, 2.5), (1.15, 2.7), 3.20),
}


def chip(size: str = "0805", kind: str = "C") -> FootprintSpec:
    if size not in CHIPS:
        raise ValueError(f"Tamanho de chip desconhecido: {size}. Opções: {', '.join(CHIPS)}")
    body, pad, pitch = CHIPS[size]
    name = f"{kind}_{size}_{int(round(body[0] * 10)):02d}{int(round(body[1] * 10)):02d}Metric"
    pads = [Pad("1", -pitch / 2, 0, pad[0], pad[1]), Pad("2", pitch / 2, 0, pad[0], pad[1])]
    return FootprintSpec(name, "SMD", 2, None, body, f"{ {'C': 'Capacitor', 'R': 'Resistor', 'L': 'Indutor', 'LED': 'LED'}.get(kind, kind)} SMD {size} (IPC-7351 nominal)",
                         pads, (pitch + pad[0] + 0.5, max(pad[1], body[1]) + 0.5), f"{kind} {size}")


def dual_row_smd(n: int, pitch: float, span: float, pad_w: float, pad_h: float, body: Tuple[float, float],
                 name: str, desc: str, ep: Optional[Tuple[float, float]] = None) -> FootprintSpec:
    per = n // 2
    pads: List[Pad] = []
    y0 = -(per - 1) * pitch / 2
    for i in range(per):
        pads.append(Pad(str(i + 1), -span / 2, y0 + i * pitch, pad_w, pad_h))
    for i in range(per):
        pads.append(Pad(str(per + i + 1), span / 2, -y0 - i * pitch, pad_w, pad_h))
    if ep:
        pads.append(Pad(str(n + 1), 0, 0, ep[0], ep[1], shape="rect"))
    return FootprintSpec(name, "SMD", n, pitch, body, desc, pads, (span + pad_w + 0.5, max(per * pitch, body[1]) + 0.5), name)


def soic(n: int = 8) -> FootprintSpec:
    if n not in (8, 14, 16):
        raise ValueError("SOIC suportado: 8, 14 ou 16 pinos")
    length = {8: 4.9, 14: 8.65, 16: 9.9}[n]
    return dual_row_smd(n, 1.27, 5.4, 1.95, 0.6, (3.9, length), f"SOIC-{n}_3.9x{length}mm_P1.27mm",
                        f"SOIC-{n}, passo 1,27 mm, corpo 3,9 × {length} mm")


def tssop(n: int = 16) -> FootprintSpec:
    length = {8: 3.0, 14: 5.0, 16: 5.0, 20: 6.5}.get(n)
    if length is None:
        raise ValueError("TSSOP suportado: 8, 14, 16, 20")
    return dual_row_smd(n, 0.65, 5.8, 1.5, 0.4, (4.4, length), f"TSSOP-{n}_4.4x{length}mm_P0.65mm",
                        f"TSSOP-{n}, passo 0,65 mm, corpo 4,4 × {length} mm")


def dip(n: int = 8, wide: bool = False) -> FootprintSpec:
    if n % 2 or n < 4:
        raise ValueError("DIP precisa de número par de pinos ≥ 4")
    row = 15.24 if wide else 7.62
    per = n // 2
    pads = []
    y0 = -(per - 1) * 2.54 / 2
    for i in range(per):
        pads.append(Pad(str(i + 1), -row / 2, y0 + i * 2.54, 1.6, 1.6, "thru", 0.8, "circle"))
    for i in range(per):
        pads.append(Pad(str(per + i + 1), row / 2, -y0 - i * 2.54, 1.6, 1.6, "thru", 0.8, "circle"))
    body = (6.35 if not wide else 13.7, per * 2.54)
    return FootprintSpec(f"DIP-{n}_W{row:.2f}mm", "THT", n, 2.54, body, f"DIP-{n}, passo 2,54 mm, largura {row:.2f} mm",
                         pads, (row + 2.6, per * 2.54 + 0.8), "DIP THT")


def to92(inline: bool = True) -> FootprintSpec:
    pads = [Pad("1", -1.27, 0, 1.05, 1.5, "thru", 0.75, "circle"), Pad("2", 0, 0, 1.05, 1.5, "thru", 0.75, "circle"),
            Pad("3", 1.27, 0, 1.05, 1.5, "thru", 0.75, "circle")]
    return FootprintSpec("TO-92_Inline", "THT", 3, 1.27, (4.8, 3.9), "TO-92, 3 pinos em linha, passo 1,27 mm (transistor/regulador 78L05)",
                         pads, (5.6, 4.7), "TO-92")


def sot23() -> FootprintSpec:
    pads = [Pad("1", -1.0, -0.95, 1.0, 0.7), Pad("2", -1.0, 0.95, 1.0, 0.7), Pad("3", 1.0, 0.0, 1.0, 0.7)]
    return FootprintSpec("SOT-23", "SMD", 3, 0.95, (1.3, 2.9), "SOT-23, 3 pinos, passo 0,95 mm", pads, (3.6, 3.4), "SOT-23")


def qfn(n: int = 32, pitch: float = 0.5, body: float = 5.0, ep: Optional[float] = 3.4) -> FootprintSpec:
    if n % 4:
        raise ValueError("QFN precisa de múltiplo de 4 pinos")
    per = n // 4
    pad_l, pad_w = 0.85, pitch * 0.55
    off = body / 2 + 0.05
    pads: List[Pad] = []
    k = 1
    y0 = -(per - 1) * pitch / 2
    for i in range(per):                                   # esquerda (desce)
        pads.append(Pad(str(k), -off, y0 + i * pitch, pad_l, pad_w)); k += 1
    for i in range(per):                                   # base (esquerda→direita)
        pads.append(Pad(str(k), y0 + i * pitch, off, pad_w, pad_l)); k += 1
    for i in range(per):                                   # direita (sobe)
        pads.append(Pad(str(k), off, -y0 - i * pitch, pad_l, pad_w)); k += 1
    for i in range(per):                                   # topo (direita→esquerda)
        pads.append(Pad(str(k), -y0 - i * pitch, -off, pad_w, pad_l)); k += 1
    if ep:
        pads.append(Pad(str(n + 1), 0, 0, ep, ep, shape="rect"))
    return FootprintSpec(f"QFN-{n}-1EP_{body:g}x{body:g}mm_P{pitch:g}mm_EP{ep or 0:g}mm", "SMD", n, pitch, (body, body),
                         f"QFN-{n}, passo {pitch:g} mm, corpo {body:g}×{body:g} mm, pad térmico {ep or 0:g} mm",
                         pads, (body + 1.6, body + 1.6), "QFN")


def pin_header(n: int = 6, rows: int = 1, pitch: float = 2.54) -> FootprintSpec:
    pads = []
    k = 1
    for i in range(n):
        for r in range(rows):
            pads.append(Pad(str(k), r * pitch, i * pitch - (n - 1) * pitch / 2, 1.7, 1.7, "thru", 1.0, "circle")); k += 1
    return FootprintSpec(f"PinHeader_{rows}x{n:02d}_P{pitch:.2f}mm", "THT", n * rows, pitch, (rows * pitch, n * pitch),
                         f"Barra de pinos {rows}x{n}, passo {pitch:.2f} mm", pads, (rows * pitch + 1.0, n * pitch + 0.5), "header")


def build_footprint(request: str) -> FootprintSpec:
    """
    Interpreta nomes como 'SOIC-8', '0805', 'C0603', 'DIP-14', 'TO-92', 'QFN-32', 'SOT-23', 'header 1x6'.
    """
    s = request.strip().upper().replace("_", "-").replace(" ", "")
    m = re.fullmatch(r"([CRL]|LED)?-?(0201|0402|0603|0805|1206|1210)", s)
    if m:
        return chip(m.group(2), m.group(1) or "C")
    m = re.fullmatch(r"SOIC-?(\d+)", s)
    if m:
        return soic(int(m.group(1)))
    m = re.fullmatch(r"TSSOP-?(\d+)", s)
    if m:
        return tssop(int(m.group(1)))
    m = re.fullmatch(r"(DIP|PDIP)-?(\d+)(W)?", s)
    if m:
        return dip(int(m.group(2)), wide=bool(m.group(3)))
    if re.fullmatch(r"TO-?92", s):
        return to92()
    if re.fullmatch(r"SOT-?23", s):
        return sot23()
    m = re.fullmatch(r"QFN-?(\d+)", s)
    if m:
        n = int(m.group(1))
        return qfn(n, 0.5, {16: 3.0, 20: 4.0, 24: 4.0, 32: 5.0, 40: 6.0, 48: 7.0}.get(n, 5.0), 3.4 if n >= 32 else 2.0)
    m = re.fullmatch(r"(?:HEADER|PINHEADER)-?(\d)X(\d+)", s)
    if m:
        return pin_header(int(m.group(2)), int(m.group(1)))
    raise ValueError(f"Pacote não reconhecido: {request!r}. Exemplos: SOIC-8, 0805, DIP-14, TO-92, QFN-32, header 1x6")


SUPPORTED = ["0201/0402/0603/0805/1206/1210 (C/R/L/LED)", "SOIC-8/14/16", "TSSOP-8/14/16/20", "DIP-N / DIP-Nw", "TO-92", "SOT-23",
             "QFN-16/20/24/32/40/48", "header RxN"]
