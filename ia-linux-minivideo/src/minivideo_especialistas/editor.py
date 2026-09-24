"""Editor: cenas do Diretor → operações (agentes) e motores cadastrados (JSON).

Só usa agentes do registro e motores de ``motores.MOTORES`` compatíveis
com cada agente. Operação indisponível nesta máquina vai para
``rejeitados`` com o motivo real (ferramenta, pesos, driver, VRAM).
"""

from __future__ import annotations

import os
from typing import Dict, List

from minivideo_agents.planner import ORDER, validate_steps
from minivideo_agents.registry import Assignment

from . import motores, schema

OBJETIVO_AGENTE = {
    "cortar": "cortador", "remover_silencios": "silencios", "limpar_audio": "audio", "normalizar_audio": "audio",
    "detectar_cenas": "cenas", "interpolar": "interpolador", "camera_lenta": "interpolador",
    "upscale_ia": "upscaler", "escalar": "escala", "transcrever": "transcritor", "legendar": "legendas",
    "gerar_video": "gerador", "editar_generativo": "editor_generativo",
}
FERRAMENTA_MOTOR = {
    "ffmpeg": "ffmpeg", "auto-editor": "auto-editor", "whisper-cli": "whisper.cpp", "whisper-cpp": "whisper.cpp",
    "rife-ncnn-vulkan": "rife-ncnn-vulkan", "realesrgan-ncnn-vulkan": "realesrgan-ncnn-vulkan",
}
MOTOR_GENERATIVO_PADRAO = {"gerador": "wan2.1-vace-1.3b", "editor_generativo": "wan2.1-vace-1.3b"}


def _motor(agente: str, a: Assignment) -> str:
    if a is not None and a.ferramenta:
        m = FERRAMENTA_MOTOR.get(os.path.basename(a.ferramenta))
        if m:
            return m
    if agente in MOTOR_GENERATIVO_PADRAO:
        return MOTOR_GENERATIVO_PADRAO[agente]
    return motores.motores_para(agente)[0].id


def _params(agente: str, cena: Dict) -> Dict:
    p = cena.get("parametros", {})
    objs = cena["objetivos"]
    if agente == "cortador":
        return {"inicio": float(cena["inicio_s"]), "fim": float(cena["fim_s"])}
    if agente == "audio":
        return {"reduzir_ruido": "limpar_audio" in objs, "normalizar": True}
    if agente == "cenas":
        return {"limiar": 0.4}
    if agente == "interpolador":
        return {"fator": int(p.get("fator_quadros", 2)), "camera_lenta": "camera_lenta" in objs}
    if agente in ("upscaler", "escala"):
        return {"altura": int(p.get("altura", 1080))}
    if agente == "transcritor":
        return {"idioma": p.get("idioma", "pt")}
    if agente == "legendas":
        return {"embutir": True}
    if agente == "silencios":
        return {"margem_s": 0.2}
    if agente in ("gerador", "editor_generativo"):
        return {"prompt": p.get("prompt_generativo", cena["descricao"])[:1000]}
    if agente == "exportador":
        return {"crf": 20}
    return {}


def editor_regras(diretor: Dict, assignments: Dict[str, Assignment]) -> Dict:
    ops: List[Dict] = []
    rejeitados: List[Dict] = []
    for cena in diretor["cenas"]:
        agentes: Dict[str, str] = {}
        for obj in cena["objetivos"]:
            agentes.setdefault(OBJETIVO_AGENTE[obj], obj)
        if "transcritor" not in agentes and "legendas" in agentes:
            agentes["transcritor"] = "transcrever"
        rejeitados_cena: List[str] = []
        for agente in [a for a in ORDER if a in agentes]:
            a = assignments.get(agente)
            if agente == "legendas" and "transcritor" in rejeitados_cena:
                rejeitados_cena.append(agente)
                rejeitados.append({"cena": cena["id"], "objetivo": agentes[agente],
                                   "motivo": "depende do transcritor, que está indisponível"})
                continue
            if a is None or not a.disponivel:
                rejeitados_cena.append(agente)
                motivo = "; ".join(a.motivos) if a else "agente desconhecido"
                rejeitados.append({"cena": cena["id"], "objetivo": agentes[agente], "motivo": motivo[:300]})
                continue
            ops.append({"cena": cena["id"], "agente": agente, "motor": _motor(agente, a),
                        "params": _params(agente, cena)})
        if any(o["cena"] == cena["id"] for o in ops) or not rejeitados_cena:
            ops.append({"cena": cena["id"], "agente": "exportador", "motor": "ffmpeg", "params": {"crf": 20}})
    ops = _harmonizar_loudness(ops, diretor)
    out = {"papel": "editor", "versao": 1, "origem": "regras", "operacoes": ops, "rejeitados": rejeitados,
           "montagem": {"transicao": "corte", "duracao_transicao_s": 0}}
    return validar(out, diretor)


def _harmonizar_loudness(ops: List[Dict], diretor: Dict) -> List[Dict]:
    """Com mais de uma cena, se alguma normaliza o áudio, todas normalizam (-16 LUFS).

    Evita salto de volume na fronteira entre trechos (achado do Continuísta).
    """
    cenas = [c["id"] for c in diretor["cenas"]]
    if len(cenas) < 2 or not any(o["agente"] == "audio" for o in ops):
        return ops
    novas: List[Dict] = []
    for cid in cenas:
        cena_ops = [o for o in ops if o["cena"] == cid]
        if cena_ops and not any(o["agente"] == "audio" for o in cena_ops):
            pos = next((i for i, o in enumerate(cena_ops) if ORDER.index(o["agente"]) > ORDER.index("audio")),
                       len(cena_ops))
            cena_ops.insert(pos, {"cena": cid, "agente": "audio", "motor": "ffmpeg",
                                  "params": {"reduzir_ruido": False, "normalizar": True}})
        novas += cena_ops
    return novas


def validar(plano: Dict, diretor: Dict) -> Dict:
    """Schema + semântica: cena existe, motor aceita o agente, parâmetros tipados."""
    schema.check("editor", plano)
    ids = {c["id"] for c in diretor["cenas"]}
    erros: List[str] = []
    for i, op in enumerate(plano["operacoes"]):
        if op["cena"] not in ids:
            erros.append(f"#/operacoes/{i}: cena inexistente {op['cena']}")
        m = motores.BY_ID.get(op["motor"])
        if m is None or op["agente"] not in m.agentes:
            erros.append(f"#/operacoes/{i}: motor {op['motor']} não serve ao agente {op['agente']}")
        if op["agente"] == "montador":
            erros.append(f"#/operacoes/{i}: montagem é definida em 'montagem', não como operação")
            continue
        try:
            validate_steps([{"agente": op["agente"], "params": op["params"]}])
        except ValueError as exc:
            erros.append(f"#/operacoes/{i}: {exc}")
    for cid in ids:
        cena_ops = [o for o in plano["operacoes"] if o["cena"] == cid]
        if cena_ops and cena_ops[-1]["agente"] != "exportador":
            erros.append(f"cena {cid}: a última operação deve ser o exportador")
    if erros:
        raise schema.SchemaError(erros)
    return plano


PROMPT_SISTEMA = (
    "Você é o Editor de um editor de vídeo local. Recebe o plano do Diretor e a lista de agentes e "
    "motores disponíveis. Responda SOMENTE com JSON no schema fornecido. Use apenas agentes e motores "
    "listados como disponíveis; o que não puder ser feito vai em 'rejeitados' com o motivo. Cada cena "
    "termina com o agente 'exportador'. Não escreva comandos de terminal."
)
