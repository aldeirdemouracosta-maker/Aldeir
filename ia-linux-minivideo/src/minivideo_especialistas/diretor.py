"""Diretor: pedido em linguagem natural → cenas + critérios de aceitação (JSON).

Não escolhe motores nem comandos. Saída sempre validada por
``schemas/diretor.schema.json`` e por checagens semânticas.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional

from minivideo_agents.planner import TIME, _norm, _seconds, plan_rules

from . import schema

AGENTE_OBJETIVO = {
    "cortador": "cortar", "silencios": "remover_silencios", "cenas": "detectar_cenas",
    "interpolador": "interpolar", "upscaler": "upscale_ia", "escala": "escalar",
    "transcritor": "transcrever", "legendas": "legendar", "gerador": "gerar_video",
    "editor_generativo": "editar_generativo",
}
SEPARADORES = r"\bcena\s*\d+\s*:|;|\b(?:depois|em seguida|entao|e por fim|por fim)\b"


def _objetivos(texto: str) -> (List[str], Dict):
    """Objetivos e parâmetros de um trecho do pedido (reusa o planner por regras)."""
    plano = plan_rules(texto)
    objs: List[str] = []
    params: Dict = {}
    for step in plano.etapas:
        a = step.agente
        if a == "exportador":
            continue
        if a == "audio":
            objs.append("limpar_audio" if step.params.get("reduzir_ruido") else "normalizar_audio")
            continue
        if a in AGENTE_OBJETIVO and a != "cortador":
            objs.append(AGENTE_OBJETIVO[a])
        if a == "interpolador":
            params["fator_quadros"] = step.params.get("fator", 2)
            if step.params.get("camera_lenta"):
                objs.append("camera_lenta")
        if a in ("upscaler", "escala"):
            params["altura"] = step.params.get("altura", 1080)
        if a == "transcritor":
            params["idioma"] = step.params.get("idioma", "pt")
        if a in ("gerador", "editor_generativo"):
            params["prompt_generativo"] = texto.strip()[:1000]
    return objs, params


def _faixas(texto: str) -> List[tuple]:
    t = _norm(texto)
    return [(_seconds(a), _seconds(b)) for a, b in re.findall(rf"{TIME}\s*(?:ate|a|-|–)\s*{TIME}", t)]


def diretor_regras(pedido: str, info: Optional[Dict] = None) -> Dict:
    """``info`` (opcional) = ffprobe da entrada: fps, duração, áudio."""
    avisos: List[str] = []
    partes = [p.strip(" ,.") for p in re.split(SEPARADORES, _norm(pedido)) if p and p.strip(" ,.")]
    partes_orig = partes or [_norm(pedido)]
    cenas: List[Dict] = []
    globais: List[str] = []
    gparams: Dict = {}
    for parte in partes_orig:
        faixas = _faixas(parte)
        objs, params = _objetivos(parte)
        if faixas:
            for ini, fim in faixas:
                if fim <= ini:
                    avisos.append(f"trecho {ini:.1f}–{fim:.1f} s ignorado: fim antes do início")
                    continue
                cenas.append({"descricao": parte[:300], "inicio_s": ini, "fim_s": fim,
                              "objetivos": ["cortar"] + objs, "parametros": params})
        else:
            globais += objs
            gparams.update(params)
    if not cenas:
        cenas = [{"descricao": _norm(pedido)[:300], "inicio_s": None, "fim_s": None, "objetivos": [],
                  "parametros": {}}]
    for i, c in enumerate(cenas, 1):
        c["id"] = f"c{i}"
        for o in globais:
            if o not in c["objetivos"]:
                c["objetivos"].append(o)
        c["parametros"] = {**gparams, **c["parametros"]}
        if not c["parametros"]:
            del c["parametros"]
    if all(not c["objetivos"] for c in cenas):
        avisos.append("nenhuma operação reconhecida; reformule (ex.: 'retire os silêncios e coloque legendas')")

    criterios = _criterios(cenas, info)
    out = {"papel": "diretor", "versao": 1, "pedido": pedido[:2000], "origem": "regras",
           "cenas": cenas, "criterios": criterios, "avisos": avisos}
    return validar(out)


def _criterios(cenas: List[Dict], info: Optional[Dict]) -> List[Dict]:
    crit: List[Dict] = []

    def add(cena, tipo, alvo, tol):
        crit.append({"id": f"k{len(crit) + 1}", "cena": cena, "tipo": tipo, "alvo": alvo, "tolerancia": tol})

    fps_in = (info or {}).get("fps")
    tem_audio = bool((info or {}).get("audio"))
    for c in cenas:
        objs, p = c["objetivos"], c.get("parametros", {})
        if c["inicio_s"] is not None:
            dur = c["fim_s"] - c["inicio_s"]
            if "remover_silencios" in objs:
                add(c["id"], "duracao_max_s", round(dur, 3), 0.25)
            elif "camera_lenta" in objs:
                add(c["id"], "duracao_s", round(dur * p.get("fator_quadros", 2), 3), 0.5)
            elif not ({"gerar_video", "editar_generativo"} & set(objs)):
                add(c["id"], "duracao_s", round(dur, 3), 0.25)
        if {"upscale_ia", "escalar"} & set(objs):
            add(c["id"], "altura", p.get("altura", 1080), 0)
        if "interpolar" in objs and "camera_lenta" not in objs and fps_in:
            add(c["id"], "fps_min", round(fps_in * p.get("fator_quadros", 2) * 0.98, 2), 0)
        if {"limpar_audio", "normalizar_audio"} & set(objs) and tem_audio:
            add(c["id"], "loudness_lufs", -16, 2)
        if "legendar" in objs:
            add(c["id"], "legenda_presente", True, 0)
    if tem_audio and not any("camera_lenta" in c["objetivos"] for c in cenas):
        add("final", "audio_presente", True, 0)
    if len(cenas) > 1:
        add("final", "fronteira_suave", True, 0)
    return crit


def validar(plano: Dict) -> Dict:
    schema.check("diretor", plano)
    ids = [c["id"] for c in plano["cenas"]]
    if len(set(ids)) != len(ids):
        raise schema.SchemaError(["#/cenas: ids de cena repetidos"])
    for c in plano["cenas"]:
        if (c["inicio_s"] is None) != (c["fim_s"] is None):
            raise schema.SchemaError([f"#/cenas/{c['id']}: início e fim devem vir juntos"])
        if c["inicio_s"] is not None and c["fim_s"] <= c["inicio_s"]:
            raise schema.SchemaError([f"#/cenas/{c['id']}: fim deve ser maior que o início"])
    for k in plano["criterios"]:
        if k["cena"] != "final" and k["cena"] not in ids:
            raise schema.SchemaError([f"#/criterios/{k['id']}: cena inexistente {k['cena']}"])
    return plano


PROMPT_SISTEMA = (
    "Você é o Diretor de um editor de vídeo local. Responda SOMENTE com um objeto JSON que obedeça ao "
    "schema fornecido. Divida o pedido em cenas (id c1, c2, ...), com início e fim em segundos quando o "
    "pedido indicar tempos, e liste objetivos apenas do enum permitido. Defina critérios de aceitação "
    "mensuráveis. Não escolha programas, não escreva comandos e não invente recursos."
)
