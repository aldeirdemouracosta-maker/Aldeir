"""Pipeline dos especialistas: Diretor → Editor → compilador → Fiscal → executor → Continuísta.

Os papéis produzem JSON validado. Só o compilador determinístico (aqui) e
o executor transformam JSON em comandos — sempre listas de argumentos de
ferramentas cadastradas, nunca shell. Cada job grava ``Jobs/<id>/job.json``
com tudo que é preciso para reproduzi-lo.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from minivideo_agents import devices as devmod
from minivideo_agents.executor import LIMITES_PADRAO, Executor, JobError, probe
from minivideo_agents.planner import Plan, validate_steps
from minivideo_agents.registry import route_all
from minivideo_agents.workspace import Workspace

from . import __version__, continuista, diretor as dir_mod, editor as ed_mod, fiscal as fis_mod, llm, schema

TOOL_DIRS = ["/usr/libexec/minivideo"]


class Recusado(RuntimeError):
    pass


@dataclass
class PlanoEspecialistas:
    job_id: str
    pedido: str
    modo: str
    entrada: Optional[Dict]
    diretor: Dict
    editor: Dict
    tarefas: List[Dict]
    fiscal: Dict
    limites: Dict
    llm: List[Dict] = field(default_factory=list)
    dispositivos: List[Dict] = field(default_factory=list)
    assignments: Dict = field(default_factory=dict, repr=False)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _descrever_entrada(entrada: str) -> Dict:
    info = probe(entrada)
    v = info["video"] or {}
    return {"caminho": os.path.abspath(entrada), "sha256": _sha256(entrada),
            "tamanho_mib": round(os.path.getsize(entrada) / 1048576, 3), "duracao": info["duracao"],
            "fps": info["fps"], "largura": v.get("width"), "altura": v.get("height"),
            "audio": info["audio"] is not None}


def compilar(editor: Dict) -> List[Dict]:
    """Operações do Editor → tarefas tipadas (mesma validação do planner)."""
    tarefas = []
    for op in editor["operacoes"]:
        step = validate_steps([{"agente": op["agente"], "params": op["params"]}])[0]
        tarefas.append({"cena": op["cena"], "agente": step.agente, "motor": op["motor"], "params": step.params})
    return tarefas


def planejar(pedido: str, entrada: Optional[str] = None, modo: str = "auto", ws: Optional[Workspace] = None,
             limites: Optional[Dict] = None, cliente: Optional[llm.ClienteLLM] = None, devices=None,
             gpu="auto", job_id: Optional[str] = None) -> PlanoEspecialistas:
    ws = ws or Workspace()
    devices = devices if devices is not None else devmod.detect()
    assignments = {a.agent.id: a for a in route_all(devices, ws.models_dirs, TOOL_DIRS)}
    lim = dict(LIMITES_PADRAO, **(limites or {}))
    ent = _descrever_entrada(entrada) if entrada else None
    info = None
    if ent:
        info = {"fps": ent["fps"], "audio": ent["audio"], "duracao": ent["duracao"],
                "tamanho_mib": ent["tamanho_mib"], "video": {"width": ent["largura"], "height": ent["altura"]}}
    if cliente is None and modo != "regras":
        try:
            cliente = llm.ClienteLLM()
        except llm.LLMIndisponivel:
            cliente = None
    registros: List[Dict] = []
    usuario_d = json.dumps({"pedido": pedido, "entrada": info}, ensure_ascii=False)
    d = llm.executar_papel("diretor", modo, lambda: dir_mod.diretor_regras(pedido, info), dir_mod.validar,
                           dir_mod.PROMPT_SISTEMA, usuario_d, cliente, registros)
    disponiveis = [{"agente": k, "motor": ed_mod._motor(k, a), "motivos": a.motivos}
                   for k, a in assignments.items() if a.disponivel]
    usuario_e = json.dumps({"diretor": d, "agentes_disponiveis": disponiveis}, ensure_ascii=False)
    e = llm.executar_papel("editor", modo, lambda: ed_mod.editor_regras(d, assignments),
                           lambda o: ed_mod.validar(o, d), ed_mod.PROMPT_SISTEMA, usuario_e, cliente, registros)
    tarefas = compilar(e)
    f = fis_mod.fiscalizar(tarefas, assignments, info, ws.jobs, lim, gpu)
    return PlanoEspecialistas(
        job_id=job_id or time.strftime("esp-%Y%m%d-%H%M%S"), pedido=pedido, modo=modo, entrada=ent,
        diretor=d, editor=e, tarefas=tarefas, fiscal=f, limites=lim, llm=registros,
        dispositivos=[{"id": x.id, "tipo": x.kind, "nome": x.name, "vram_mib": x.vram_mib, "usavel": x.usable}
                      for x in devices],
        assignments=assignments)


# ---------------- montagem ----------------

def montar(trechos: List[str], saida: str, montagem: Dict, limites: Dict) -> None:
    """Junta trechos normalizando resolução, fps e áudio (sem shell)."""
    infos = [probe(t) for t in trechos]
    # Alvo = maior resolução e maior fps entre os trechos: não desfaz upscale nem interpolação.
    maior = max(infos, key=lambda i: int(i["video"]["width"]) * int(i["video"]["height"]))
    w, h = int(maior["video"]["width"]), int(maior["video"]["height"])
    fps = max(i["fps"] or 0 for i in infos) or 30.0
    cmd: List[str] = ["ffmpeg", "-y", "-v", "error"]
    for t in trechos:
        cmd += ["-i", t]
    filtros, n = [], len(trechos)
    for i, info in enumerate(infos):
        filtros.append(f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=decrease,"
                       f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps:.6f},format=yuv420p[v{i}]")
        if info["audio"]:
            filtros.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}]")
        else:
            filtros.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{info['duracao']:.3f}[a{i}]")
    dur_x = float(montagem.get("duracao_transicao_s") or 0)
    if montagem.get("transicao") == "crossfade" and dur_x > 0:
        vprev, aprev, offset = "v0", "a0", 0.0
        for i in range(1, n):
            offset += infos[i - 1]["duracao"] - dur_x
            filtros.append(f"[{vprev}][v{i}]xfade=transition=fade:duration={dur_x}:offset={offset:.3f}[vx{i}]")
            filtros.append(f"[{aprev}][a{i}]acrossfade=d={dur_x}[ax{i}]")
            vprev, aprev = f"vx{i}", f"ax{i}"
        mapa = [f"[{vprev}]", f"[{aprev}]"]
    else:
        filtros.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[vout][aout]")
        mapa = ["[vout]", "[aout]"]
    cmd += ["-filter_complex", ";".join(filtros), "-map", mapa[0], "-map", mapa[1],
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", saida]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=limites["tempo_max_etapa_s"], check=False)
    if out.returncode != 0:
        raise JobError(f"montador: {out.stderr.strip()[-400:]}")


# ---------------- registro ----------------

def _versoes(assignments: Dict) -> Dict:
    def primeira_linha(cmd):
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False)
            return (out.stdout or out.stderr).strip().splitlines()[0][:200]
        except (OSError, IndexError, subprocess.TimeoutExpired):
            return None
    ferramentas = {}
    for k, a in assignments.items():
        if a.ferramenta and a.ferramenta not in ferramentas:
            st = os.stat(a.ferramenta)
            ferramentas[a.ferramenta] = {"tamanho": st.st_size, "mtime": int(st.st_mtime)}
    schemas = {}
    for nome in ("diretor", "editor", "fiscal", "continuista", "job"):
        with open(os.path.join(schema.SCHEMA_DIR, f"{nome}.schema.json"), "rb") as fh:
            schemas[nome] = hashlib.sha256(fh.read()).hexdigest()
    return {"minivideo": __version__, "python": sys.version.split()[0], "plataforma": platform.platform(),
            "ffmpeg": primeira_linha(["ffmpeg", "-version"]),
            "auto_editor": primeira_linha(["auto-editor", "--version"]) if shutil.which("auto-editor") else None,
            "ferramentas": ferramentas, "schemas_sha256": schemas}


def registro(plano: PlanoEspecialistas, saida: Optional[str], resultado: Dict,
             cont: Optional[Dict] = None) -> Dict:
    return {"formato": "minivideo-job/1", "job_id": plano.job_id,
            "criado_em": datetime.now(timezone.utc).isoformat(), "pedido": plano.pedido[:2000],
            "entrada": plano.entrada, "saida": os.path.abspath(saida) if saida else None,
            "modo_orquestrador": plano.modo, "llm": plano.llm, "diretor": plano.diretor, "editor": plano.editor,
            "tarefas": plano.tarefas, "fiscal": plano.fiscal, "continuista": cont, "limites": plano.limites,
            "versoes": _versoes(plano.assignments), "dispositivos": plano.dispositivos, "resultado": resultado}


def gravar_registro(ws: Workspace, reg: Dict, nome: str = "job.json") -> str:
    schema.check("job", reg)
    d = os.path.join(ws.jobs, reg["job_id"])
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, nome)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(reg, fh, ensure_ascii=False, indent=2)
    return path


# ---------------- execução ----------------

def executar(plano: PlanoEspecialistas, saida: str, ws: Optional[Workspace] = None,
             permitir_parcial: bool = False, guard: bool = True) -> Dict:
    ws = ws or Workspace()
    t0 = time.time()
    if plano.entrada is None:
        raise Recusado("este protótipo edita um vídeo de entrada; geração sem entrada exige CUDA (futuro)")
    if plano.fiscal["decisao"] == "suspender":
        reg = registro(plano, None, {"status": "recusado", "motivo": "Fiscal suspendeu",
                                     "detalhes": plano.fiscal["motivos"] +
                                     [m for t in plano.fiscal["tarefas"] for m in t["motivos"]]})
        gravar_registro(ws, reg)
        raise Recusado("Fiscal de hardware suspendeu a execução: " +
                       "; ".join(reg["resultado"]["detalhes"])[:600])
    if plano.editor["rejeitados"] and not permitir_parcial:
        motivos = [f"{r['cena']}/{r['objetivo']}: {r['motivo']}" for r in plano.editor["rejeitados"]]
        gravar_registro(ws, registro(plano, None, {"status": "recusado", "motivo": "plano parcial",
                                                   "detalhes": motivos}))
        raise Recusado("plano parcial (use --permitir-parcial): " + "; ".join(motivos)[:600])

    tarefas = fis_mod.aplicar_ajustes(plano.tarefas, plano.fiscal)
    ex = Executor(ws, plano.assignments, guard=guard, limites=plano.limites)
    cenas = [c["id"] for c in plano.diretor["cenas"] if any(t["cena"] == c["id"] for t in tarefas)]
    trechos, etapas, artefatos = [], [], {}
    job_dir = os.path.join(ws.jobs, plano.job_id)
    os.makedirs(job_dir, exist_ok=True)
    resultado: Dict = {"status": "falhou"}
    cont = None
    try:
        for cid in cenas:
            steps = validate_steps([{"agente": t["agente"], "params": t["params"]} for t in tarefas
                                    if t["cena"] == cid])
            destino = os.path.join(job_dir, f"{cid}.mp4")
            res = ex.run(Plan(plano.pedido, steps), plano.entrada["caminho"], destino, f"{plano.job_id}.{cid}")
            etapas.append({"cena": cid, "job": res.job_id, "ok": res.ok, "erro": res.erro,
                           "etapas": [e for e in res.etapas if "agente" in e]})
            artefatos.update(res.etapas[-1].get("artefatos", {}))
            if not res.ok:
                raise JobError(f"cena {cid}: {res.erro}")
            trechos.append((cid, destino))
        if len(trechos) > 1:
            montar([p for _, p in trechos], saida, plano.editor["montagem"], plano.limites)
        else:
            shutil.copyfile(trechos[0][1], saida)
        reducoes = {t["cena"]: t for t in plano.fiscal["tarefas"] if t["decisao"] == "reduzir"}
        cont = continuista.avaliar(trechos, saida, plano.diretor, plano.editor["montagem"], artefatos, reducoes)
        resultado = {"status": "concluido", "saida_sha256": _sha256(saida), "etapas": etapas,
                     "artefatos": artefatos, "segundos": round(time.time() - t0, 2)}
    except (JobError, OSError, subprocess.TimeoutExpired) as exc:
        resultado = {"status": "falhou", "erro": str(exc)[:1000], "etapas": etapas,
                     "segundos": round(time.time() - t0, 2)}
    reg = registro(plano, saida if resultado["status"] == "concluido" else None, resultado, cont)
    resultado["registro"] = gravar_registro(ws, reg)
    resultado["continuista"] = cont
    return resultado


def plano_de_registro(reg: Dict, ws: Workspace, sufixo: str = "rep") -> PlanoEspecialistas:
    """Reconstrói o plano gravado (sem LLM) para reproduzir o job na máquina atual."""
    schema.check("job", reg)
    dir_mod.validar(reg["diretor"])
    ed_mod.validar(reg["editor"], reg["diretor"])
    devices = devmod.detect()
    assignments = {a.agent.id: a for a in route_all(devices, ws.models_dirs, TOOL_DIRS)}
    entrada = reg["entrada"]
    if entrada is None or not os.path.exists(entrada["caminho"]):
        raise Recusado("entrada original não encontrada")
    if _sha256(entrada["caminho"]) != entrada["sha256"]:
        raise Recusado("a entrada mudou desde o job original (sha256 diferente)")
    tarefas = compilar(reg["editor"])
    fiscal = fis_mod.fiscalizar(tarefas, assignments, None, ws.jobs, reg["limites"])
    return PlanoEspecialistas(
        job_id=f"{reg['job_id']}-{sufixo}-{time.strftime('%H%M%S')}", pedido=reg["pedido"], modo="regras",
        entrada=entrada, diretor=reg["diretor"], editor=reg["editor"], tarefas=tarefas, fiscal=fiscal,
        limites=reg["limites"], llm=[{"papel": "reproducao", "origem": reg["job_id"]}],
        dispositivos=[{"id": x.id, "tipo": x.kind, "nome": x.name, "vram_mib": x.vram_mib, "usavel": x.usable}
                      for x in devices],
        assignments=assignments)
