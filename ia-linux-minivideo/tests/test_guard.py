import builtins
import json
import os
import subprocess
import sys
import time

import pytest

from conftest import make_polaris, set_temp
from minivideo_guard import cli
from minivideo_guard.actions import ActionDispatcher, CallbackJobControl, ProcessJobControl
from minivideo_guard.monitor import GuardMonitor, JobLog
from minivideo_guard.policy import (ATENCAO, CRITICO, NORMAL, PAUSAR, REDUZIR, GuardPolicy, load_config)
from minivideo_guard.sensors import AmdgpuSysfsBackend, Reading, empty_metrics, parse_nvidia_smi_csv


def reading(**metrics):
    m = empty_metrics()
    m.update(metrics)
    return Reading("fake:0", "fake", time.time(), m)


# ---------------- sensores ----------------

def test_discover_polaris_ignores_connectors(polaris):
    root, _ = polaris
    devs = AmdgpuSysfsBackend(os.path.join(root, "sys")).discover()
    assert [d.id for d in devs] == ["amdgpu:card0"]
    assert devs[0].driver == "amdgpu" and devs[0].pci_device == "0x6fdf"
    assert devs[0].pci_slot == "0000:03:00.0"


def test_read_polaris_values_and_missing_hotspot(polaris):
    root, _ = polaris
    b = AmdgpuSysfsBackend(os.path.join(root, "sys"))
    r = b.read(b.discover()[0])
    m = r.metrics
    assert m["temp_edge_c"] == 60.0
    assert m["load_pct"] == 97 and m["vram_used_mib"] == 512 and m["vram_total_mib"] == 8192
    assert m["power_w"] == 90.0 and m["power_cap_w"] == 185.0
    assert m["fan_rpm"] == 1200 and m["fan_pct"] == pytest.approx(50.2, abs=0.1)
    assert m["sclk_mhz"] == 1340 and m["mclk_mhz"] == 2000
    # Polaris não expõe hotspot/memória: indisponível, nunca inventado.
    assert "temp_hotspot_c" in r.unavailable and "temp_mem_c" in r.unavailable


def test_missing_hwmon_marks_unavailable(tmp_path):
    make_polaris(str(tmp_path), hwmon=False)
    b = AmdgpuSysfsBackend(str(tmp_path / "sys"))
    r = b.read(b.discover()[0])
    assert r.metrics["temp_edge_c"] is None and r.metrics["fan_rpm"] is None
    assert any("hwmon ausente" in e for e in r.errors)


def test_non_amdgpu_driver_reported(tmp_path):
    make_polaris(str(tmp_path), driver="radeon", hwmon=False)
    b = AmdgpuSysfsBackend(str(tmp_path / "sys"))
    r = b.read(b.discover()[0])
    assert any("radeon" in e for e in r.errors)


def test_sensor_layer_never_opens_for_writing(polaris, monkeypatch):
    root, _ = polaris
    real_open = builtins.open

    def guarded(path, mode="r", *a, **k):
        assert not any(c in mode for c in "wax+"), f"escrita proibida: {path} {mode}"
        return real_open(path, mode, *a, **k)

    monkeypatch.setattr(builtins, "open", guarded)
    b = AmdgpuSysfsBackend(os.path.join(root, "sys"))
    b.read(b.discover()[0])


def test_nvidia_parser_handles_not_supported():
    rows = parse_nvidia_smi_csv("0, 00000000:01:00.0, NVIDIA RTX 4060 Ti, 55, 30, 1200, 16380, 80.5, 165.0, [N/A], 2500, 9000\n")
    assert rows[0]["name"] == "NVIDIA RTX 4060 Ti" and rows[0]["fan.speed"] is None
    assert rows[0]["memory.total"] == "16380"


# ---------------- política ----------------

def test_policy_escalates_immediately():
    p = GuardPolicy()
    assert p.evaluate(reading(temp_edge_c=60)).level == NORMAL
    assert p.evaluate(reading(temp_edge_c=81)).level == REDUZIR
    assert p.evaluate(reading(temp_edge_c=86)).level == PAUSAR


def test_policy_hysteresis_and_cooldown():
    p = GuardPolicy()
    p.evaluate(reading(temp_edge_c=86))
    # 82 °C: abaixo de 85, mas não abaixo de 85-5 → continua pausado.
    for _ in range(5):
        assert p.evaluate(reading(temp_edge_c=82)).level == PAUSAR
    # 79 °C: sai de pausar só após 3 amostras estáveis; cai para "atencao" (75 ≤ 79 < 80-5? não: 79 ≥ 75)
    levels = [p.evaluate(reading(temp_edge_c=79)).level for _ in range(3)]
    assert levels[:2] == [PAUSAR, PAUSAR] and levels[2] == REDUZIR
    levels = [p.evaluate(reading(temp_edge_c=60)).level for _ in range(3)]
    assert levels[-1] == NORMAL


def test_policy_critical_latches():
    p = GuardPolicy()
    assert p.evaluate(reading(temp_edge_c=91)).level == CRITICO
    assert p.evaluate(reading(temp_edge_c=40)).level == CRITICO


def test_policy_missing_temperature():
    assert GuardPolicy().evaluate(reading()).level == ATENCAO
    cfg = load_config()
    cfg["sem_temperatura"] = "pausar"
    assert GuardPolicy(cfg).evaluate(reading()).level == PAUSAR


def test_policy_vram_and_power():
    p = GuardPolicy()
    d = p.evaluate(reading(temp_edge_c=50, vram_used_mib=7700, vram_total_mib=8192))
    assert d.level == REDUZIR and any("vram_pct" in r for r in d.reasons)
    d = GuardPolicy().evaluate(reading(temp_edge_c=50, power_w=180, power_cap_w=185))
    assert d.level == ATENCAO


def test_policy_fan_stopped_under_heat():
    d = GuardPolicy().evaluate(reading(temp_edge_c=72, fan_rpm=0))
    assert d.level == ATENCAO and any("ventoinha" in r for r in d.reasons)


def test_config_override_and_validation(tmp_path):
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"limites": {"temp_edge_c": {"pausar": 83}}, "amostras_para_rebaixar": 1}))
    cfg = load_config(str(f))
    assert cfg["limites"]["temp_edge_c"]["pausar"] == 83 and cfg["amostras_para_rebaixar"] == 1
    f.write_text(json.dumps({"limites": {"temp_edge_c": {"atencao": 95}}}))
    with pytest.raises(ValueError):
        load_config(str(f))


# ---------------- ações ----------------

class Recorder:
    def __init__(self, can_reduce=True):
        self.calls = []
        self.can_reduce = can_reduce

    def control(self):
        def rec(name, ret=True):
            return lambda *a: (self.calls.append(name), ret)[1]
        return CallbackJobControl(reduce=rec("reduce", self.can_reduce), restore=rec("restore"),
                                  pause=rec("pause"), resume=rec("resume"), stop=rec("stop"))


def test_dispatcher_transitions_only():
    rec = Recorder()
    p, d = GuardPolicy(), ActionDispatcher(rec.control())
    for t in [60, 81, 81, 86, 86] + [60] * 6:
        d.apply(p.evaluate(reading(temp_edge_c=t)))
    assert rec.calls == ["reduce", "pause", "resume", "restore"]


def test_dispatcher_reports_unsupported_reduction():
    rec = Recorder(can_reduce=False)
    events = ActionDispatcher(rec.control()).apply(GuardPolicy().evaluate(reading(temp_edge_c=81)))
    assert events[0]["acao"] == "reduzir_carga" and events[0]["ok"] is False
    assert "não suporta" in events[0]["motivo"]


def test_dispatcher_critical_stops_once():
    rec = Recorder()
    p, d = GuardPolicy(), ActionDispatcher(rec.control())
    d.apply(p.evaluate(reading(temp_edge_c=95)))
    d.apply(p.evaluate(reading(temp_edge_c=95)))
    assert rec.calls == ["stop"] and d.stopped


# ---------------- monitor + log ----------------

def test_monitor_logs_jsonl_per_job(polaris, tmp_path):
    root, pci = polaris
    b = AmdgpuSysfsBackend(os.path.join(root, "sys"))
    rec = Recorder()
    log = JobLog(str(tmp_path / "logs"), "job-001")
    mon = GuardMonitor(b, b.discover()[0], GuardPolicy(), ActionDispatcher(rec.control()), log, interval=0)
    mon.step()
    set_temp(pci, 87)
    mon.step()
    lines = [json.loads(l) for l in open(log.path)]
    kinds = [l["tipo"] for l in lines]
    assert kinds.count("amostra") == 2 and "transicao" in kinds and "acao" in kinds
    assert all(l["job_id"] == "job-001" for l in lines)
    assert lines[0]["leitura"]["metrics"]["temp_edge_c"] == 60.0


def test_monitor_survives_backend_exception():
    class Broken(AmdgpuSysfsBackend):
        def read(self, device):
            raise OSError("sensor sumiu")
    mon = GuardMonitor(Broken("/nao-existe"), type("D", (), {"id": "x"})(), GuardPolicy(), interval=0)
    res = mon.step()
    assert res["leitura"].metrics["temp_edge_c"] is None and res["leitura"].errors


def test_joblog_rejects_path_traversal(tmp_path):
    with pytest.raises(ValueError):
        JobLog(str(tmp_path), "../fora")


# ---------------- processo real ----------------

def _state(pid):
    with open(f"/proc/{pid}/stat") as fh:
        return fh.read().rsplit(")", 1)[1].split()[0]


def test_process_control_pause_resume_stop():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
    ctl = ProcessJobControl(proc, grace=5)
    try:
        assert ctl.pause()
        time.sleep(0.2)
        assert _state(proc.pid) == "T"
        assert ctl.resume()
        time.sleep(0.2)
        assert _state(proc.pid) in ("S", "R")
        assert ctl.stop("teste")
        assert proc.poll() is not None
    finally:
        if proc.poll() is None:
            proc.kill()


def test_cli_run_stops_job_on_critical(tmp_path, capsys):
    root = str(tmp_path / "fake")
    make_polaris(root, temp=95)
    code = cli.main(["run", "--sysfs-root", os.path.join(root, "sys"), "--backend", "amdgpu",
                     "--job-id", "quente", "--interval", "0.1", "--log-dir", str(tmp_path / "logs"),
                     "--", sys.executable, "-c", "import time; time.sleep(30)"])
    assert code == 3
    kinds = [json.loads(l)["tipo"] for l in open(tmp_path / "logs" / "quente.guard.jsonl")]
    assert kinds[0] == "inicio" and "acao" in kinds and kinds[-1] == "fim"


def test_cli_run_normal_job_returns_child_code(tmp_path):
    root = str(tmp_path / "fake")
    make_polaris(root, temp=50)
    code = cli.main(["run", "--sysfs-root", os.path.join(root, "sys"), "--backend", "amdgpu",
                     "--job-id", "ok", "--interval", "0.05", "--log-dir", str(tmp_path / "logs"),
                     "--", sys.executable, "-c", "import sys, time; time.sleep(0.3); sys.exit(7)"])
    assert code == 7


def test_cli_detect_and_sample(polaris, capsys):
    root, _ = polaris
    assert cli.main(["detect", "--sysfs-root", os.path.join(root, "sys"), "--backend", "amdgpu"]) == 0
    out = capsys.readouterr().out
    assert "amdgpu:card0" in out and "temp_hotspot_c" in out
    assert cli.main(["sample", "--json", "--sysfs-root", os.path.join(root, "sys"), "--backend", "amdgpu"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data[0]["metrics"]["temp_edge_c"] == 60.0
