"""Continuísta: fronteiras, áudio e coerência entre trechos (JSON).

Medidas com FFmpeg, sem modelo: diferença visual entre o último quadro de
um trecho e o primeiro do seguinte (64x36, tons de cinza), loudness
integrado EBU R128 e loudness do último/primeiro segundo nas fronteiras.
"""

from __future__ import annotations

import os
import re
import subprocess
from typing import Dict, List, Optional, Tuple

from minivideo_agents.executor import probe

from . import schema

LIMIAR_VISUAL = 0.35      # 0..1 — acima disso a fronteira é um "salto" visível
LIMIAR_LOUDNESS_DB = 6.0  # salto de loudness perceptível entre trechos


def _ffmpeg(args: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *args], capture_output=True, check=False)


def loudness(path: str, inicio: Optional[float] = None, duracao: Optional[float] = None) -> Optional[float]:
    args: List[str] = []
    if inicio is not None:
        args += ["-ss", f"{max(inicio, 0):.3f}"]
    args += ["-i", path]
    if duracao is not None:
        args += ["-t", f"{duracao:.3f}"]
    out = _ffmpeg(args + ["-vn", "-af", "ebur128", "-f", "null", "-"])
    m = re.findall(rb"I:\s+(-?[0-9.]+|-inf) LUFS", out.stderr)
    if not m or m[-1] == b"-inf":
        return None
    val = float(m[-1])
    return None if val <= -70 else val


def _quadro(path: str, fim: bool) -> Optional[bytes]:
    pos = ["-sseof", "-0.2"] if fim else ["-ss", "0"]
    out = _ffmpeg([*pos, "-i", path, "-frames:v", "1", "-vf", "scale=64:36,format=gray", "-f", "rawvideo", "-"])
    return out.stdout if len(out.stdout) == 64 * 36 else None


def diferenca_visual(a: str, b: str) -> Optional[float]:
    fa, fb = _quadro(a, fim=True), _quadro(b, fim=False)
    if fa is None or fb is None:
        return None
    return round(sum(abs(x - y) for x, y in zip(fa, fb)) / (255.0 * len(fa)), 4)


def medir(cena: str, path: str) -> Dict:
    info = probe(path)
    v = info["video"] or {}
    return {"cena": cena, "duracao_s": round(info["duracao"], 3),
            "largura": int(v["width"]) if v.get("width") else None,
            "altura": int(v["height"]) if v.get("height") else None,
            "fps": round(info["fps"], 3) if info["fps"] else None, "audio": info["audio"] is not None,
            "loudness_lufs": loudness(path) if info["audio"] else None}


def avaliar(trechos: List[Tuple[str, str]], final: Optional[str], diretor: Dict, montagem: Dict,
            artefatos: Optional[Dict] = None, reducoes: Optional[Dict] = None) -> Dict:
    """``reducoes``: tarefas que o Fiscal reduziu, por cena (explica critérios não atendidos)."""
    notas: List[str] = []
    if final is None or not os.path.exists(final):
        out = {"papel": "continuista", "versao": 1, "veredito": "reprovado", "trechos": [], "fronteiras": [],
               "criterios": [], "notas": ["saída final ausente"]}
        return schema.check("continuista", out)

    med = [medir(c, p) for c, p in trechos]
    med_final = medir("final", final)
    fronteiras = []
    for (ca, pa), (cb, pb), ma, mb in zip(trechos, trechos[1:], med, med[1:]):
        vis = diferenca_visual(pa, pb)
        la = loudness(pa, inicio=max(ma["duracao_s"] - 1.0, 0), duracao=1.0) if ma["audio"] else None
        lb = loudness(pb, inicio=0, duracao=1.0) if mb["audio"] else None
        salto = round(abs(la - lb), 2) if la is not None and lb is not None else None
        mesma_res = (ma["largura"], ma["altura"]) == (mb["largura"], mb["altura"])
        mesmo_fps = ma["fps"] is not None and mb["fps"] is not None and abs(ma["fps"] - mb["fps"]) < 0.01
        suave_visual = vis is None or vis <= LIMIAR_VISUAL or montagem.get("transicao") == "crossfade"
        ok = suave_visual and (salto is None or salto <= LIMIAR_LOUDNESS_DB) and ma["audio"] == mb["audio"]
        if not (mesma_res and mesmo_fps):
            notas.append(f"{ca}→{cb}: formatos diferentes; o montador normalizou resolução/fps na saída final")
        if not suave_visual:
            notas.append(f"{ca}→{cb}: salto visual {vis:.2f} (> {LIMIAR_VISUAL}); considere transição crossfade")
        if salto is not None and salto > LIMIAR_LOUDNESS_DB:
            notas.append(f"{ca}→{cb}: salto de loudness {salto:.1f} dB")
        if ma["audio"] != mb["audio"]:
            notas.append(f"{ca}→{cb}: um trecho tem áudio e o outro não")
        fronteiras.append({"entre": [ca, cb], "diferenca_visual": vis, "salto_loudness_db": salto,
                           "mesma_resolucao": mesma_res, "mesmo_fps": mesmo_fps, "ok": ok})

    por_cena = {m["cena"]: m for m in med}
    criterios = []
    for k in diretor["criterios"]:
        alvo_med = med_final if k["cena"] == "final" or len(trechos) == 1 else por_cena.get(k["cena"])
        medido, ok = None, False
        if alvo_med is not None:
            t = k["tipo"]
            if t == "duracao_s":
                medido = alvo_med["duracao_s"]
                ok = abs(medido - k["alvo"]) <= k["tolerancia"]
            elif t == "duracao_max_s":
                medido = alvo_med["duracao_s"]
                ok = medido <= k["alvo"] + k["tolerancia"]
            elif t == "altura":
                medido = alvo_med["altura"]
                ok = medido is not None and abs(medido - k["alvo"]) <= k["tolerancia"]
            elif t == "fps_min":
                medido = alvo_med["fps"]
                ok = medido is not None and medido >= k["alvo"] - k["tolerancia"]
            elif t == "loudness_lufs":
                medido = alvo_med["loudness_lufs"]
                ok = medido is not None and abs(medido - k["alvo"]) <= k["tolerancia"]
            elif t == "audio_presente":
                medido = med_final["audio"]
                ok = medido == k["alvo"]
            elif t == "legenda_presente":
                medido = bool((artefatos or {}).get("srt"))
                ok = medido == k["alvo"]
            elif t == "fronteira_suave":
                medido = all(f["ok"] for f in fronteiras)
                ok = medido == k["alvo"]
        criterios.append({"id": k["id"], "tipo": k["tipo"], "alvo": k["alvo"], "medido": medido, "ok": ok})

    veredito = "aprovado" if all(c["ok"] for c in criterios) and all(f["ok"] for f in fronteiras) else "ressalvas"
    cena_de = {k["id"]: k["cena"] for k in diretor["criterios"]}
    for c in criterios:
        if not c["ok"]:
            causa = ""
            red = (reducoes or {}).get(cena_de.get(c["id"]))
            if red and c["tipo"] in ("altura", "fps_min"):
                causa = f" — reduzido pelo Fiscal ({'; '.join(red['motivos'])})"
            notas.append(f"critério {c['id']} ({c['tipo']}) não atendido: alvo {c['alvo']}, medido {c['medido']}"
                         + causa)
    out = {"papel": "continuista", "versao": 1, "veredito": veredito,
           "trechos": med + ([med_final] if len(trechos) > 1 else []),
           "fronteiras": fronteiras, "criterios": criterios, "notas": notas[:60]}
    return schema.check("continuista", out)
