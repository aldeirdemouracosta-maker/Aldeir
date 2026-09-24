import copy
import http.server
import json
import os
import re
import shutil
import subprocess
import threading

import pytest

from minivideo_agents.devices import Device
from minivideo_agents.registry import route_all
from minivideo_agents.workspace import Workspace
from minivideo_especialistas import continuista, diretor, editor, fiscal, llm, motores, pipeline, schema

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg ausente")
SRC = os.path.join(os.path.dirname(__file__), "..", "src")
CPU = [Device("cpu", "cpu", "CPU")]


def assigns(ws, devices=CPU, tool_paths=()):
    return {a.agent.id: a for a in route_all(devices, ws.models_dirs, list(tool_paths))}


@pytest.fixture
def ws(tmp_path):
    return Workspace(str(tmp_path / "ws"))


def video(path, seconds=4, freq=440, volume=1.0, size="160x90", rate=10, audio=True):
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate={rate}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency={freq}:sample_rate=48000", "-af", f"volume={volume}"]
    cmd += ["-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p"] + (["-c:a", "aac"] if audio else [])
    subprocess.run(cmd + [path], check=True)
    return path


# ---------------- validador de schema ----------------

def test_schemas_load_and_reject_unknown_keywords(tmp_path, monkeypatch):
    for n in ("diretor", "editor", "fiscal", "continuista", "job"):
        assert schema.load(n)["$schema"].endswith("2020-12/schema")
    bad = tmp_path / "x.schema.json"
    bad.write_text(json.dumps({"type": "object", "if": {}}))
    monkeypatch.setattr(schema, "SCHEMA_DIR", str(tmp_path))
    schema._CACHE.pop("x", None)
    with pytest.raises(ValueError, match="não suportadas"):
        schema.load("x")


def test_validator_core_rules():
    s = {"type": "object", "additionalProperties": False, "required": ["a"],
         "properties": {"a": {"type": "integer", "minimum": 1}, "b": {"enum": ["x"]},
                        "c": {"type": "string", "pattern": "^c[0-9]$"},
                        "d": {"type": "array", "maxItems": 1, "items": {"$ref": "#/$defs/n"}}},
         "$defs": {"n": {"type": "number"}}}
    schema.validate({"a": 2, "b": "x", "c": "c1", "d": [1.5]}, s)
    for bad in ({}, {"a": 0}, {"a": True}, {"a": 1, "z": 1}, {"a": 1, "b": "y"}, {"a": 1, "c": "c10"},
                {"a": 1, "d": [1, 2]}, {"a": 1, "d": ["x"]}):
        with pytest.raises(schema.SchemaError):
            schema.validate(bad, s)


# ---------------- Diretor ----------------

def test_diretor_single_scene_and_criteria():
    d = diretor.diretor_regras("corte 00:00:15 até 00:00:30, retire os silêncios e melhore para 1080p",
                               {"fps": 30, "audio": True})
    assert [c["id"] for c in d["cenas"]] == ["c1"]
    c = d["cenas"][0]
    assert (c["inicio_s"], c["fim_s"]) == (15.0, 30.0)
    assert set(c["objetivos"]) == {"cortar", "remover_silencios", "upscale_ia"}
    tipos = {(k["tipo"], k["alvo"]) for k in d["criterios"]}
    assert ("duracao_max_s", 15.0) in tipos and ("altura", 1080) in tipos and ("audio_presente", True) in tipos


def test_diretor_multi_scene_with_global_objective():
    d = diretor.diretor_regras("cena 1: 00:00:00 até 00:00:02 limpe o áudio; "
                               "cena 2: 00:00:05 até 00:00:07 câmera lenta; coloque legendas",
                               {"fps": 25, "audio": True})
    assert [c["id"] for c in d["cenas"]] == ["c1", "c2"]
    assert all("legendar" in c["objetivos"] for c in d["cenas"])
    assert "camera_lenta" in d["cenas"][1]["objetivos"]
    dur_c2 = next(k for k in d["criterios"] if k["cena"] == "c2" and k["tipo"] == "duracao_s")
    assert dur_c2["alvo"] == 4.0  # 2 s em câmera lenta 2x
    assert any(k["tipo"] == "fronteira_suave" for k in d["criterios"])


def test_diretor_semantic_validation():
    d = diretor.diretor_regras("limpe o áudio")
    bad = copy.deepcopy(d)
    bad["cenas"].append(dict(bad["cenas"][0]))
    with pytest.raises(schema.SchemaError, match="repetidos"):
        diretor.validar(bad)
    bad = copy.deepcopy(d)
    bad["cenas"][0].update(inicio_s=5, fim_s=2)
    with pytest.raises(schema.SchemaError):
        diretor.validar(bad)
    bad = copy.deepcopy(d)
    bad["criterios"].append({"id": "k9", "cena": "c7", "tipo": "altura", "alvo": 720, "tolerancia": 0})
    with pytest.raises(schema.SchemaError, match="inexistente"):
        diretor.validar(bad)
    bad = copy.deepcopy(d)
    bad["cenas"][0]["objetivos"] = ["apagar_disco"]
    with pytest.raises(schema.SchemaError):
        diretor.validar(bad)


# ---------------- Editor ----------------

def test_editor_uses_only_registered_and_available(ws):
    d = diretor.diretor_regras("cena 1: 00:00:00 até 00:00:02 limpe o áudio; cena 2: 00:00:03 até 00:00:05 "
                               "coloque legendas e crie um vídeo novo", {"audio": True, "fps": 10})
    e = editor.editor_regras(d, assigns(ws))
    for op in e["operacoes"]:
        assert op["agente"] in motores.BY_ID[op["motor"]].agentes
    rej = {(r["cena"], r["objetivo"]) for r in e["rejeitados"]}
    assert ("c2", "transcrever") in rej and ("c2", "legendar") in rej and ("c2", "gerar_video") in rej
    assert any("CUDA" in r["motivo"] for r in e["rejeitados"] if r["objetivo"] == "gerar_video")
    # harmonização: c2 também normaliza o áudio (continuidade de loudness)
    assert any(o["cena"] == "c2" and o["agente"] == "audio" for o in e["operacoes"])


def test_editor_rejects_bad_llm_style_output(ws):
    d = diretor.diretor_regras("corte 00:00:01 até 00:00:02")
    base = editor.editor_regras(d, assigns(ws))
    casos = [
        ("motor incompatível", lambda e: e["operacoes"][0].update(motor="realesrgan-ncnn-vulkan")),
        ("agente inexistente", lambda e: e["operacoes"][0].update(agente="shell")),
        ("parâmetro com comando", lambda e: e["operacoes"][0]["params"].update(inicio="0; rm -rf /")),
        ("parâmetro extra", lambda e: e["operacoes"][0]["params"].update(cmd="ls")),
        ("cena inexistente", lambda e: e["operacoes"][0].update(cena="c9")),
        ("sem exportador no fim", lambda e: e["operacoes"].pop()),
        ("montador como operação", lambda e: e["operacoes"].insert(0, {"cena": "c1", "agente": "montador",
                                                                        "motor": "ffmpeg", "params": {}})),
    ]
    for nome, mutacao in casos:
        e = copy.deepcopy(base)
        mutacao(e)
        with pytest.raises(schema.SchemaError):
            editor.validar(e, d)


# ---------------- Fiscal ----------------

def _tarefas(ws, pedido, devices=CPU, info=None):
    d = diretor.diretor_regras(pedido, info)
    a = assigns(ws, devices)
    e = editor.editor_regras(d, a)
    return pipeline.compilar(e), a


def test_fiscal_approves_cpu_plan(ws):
    t, a = _tarefas(ws, "corte 00:00:01 até 00:00:02 e limpe o áudio")
    f = fiscal.fiscalizar(t, a, None, ws.jobs, gpu=None)
    assert f["decisao"] == "aprovar" and all(x["decisao"] == "aprovar" for x in f["tarefas"])


def _gpu_dev():
    return [Device("cpu", "cpu", "CPU"), Device("amdgpu:card0", "vulkan-dgpu", "RX 580", 8192, "amdgpu")]


def _gpu_assigns(ws, tmp_path):
    base = tmp_path / "Modelos" / "realesrgan" / "models"
    base.mkdir(parents=True)
    (base / "realesr-animevideov3-x2.param").write_text("7767517")
    b = tmp_path / "bin"
    b.mkdir()
    (b / "realesrgan-ncnn-vulkan").write_text("#!/bin/sh\n")
    (b / "realesrgan-ncnn-vulkan").chmod(0o755)
    return {x.agent.id: x for x in route_all(_gpu_dev(), [str(tmp_path / "Modelos")], [str(b)])}


@pytest.mark.parametrize("nivel,num,esperado", [("reduzir", 2, "reduzir"), ("pausar", 3, "suspender"),
                                                ("critico", 4, "suspender")])
def test_fiscal_reacts_to_gpu_level(ws, tmp_path, nivel, num, esperado):
    a = _gpu_assigns(ws, tmp_path)
    d = diretor.diretor_regras("melhore para 1080p")
    t = pipeline.compilar(editor.editor_regras(d, a))
    gpu = {"dispositivo": "amdgpu:card0", "temp_edge_c": 86.0, "vram_usada_mib": 100, "nivel": nivel,
           "nivel_num": num, "motivos": ["temp_edge_c=86"]}
    f = fiscal.fiscalizar(t, a, None, ws.jobs, gpu=gpu)
    up = next(x for x in f["tarefas"] if x["agente"] == "upscaler")
    assert f["decisao"] == esperado and up["decisao"] == esperado
    if esperado == "reduzir":
        assert up["ajustes"] == {"altura": 720}
        novas = fiscal.aplicar_ajustes(t, f)
        assert next(x for x in novas if x["agente"] == "upscaler")["params"]["altura"] == 720


def test_fiscal_disk_and_unavailable(ws, monkeypatch):
    t, a = _tarefas(ws, "corte 00:00:01 até 00:00:02")
    monkeypatch.setattr(fiscal.shutil, "disk_usage", lambda p: type("U", (), {"free": 100 * 1048576})())
    f = fiscal.fiscalizar(t, a, None, ws.jobs, gpu=None)
    assert f["decisao"] == "suspender" and any("disco insuficiente" in m for m in f["motivos"])
    t2, a2 = _tarefas(ws, "crie um vídeo de uma praia")
    assert pipeline.compilar(editor.editor_regras(diretor.diretor_regras("crie um vídeo"), a2)) == []


def test_fiscal_never_increases_load():
    tarefas = [{"cena": "c1", "agente": "upscaler", "motor": "realesrgan-ncnn-vulkan", "params": {"altura": 480}}]
    f = {"tarefas": [{"decisao": "reduzir", "ajustes": {"altura": 1080}}]}
    assert fiscal.aplicar_ajustes(tarefas, f)[0]["params"]["altura"] == 480


# ---------------- LLM (servidor local falso) ----------------

class _Fake(http.server.BaseHTTPRequestHandler):
    respostas = []
    pedidos = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Fake.pedidos.append(body)
        content = _Fake.respostas.pop(0)
        data = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


@pytest.fixture
def fake_llm():
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Fake)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    _Fake.respostas, _Fake.pedidos = [], []
    yield f"http://127.0.0.1:{srv.server_port}/v1"
    srv.shutdown()


def test_llm_valid_json_is_used_and_logged(ws, fake_llm):
    d = diretor.diretor_regras("limpe o áudio")
    d_llm = dict(d, origem="llm")
    e = editor.editor_regras(d, assigns(ws))
    _Fake.respostas = ["```json\n" + json.dumps(d_llm) + "\n```", json.dumps(e)]
    cli = llm.ClienteLLM(fake_llm, "Qwen3-1.7B", 5)
    pl = pipeline.planejar("limpe o áudio", None, "qwen", ws, cliente=cli, devices=CPU, gpu=None)
    assert pl.diretor["origem"] == "llm" and pl.editor["origem"] == "llm"
    assert len(pl.llm) == 2 and all(r["erro"] is None for r in pl.llm)
    body = _Fake.pedidos[0]
    assert body["temperature"] == 0 and body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"]["title"] == "Diretor"


def test_llm_invalid_output_falls_back_in_auto_and_fails_in_qwen(ws, fake_llm):
    malicioso = json.dumps({"papel": "diretor", "versao": 1, "pedido": "x", "origem": "llm",
                            "cenas": [{"id": "c1", "descricao": "rm -rf /", "inicio_s": None, "fim_s": None,
                                       "objetivos": ["executar_shell"]}], "criterios": [], "avisos": []})
    _Fake.respostas = [malicioso, "isto não é JSON"]
    cli = llm.ClienteLLM(fake_llm, "Qwen3-0.6B", 5)
    pl = pipeline.planejar("limpe o áudio", None, "auto", ws, cliente=cli, devices=CPU, gpu=None)
    assert pl.diretor["origem"] == "regras" and pl.editor["origem"] == "regras"
    assert "schema" in pl.llm[0]["erro"] and pl.llm[0]["fallback"] == "regras"
    _Fake.respostas = [malicioso]
    with pytest.raises(llm.LLMIndisponivel):
        pipeline.planejar("limpe o áudio", None, "qwen", ws, cliente=cli, devices=CPU, gpu=None)


def test_llm_refuses_non_local_url():
    with pytest.raises(llm.LLMIndisponivel, match="não é local"):
        llm.ClienteLLM("https://api.exemplo.com/v1")


# ---------------- pipeline real (sem CUDA) ----------------

@needs_ffmpeg
def test_dry_run_complete_writes_valid_plan(ws):
    src = video(os.path.join(ws.path("Midia"), "in.mp4"))
    pl = pipeline.planejar("cena 1: 00:00:00 até 00:00:01 limpe o áudio; cena 2: 00:00:02 até 00:00:03 "
                           "converta para 180p sem IA; coloque legendas", src, "regras", ws, devices=CPU, gpu=None)
    reg = pipeline.registro(pl, None, {"status": "simulado"})
    path = pipeline.gravar_registro(ws, reg, "plano.json")
    data = json.load(open(path))
    schema.check("job", data)
    assert data["entrada"]["sha256"] and data["versoes"]["schemas_sha256"]["diretor"]
    assert [t["agente"] for t in data["tarefas"] if t["cena"] == "c2"] == ["cortador", "audio", "escala", "exportador"]
    assert {r["objetivo"] for r in data["editor"]["rejeitados"]} == {"transcrever", "legendar"}
    assert not os.listdir(ws.path("Saidas"))  # nada executado


@needs_ffmpeg
def test_execute_two_scenes_continuity_and_reproduce(ws):
    src = os.path.join(ws.path("Midia"), "in.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=10",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000", "-filter_complex",
                    "[1]volume=enable='gte(t,2)':volume=0.05[a]", "-map", "0:v", "-map", "[a]", "-t", "4",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", src], check=True)
    pedido = "cena 1: 00:00:00 até 00:00:01.5 limpe o áudio; cena 2: 00:00:02 até 00:00:03.5 converta para 180p sem IA"
    pl = pipeline.planejar(pedido, src, "regras", ws, devices=CPU, gpu=None, job_id="t-duas-cenas")
    out = os.path.join(ws.path("Saidas"), "final.mp4")
    res = pipeline.executar(pl, out, ws)
    assert res["status"] == "concluido", res
    c = res["continuista"]
    schema.check("continuista", c)
    ks = {k["tipo"]: k for k in c["criterios"] if k["tipo"] in ("loudness_lufs", "fronteira_suave", "altura")}
    assert ks["loudness_lufs"]["ok"] and ks["altura"]["ok"]
    # sem harmonização a cena 2 (volume 0,05) daria um salto grande; com ela a fronteira fica suave
    assert c["fronteiras"][0]["salto_loudness_db"] < 6 and ks["fronteira_suave"]["ok"]
    reg = json.load(open(res["registro"]))
    schema.check("job", reg)
    pl2 = pipeline.plano_de_registro(reg, ws)
    res2 = pipeline.executar(pl2, os.path.join(ws.path("Saidas"), "rep.mp4"), ws)
    assert res2["status"] == "concluido" and res2["saida_sha256"] == reg["resultado"]["saida_sha256"]


@needs_ffmpeg
def test_continuista_flags_loudness_jump_and_missing_output(ws, tmp_path):
    a = video(str(tmp_path / "a.mp4"), 2, volume=1.0)
    b = video(str(tmp_path / "b.mp4"), 2, volume=0.02)
    d = diretor.diretor_regras("cena 1: 00:00:00 até 00:00:02 corte; cena 2: 00:00:02 até 00:00:04 corte")
    final = str(tmp_path / "f.mp4")
    pipeline.montar([a, b], final, {"transicao": "corte", "duracao_transicao_s": 0}, {"tempo_max_etapa_s": 60})
    c = continuista.avaliar([("c1", a), ("c2", b)], final, d, {"transicao": "corte"})
    assert c["fronteiras"][0]["salto_loudness_db"] > 20 and not c["fronteiras"][0]["ok"]
    assert c["veredito"] == "ressalvas"
    assert continuista.avaliar([], None, d, {})["veredito"] == "reprovado"


@needs_ffmpeg
def test_crossfade_montage(tmp_path):
    a = video(str(tmp_path / "a.mp4"), 2)
    b = video(str(tmp_path / "b.mp4"), 2, size="320x180")
    out = str(tmp_path / "x.mp4")
    pipeline.montar([a, b], out, {"transicao": "crossfade", "duracao_transicao_s": 0.5}, {"tempo_max_etapa_s": 60})
    from minivideo_agents.executor import probe
    info = probe(out)
    assert abs(info["duracao"] - 3.5) < 0.2 and info["altura"] == 180


def test_refuses_when_fiscal_suspends_or_plan_partial(ws, tmp_path):
    src = str(tmp_path / "in.mp4")
    open(src, "wb").close()
    pl = pipeline.PlanoEspecialistas(
        job_id="t-recusa", pedido="x", modo="regras", entrada={"caminho": src, "sha256": "0"},
        diretor=diretor.diretor_regras("limpe o áudio"), editor={"rejeitados": [], "operacoes": [],
                                                                 "montagem": {}},
        tarefas=[], fiscal={"decisao": "suspender", "motivos": ["GPU quente"], "tarefas": []},
        limites={}, assignments={})
    with pytest.raises(pipeline.Recusado, match="suspendeu"):
        pipeline.executar(pl, str(tmp_path / "o.mp4"), ws)


# ---------------- segurança do código ----------------

def test_no_shell_execution_anywhere():
    proibidos = re.compile(r"shell\s*=\s*True|os\.system\(|os\.popen\(|\beval\(|\bexec\(")
    for root, _, files in os.walk(SRC):
        for f in files:
            if f.endswith(".py"):
                texto = open(os.path.join(root, f), encoding="utf-8").read()
                assert not proibidos.search(texto), f"{f} usa execução por shell/eval"


def test_model_manager_has_no_network_code():
    for f in os.listdir(os.path.join(SRC, "minivideo_modelos")):
        if f.endswith(".py"):
            texto = open(os.path.join(SRC, "minivideo_modelos", f), encoding="utf-8").read()
            assert not re.search(r"import (urllib|socket|http|requests)|from (urllib|http) ", texto), f
