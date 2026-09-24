import json
import os

from conftest import make_polaris
from minivideo_audit import audit

CPUINFO_XEON_E5_2630L_V2 = "".join(
    f"processor\t: {i}\nmodel name\t: Intel(R) Xeon(R) CPU E5-2630L v2 @ 2.40GHz\n"
    "flags\t\t: fpu sse sse2 ssse3 sse4_1 sse4_2 popcnt aes avx f16c rdrand\n\n"
    for i in range(12)
)


def fake_root(tmp_path):
    root = str(tmp_path / "root")
    os.makedirs(os.path.join(root, "proc"))
    with open(os.path.join(root, "proc/cpuinfo"), "w") as fh:
        fh.write(CPUINFO_XEON_E5_2630L_V2)
    with open(os.path.join(root, "proc/meminfo"), "w") as fh:
        fh.write("MemTotal:       16384000 kB\nMemAvailable:   12000000 kB\n")
    make_polaris(root)
    return root


def test_cpu_without_avx2(tmp_path):
    c = audit.cpu_info(fake_root(tmp_path))
    assert c["threads_logicos"] == 12
    assert c["instrucoes"]["avx"] and not c["instrucoes"]["avx2"]


def test_gpu_rx580_2048sp_identified(tmp_path):
    g = audit.gpu_info(fake_root(tmp_path))
    assert g[0]["nome"] == "AMD Polaris 20 XL (RX 580 2048SP)" and g[0]["vram_mib"] == 8192


def test_profile_without_cuda_or_vulkan_lists_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(audit.shutil, "which", lambda name: None)
    r = audit.collect(fake_root(tmp_path))
    perfil = r["perfil"]
    assert perfil["perfis"] == ["cpu"]
    assert any("wan-vace-1.3b" in i for i in perfil["indisponivel"])
    assert any("RIFE" in i for i in perfil["indisponivel"])
    assert any("AVX2" in a for a in perfil["avisos"])
    assert any("Vulkan não confirmado" in a for a in perfil["avisos"])
    assert "Indisponível nesta máquina" in audit.render_text(r)


def test_profile_cuda16_and_vulkan():
    report = {
        "cpu": {"instrucoes": {"avx": True, "avx2": True}},
        "cuda": {"gpus": [{"vram_mib": 16380}]},
        "vulkan": {"estado": "presente", "dispositivos": [{"nome": "AMD Radeon RX 580 (RADV POLARIS10)"}]},
        "gpus": [],
        "ferramentas": {k: {"estado": "presente"} for k in audit.TOOLS},
    }
    perfil = audit.choose_profile(report)
    assert perfil["perfis"] == ["cuda16", "vulkan", "cpu"] and perfil["indisponivel"] == []


def test_find_weights_lists_without_reading(tmp_path):
    (tmp_path / "whisper").mkdir()
    (tmp_path / "whisper" / "ggml-small.bin").write_bytes(b"x" * 10)
    (tmp_path / "rife").mkdir()
    (tmp_path / "rife" / "flownet.param").write_text("p")
    hits = audit.find_weights([str(tmp_path), str(tmp_path / "nao-existe")])
    kinds = sorted(h.get("tipo", "erro") for h in hits)
    assert kinds == ["erro", "ncnn (RIFE/Real-ESRGAN)", "whisper.cpp (ggml)"]


def test_main_writes_json(tmp_path, capsys):
    out = tmp_path / "audit.json"
    assert audit.main(["--json", "-o", str(out)]) == 0
    data = json.loads(out.read_text())
    assert "perfil" in data and "ferramentas" in data
