import json
import os

import pytest

from minivideo_agents.devices import Device
from minivideo_modelos import cli, gerenciador as g


def w(path, data: bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def test_header_detection(tmp_path):
    assert g.formato_por_cabecalho(w(str(tmp_path / "a.gguf"), b"GGUF" + b"\0" * 20)) == "gguf"
    assert g.formato_por_cabecalho(w(str(tmp_path / "b.bin"), b"lmgg" + b"\0" * 20)) == "ggml-whisper"
    assert g.formato_por_cabecalho(w(str(tmp_path / "c.param"), b"7767517\n1 2\n")) == "ncnn"
    hdr = (10).to_bytes(8, "little") + b'{"a":1}   '
    assert g.formato_por_cabecalho(w(str(tmp_path / "d.safetensors"), hdr)) == "safetensors"
    assert g.formato_por_cabecalho(w(str(tmp_path / "e.gguf"), b"<html>404</html>")) == "desconhecido"
    assert g.formato_por_cabecalho(w(str(tmp_path / "f.bin"), b"ab")) == "vazio"


def test_inventory_flags_problems_and_organize(tmp_path):
    m = str(tmp_path / "Modelos")
    w(os.path.join(m, "downloads", "Qwen3-1.7B-Q8_0.gguf"), b"GGUF" + b"\0" * 64)
    w(os.path.join(m, "ggml-small.bin"), b"lmgg" + b"\0" * 1024)          # pequeno demais
    w(os.path.join(m, "llm", "quebrado.gguf"), b"<!DOCTYPE html>")        # download virou página HTML
    itens = {i.relativo: i for i in g.inventario(m)}
    assert itens["downloads/Qwen3-1.7B-Q8_0.gguf"].modelo == "qwen3-1.7b"
    assert any("fora da pasta padrão" in p for p in itens["downloads/Qwen3-1.7B-Q8_0.gguf"].problemas)
    assert any("incompleto" in p for p in itens["ggml-small.bin"].problemas)
    assert any("cabeçalho" in p for p in itens["llm/quebrado.gguf"].problemas)
    previa = g.organizar(m)
    assert all(not a["feito"] for a in previa) and os.path.exists(os.path.join(m, "ggml-small.bin"))
    feito = g.organizar(m, aplicar=True)
    assert {a["para"] for a in feito if a["feito"]} == {"llm/Qwen3-1.7B-Q8_0.gguf", "whisper/ggml-small.bin"}
    w(os.path.join(m, "outro", "ggml-small.bin"), b"lmgg" + b"\0" * 10)
    conflito = g.organizar(m, aplicar=True)
    assert conflito and not conflito[0]["feito"] and "sobrescrito" in conflito[0]["motivo"]


def test_verify_uses_cache(tmp_path):
    m = str(tmp_path / "Modelos")
    w(os.path.join(m, "llm", "Qwen3-0.6B-Q8_0.gguf"), b"GGUF" + b"x" * 100)
    r1 = g.verificar(m)
    r2 = g.verificar(m)
    assert r1[0]["sha256"] == r2[0]["sha256"] and not r1[0]["hash_do_cache"] and r2[0]["hash_do_cache"]


def test_recommend_by_hardware():
    rx580 = [Device("cpu", "cpu", "Xeon"), Device("amdgpu:card0", "vulkan-dgpu", "RX 580", 8192, "amdgpu")]
    ids = [r["id"] for r in g.recomendar(rx580, 12000)]
    assert ids[:2] == ["whisper-small", "qwen3-1.7b"] and None in ids  # generativos indisponíveis
    fraco = [Device("cpu", "cpu", "CPU")]
    assert [r["id"] for r in g.recomendar(fraco, 4000)][:2] == ["whisper-base", "qwen3-0.6b"]
    cuda16 = rx580 + [Device("nvidia:0", "cuda", "RTX", 16376, "nvidia")]
    ids = [r["id"] for r in g.recomendar(cuda16, 32000)]
    assert "wan2.1-vace-1.3b" in ids and "editctrl-1.3b" in ids and "wan2.2-ti2v-5b" not in ids


def test_instructions_never_download(capsys):
    assert cli.main(["instrucoes", "whisper-small"]) == 0
    out = capsys.readouterr().out
    assert "curl -L --fail" in out and "nada é baixado automaticamente" in out
    assert cli.main(["instrucoes", "qwen3-1.7b"]) == 0
    assert "curl" not in capsys.readouterr().out  # sem URL de arquivo conferida: só a página
    assert cli.main(["instrucoes", "rife-v4.6"]) == 0
    assert "Já vem no ISO" in capsys.readouterr().out
    assert cli.main(["instrucoes", "inexistente"]) == 2


def test_calibrate_with_fake_llama_bench(tmp_path):
    gguf = w(str(tmp_path / "m.gguf"), b"GGUF" + b"\0" * 32)
    linhas = []
    for t in (6, 12):
        for ngl in (0, 99):
            linhas.append({"n_threads": t, "n_gpu_layers": ngl, "n_prompt": 256, "n_gen": 0,
                           "avg_ts": 50.0 + ngl + t})
            linhas.append({"n_threads": t, "n_gpu_layers": ngl, "n_prompt": 0, "n_gen": 64,
                           "avg_ts": 5.0 + ngl / 10 + (1 if t == 6 else 0)})
    bench = tmp_path / "llama-bench"
    bench.write_text("#!/bin/sh\ncat <<'EOF'\n" + json.dumps(linhas) + "\nEOF\n")
    bench.chmod(0o755)
    res = g.calibrar(gguf, str(bench), saida=str(tmp_path / "cal.json"))
    assert res["melhor"] == {"threads": 6, "ngl": 99, "geracao_tok_s": 15.9, "prompt_tok_s": 155.0}
    assert json.load(open(tmp_path / "cal.json"))["melhor"]["ngl"] == 99
    with pytest.raises(ValueError):
        g.calibrar(w(str(tmp_path / "x.gguf"), b"nao gguf!!"), str(bench))
