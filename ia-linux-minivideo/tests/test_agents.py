import json
import os
import shutil
import stat
import time
import subprocess

import pytest

from minivideo_agents.devices import Device, classify
from minivideo_agents.executor import Executor, probe
from minivideo_agents.planner import explain, plan_rules, validate_steps
from minivideo_agents.registry import BY_ID, route, route_all
from minivideo_agents.workspace import Workspace

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg ausente")


def report(gpus=(), cuda=(), vk=(), avx2=False):
    return {
        "cpu": {"modelo": "Xeon E5-2630L v2", "instrucoes": {"avx": True, "avx2": avx2}},
        "gpus": list(gpus),
        "cuda": {"gpus": list(cuda)},
        "vulkan": {"estado": "presente" if any("llvmpipe" not in n for n in vk) else "x",
                   "dispositivos": [{"nome": n} for n in vk]},
    }


RX580 = {"card": "card0", "vendor": "0x1002", "device": "0x6fdf", "driver": "amdgpu",
         "nome": "AMD Polaris 20 XL (RX 580 2048SP)", "vram_mib": 8192}
APU = {"card": "card1", "vendor": "0x1002", "device": "0x1638", "driver": "amdgpu", "nome": None, "vram_mib": 512}
RTX16 = {"indice": "0", "nome": "NVIDIA RTX 4060 Ti", "vram_mib": 16380}
RTX8 = {"indice": "0", "nome": "NVIDIA RTX 3050", "vram_mib": 8192}


# ---------------- dispositivos ----------------

def test_classify_x79_rx580():
    devs = classify(report([RX580], vk=["AMD Radeon RX 580 (RADV POLARIS10)"]))
    assert [(d.id, d.kind, d.usable) for d in devs] == [("cpu", "cpu", True), ("amdgpu:card0", "vulkan-dgpu", True)]
    assert any("AVX2" in n for n in devs[0].notes)


def test_classify_mixed_apu_and_cuda():
    devs = classify(report([RX580, APU], [RTX16], vk=["RADV POLARIS10", "RADV RENOIR"]))
    kinds = {d.id: d.kind for d in devs}
    assert kinds == {"cpu": "cpu", "amdgpu:card0": "vulkan-dgpu", "amdgpu:card1": "vulkan-apu", "nvidia:0": "cuda"}
    apu = next(d for d in devs if d.kind == "vulkan-apu")
    assert "Cezanne" in apu.name and any("compartilhada" in n for n in apu.notes)


def test_amd_without_vulkan_or_amdgpu_is_unusable():
    no_vk = classify(report([RX580]))
    assert not no_vk[1].usable and any("Vulkan" in n for n in no_vk[1].notes)
    radeon = classify(report([dict(RX580, driver="radeon")], vk=["RADV"]))
    assert not radeon[1].usable and any("radeon" in n for n in radeon[1].notes)


def test_llvmpipe_only_when_no_real_gpu():
    devs = classify(report(vk=["llvmpipe (LLVM 20)"]))
    assert devs[-1].kind == "vulkan-sw"
    devs = classify(report([RX580], vk=["RADV POLARIS10", "llvmpipe"]))
    assert all(d.kind != "vulkan-sw" for d in devs)


# ---------------- roteamento ----------------

def _fake_tools(tmp_path, names):
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    for n in names:
        p = d / n
        p.write_text("#!/bin/sh\nexit 0\n")
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return [str(d)]


def test_generative_needs_cuda_12gb(tmp_path):
    paths = _fake_tools(tmp_path, ["mini-ia-videos"])
    x79 = classify(report([RX580], vk=["RADV POLARIS10"]))
    a = route(BY_ID["gerador"], x79, [], paths)
    assert not a.disponivel and any("CUDA" in m for m in a.motivos)
    small = classify(report([RX580], [RTX8], vk=["RADV"]))
    a = route(BY_ID["gerador"], small, [], paths)
    assert not a.disponivel and any("8192 MiB < 12000" in m for m in a.motivos)
    big = classify(report([RX580], [RTX16], vk=["RADV"]))
    a = route(BY_ID["gerador"], big, [], paths)
    assert a.disponivel and a.device.id == "nvidia:0" and any("futuro" in m for m in a.motivos)


def test_vulkan_agents_prefer_amd_dgpu_then_apu(tmp_path):
    models = tmp_path / "Modelos" / "rife" / "rife-v4.6"
    models.mkdir(parents=True)
    (models / "flownet.param").write_text("x")
    paths = _fake_tools(tmp_path, ["rife-ncnn-vulkan"])
    both = classify(report([APU, RX580], [RTX16], vk=["RADV"]))
    assert route(BY_ID["interpolador"], both, [str(tmp_path / "Modelos")], paths).device.id == "amdgpu:card0"
    only_apu = classify(report([APU], vk=["RADV"]))
    a = route(BY_ID["interpolador"], only_apu, [str(tmp_path / "Modelos")], paths)
    assert a.disponivel and a.device.kind == "vulkan-apu"  # VRAM dedicada pequena não bloqueia APU


def test_missing_weights_and_tool_are_explained(tmp_path):
    devs = classify(report([RX580], vk=["RADV"]))
    a = route(BY_ID["transcritor"], devs, [str(tmp_path)], [])
    assert not a.disponivel
    assert any("whisper" in m for m in a.motivos) and any("ggml" in m for m in a.motivos)


def test_whisper_falls_back_to_cpu_without_gpu(tmp_path):
    (tmp_path / "whisper").mkdir()
    (tmp_path / "whisper" / "ggml-small.bin").write_text("x")
    paths = _fake_tools(tmp_path, ["whisper-cli"])
    a = route(BY_ID["transcritor"], classify(report()), [str(tmp_path)], paths)
    assert a.disponivel and a.device.kind == "cpu" and any("lento" in m for m in a.motivos)


# ---------------- planejador ----------------

def test_plan_full_request_in_canonical_order():
    p = plan_rules("corte 00:00:15 até 00:00:30, retire os silêncios, coloque legendas e melhore para 1080p")
    assert [s.agente for s in p.etapas] == ["cortador", "silencios", "upscaler", "transcritor", "legendas", "exportador"]
    assert p.etapas[0].params == {"inicio": 15.0, "fim": 30.0}
    assert p.etapas[2].params["altura"] == 1080


def test_plan_remove_silence_is_not_generative_edit():
    """"remova os silêncios/o ruído" é edição comum; "remova o carro" é generativa (CUDA)."""
    def agentes(pedido):
        return [e.agente for e in plan_rules(pedido).etapas]
    assert "editor_generativo" not in agentes("remova os silêncios da entrevista e limpe o áudio")
    assert agentes("remova o ruído") == ["audio", "exportador"]
    assert agentes("remova as pausas") == ["silencios", "exportador"]
    assert "editor_generativo" in agentes("remova o carro do fundo")
    assert "editor_generativo" in agentes("troque o fundo por uma praia")


@pytest.mark.parametrize("pedido,agentes", [
    ("reduza o chiado", ["audio", "exportador"]),
    ("câmera lenta 4x", ["interpolador", "exportador"]),
    ("converta para 720p sem IA", ["escala", "exportador"]),
    ("troque o fundo por uma sala de aula", ["editor_generativo", "exportador"]),
    ("crie um vídeo de uma floresta", ["gerador", "exportador"]),
    ("detecte as cenas", ["cenas", "exportador"]),
])
def test_plan_variants(pedido, agentes):
    assert [s.agente for s in plan_rules(pedido).etapas] == agentes


def test_plan_invalid_cut_and_unknown_request():
    p = plan_rules("corte 00:00:30 até 00:00:10")
    assert not any(s.agente == "cortador" for s in p.etapas) and p.avisos
    p = plan_rules("faça algo bonito")
    assert p.etapas == [] and "nenhuma tarefa" in p.avisos[0]


def test_validate_steps_from_llm():
    steps = validate_steps([{"agente": "exportador", "params": {"crf": 22}},
                            {"agente": "cortador", "params": {"inicio": 1, "fim": 2.5}}])
    assert [s.agente for s in steps] == ["cortador", "exportador"]
    for bad in ([{"agente": "rm -rf"}], [{"agente": "cortador", "params": {"cmd": "x"}}],
                [{"agente": "exportador", "params": {"crf": "20"}}], [{"agente": "exportador", "params": {"crf": True}}]):
        with pytest.raises(ValueError):
            validate_steps(bad)


def test_explain_marks_blocked_steps():
    devs = classify(report([RX580], vk=["RADV"]))
    assigns = {a.agent.id: a for a in route_all(devs, [], [])}
    text = explain(plan_rules("crie um vídeo de gatos"), assigns)
    assert "INDISPONÍVEL" in text and "Bloqueado" in text and "Gerador de vídeo" in text


# ---------------- execução real com FFmpeg ----------------

@pytest.fixture
def ws(tmp_path):
    return Workspace(str(tmp_path / "ws"))


def make_video(path, seconds=4, audio=True):
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=10"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=300:sample_rate=48000"]
    cmd += ["-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p"]
    cmd += (["-c:a", "aac"] if audio else [])
    subprocess.run(cmd + [path], check=True)
    return path


def assigns_for(ws, tool_paths=()):
    devs = [Device("cpu", "cpu", "CPU")]
    return {a.agent.id: a for a in route_all(devs, ws.models_dirs, list(tool_paths))}


@needs_ffmpeg
def test_execute_cut_audio_scale_scenes(ws):
    src = make_video(os.path.join(ws.path("Midia"), "in.mp4"))
    plan = plan_rules("corte 00:00:01 até 00:00:03, limpe o áudio, detecte as cenas e converta para 180p sem IA")
    out = os.path.join(ws.path("Saidas"), "out.mp4")
    res = Executor(ws, assigns_for(ws), guard=False).run(plan, src, out, "t1")
    assert res.ok, res.erro
    info = probe(out)
    assert abs(info["duracao"] - 2.0) < 0.3 and info["altura"] == 180 and info["audio"]
    assert os.path.exists(os.path.join(ws.jobs, "t1", "cenas.csv"))
    log = [json.loads(line) for line in open(os.path.join(ws.logs, "t1.agentes.jsonl"))]
    assert log[0]["tipo"] == "inicio" and log[-1]["tipo"] == "fim" and log[-1]["ok"]


@needs_ffmpeg
def test_execute_subtitles_with_fake_whisper(ws, tmp_path):
    (tmp_path / "bin").mkdir()
    fake = tmp_path / "bin" / "whisper-cli"
    fake.write_text('#!/bin/sh\nwhile [ $# -gt 0 ]; do [ "$1" = "-of" ] && OF="$2"; shift; done\n'
                    'printf "1\\n00:00:00,000 --> 00:00:01,500\\nOlá mundo\\n" > "$OF.srt"\n')
    fake.chmod(0o755)
    os.makedirs(os.path.join(ws.path("Modelos"), "whisper"))
    open(os.path.join(ws.path("Modelos"), "whisper", "ggml-base.bin"), "w").close()
    src = make_video(os.path.join(ws.path("Midia"), "in.mp4"), 2)
    out = os.path.join(ws.path("Saidas"), "leg.mp4")
    res = Executor(ws, assigns_for(ws, [str(tmp_path / "bin")]), guard=False).run(
        plan_rules("coloque legendas"), src, out, "t2")
    assert res.ok, res.erro
    assert os.path.exists(os.path.join(ws.jobs, "t2", "legenda.srt")) and probe(out)["video"]


def test_refuses_plan_with_unavailable_step(ws):
    res = Executor(ws, assigns_for(ws), guard=False).run(plan_rules("crie um vídeo de gatos"), "/x.mp4", "/y.mp4", "t3")
    assert not res.ok and "gerador" in res.erro


@needs_ffmpeg
def test_audio_step_skips_silent_video(ws):
    src = make_video(os.path.join(ws.path("Midia"), "mudo.mp4"), 2, audio=False)
    res = Executor(ws, assigns_for(ws), guard=False).run(plan_rules("reduza o ruído"), src,
                                                         os.path.join(ws.path("Saidas"), "o.mp4"), "t4")
    assert res.ok and any("sem trilha" in n for n in res.etapas[-1]["notas"])


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("rife-ncnn-vulkan")
                         and os.environ.get("MINIVIDEO_TEST_RIFE_MODEL")),
                    reason="rife-ncnn-vulkan e MINIVIDEO_TEST_RIFE_MODEL não configurados")
def test_execute_rife_real(ws):
    shutil.copytree(os.environ["MINIVIDEO_TEST_RIFE_MODEL"], os.path.join(ws.path("Modelos"), "rife", "rife-v4.6"))
    devs = [Device("cpu", "cpu", "CPU"), Device("vulkan:llvmpipe", "vulkan-sw", "llvmpipe")]
    assigns = {a.agent.id: a for a in route_all(devs, ws.models_dirs, [])}
    src = make_video(os.path.join(ws.path("Midia"), "in.mp4"), 1)
    out = os.path.join(ws.path("Saidas"), "rife.mp4")
    res = Executor(ws, assigns, guard=False).run(plan_rules("mais quadros"), src, out, "t5")
    assert res.ok, res.erro
    assert round(probe(out)["fps"]) == 20
    log = [json.loads(line) for line in open(os.path.join(ws.logs, "t5.agentes.jsonl"))]
    onde = [e["onde"] for e in log if e["tipo"] == "quadros"]
    assert onde == ["ram"] if os.access("/dev/shm", os.W_OK) else onde == ["disco"]
    assert not os.path.exists("/dev/shm/minivideo-t5")  # RAM liberada no fim


def test_quadros_vao_para_o_disco_quando_nao_cabem_na_ram(ws):
    from minivideo_agents import executor as ex
    from minivideo_guard.monitor import JobLog
    e = Executor(ws, assigns_for(ws), guard=False)
    e.job_id, e.job_dir, e._pastas_ram = "t9", os.path.join(ws.jobs, "t9"), []
    os.makedirs(e.job_dir)
    e.log = JobLog(ws.logs, "t9", suffix="agentes")
    pequeno = {"video": {"width": 320, "height": 180}, "duracao": 1.0, "fps": 10.0}
    enorme = {"video": {"width": 3840, "height": 2160}, "duracao": 36000.0, "fps": 60.0}
    assert 0 < ex.estimar_quadros_mib(pequeno, 2) < 5
    assert e._base_quadros(enorme, 4, "upscaler") == e.job_dir
    if os.access("/dev/shm", os.W_OK):
        assert e._base_quadros(pequeno, 2, "interpolador") == "/dev/shm/minivideo-t9"
        os.rmdir("/dev/shm/minivideo-t9")
    e.limites = dict(e.limites, quadros_ram_fracao=0)
    assert e._base_quadros(pequeno, 2, "interpolador") == e.job_dir


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("auto-editor")), reason="auto-editor ausente")
def test_execute_remove_silence_real(ws):
    src = os.path.join(ws.path("Midia"), "sil.mp4")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=10",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1.5", "-filter_complex", "[1]apad=pad_dur=1.5[a]",
                    "-map", "0:v", "-map", "[a]", "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", src],
                   check=True)
    out = os.path.join(ws.path("Saidas"), "sem_silencio.mp4")
    res = Executor(ws, assigns_for(ws), guard=False).run(plan_rules("retire os silêncios"), src, out, "t6")
    assert res.ok, res.erro
    assert probe(out)["duracao"] < 2.5  # metade silenciosa removida


def test_limpar_jobs_antigos_mantem_registro(tmp_path, capsys):
    from minivideo_agents import cli, limpeza
    ws = Workspace(str(tmp_path / "ws"))
    velho = os.path.join(ws.jobs, "esp-velho")
    os.makedirs(os.path.join(velho, "quadros"))
    for nome, dados in (("job.json", b"{}"), ("c1.mp4", b"x" * 2048), ("quadros/00001.png", b"p" * 1024),
                        ("cenas.csv", b"a,b")):
        with open(os.path.join(velho, nome), "wb") as fh:
            fh.write(dados)
    novo = os.path.join(ws.jobs, "esp-novo")
    os.makedirs(novo)
    open(os.path.join(novo, "c1.mp4"), "wb").close()
    antigo = time.time() - 10 * 86400
    for raiz, dirs, arquivos in os.walk(velho):
        for n in dirs + arquivos + [""]:
            os.utime(os.path.join(raiz, n), (antigo, antigo))

    assert cli.main(["--workspace", ws.root, "limpar", "--dias", "7"]) == 0
    assert "Nada foi apagado" in capsys.readouterr().out
    assert os.path.exists(os.path.join(velho, "c1.mp4"))
    assert cli.main(["--workspace", ws.root, "limpar", "--dias", "7", "--confirmar"]) == 0
    assert sorted(os.listdir(velho)) == ["cenas.csv", "job.json"]  # quadros/ vazia foi removida
    assert os.path.exists(os.path.join(novo, "c1.mp4"))  # job recente intocado
    assert limpeza.planejar(ws.jobs, 7) == []


def test_default_root_usa_o_env_da_sessao(tmp_path, monkeypatch):
    from minivideo_agents import workspace as w
    env = tmp_path / "minivideo.env"
    env.write_text("MINIVIDEO_HOME=/data/minivideo\n")
    monkeypatch.delenv("MINIVIDEO_HOME", raising=False)
    monkeypatch.setattr(w, "SESSAO_ENV", str(env))
    assert w.default_root() == "/data/minivideo"
    monkeypatch.setenv("MINIVIDEO_HOME", "/outro")
    assert w.default_root() == "/outro"
