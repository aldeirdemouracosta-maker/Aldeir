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
    assert "curl -L --fail" in out and "tecla M → B" in out
    assert cli.main(["instrucoes", "qwen3-1.7b"]) == 0
    out = capsys.readouterr().out
    assert "curl" not in out and "baixar qwen3-1.7b --confirmar" in out  # nome escolhido pela lista do repo
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


def test_baixar_modelo_escolhe_pela_lista_e_confere_sha256(tmp_path):
    import hashlib
    import http.server
    import json as _json
    import threading
    from minivideo_atualizacoes import forjas
    from minivideo_modelos import baixar as bx

    q4, q8 = b"GGUF" + b"4" * 300, b"GGUF" + b"8" * 600
    rotas = {"/api/models/Qwen/Qwen3-1.7B-GGUF/tree/main": _json.dumps([
        {"type": "file", "path": "README.md", "size": 10},
        {"type": "file", "path": "Qwen3-1.7B-Q8_0.gguf", "size": 1, "lfs": {"oid": hashlib.sha256(q8).hexdigest(), "size": len(q8)}},
        {"type": "file", "path": "Qwen3-1.7B-Q4_K_M.gguf", "size": 1, "lfs": {"oid": hashlib.sha256(q4).hexdigest(), "size": len(q4)}},
    ]).encode(), "/Qwen/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q4_K_M.gguf": q4}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            corpo = rotas.get(self.path)
            self.send_response(200 if corpo is not None else 404)
            self.send_header("Content-Length", str(len(corpo or b"")))
            self.end_headers()
            self.wfile.write(corpo or b"")

        def log_message(self, *a):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    host = f"http://127.0.0.1:{httpd.server_address[1]}"
    cli = forjas.Cliente(timeout=5, permitir_http_local=True)
    modelos = str(tmp_path / "Modelos")
    try:
        final = bx.baixar(modelos, "qwen3-1.7b", cli, host=host)
        assert final.endswith("llm/Qwen3-1.7B-Q4_K_M.gguf") and open(final, "rb").read() == q4
        with pytest.raises(bx.Recusado, match="já existe"):
            bx.baixar(modelos, "qwen3-1.7b", cli, host=host)
        os.unlink(final)
        rotas["/Qwen/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q4_K_M.gguf"] = b"GGUF" + b"x" * 300  # adulterado
        with pytest.raises(bx.Recusado, match="sha256 não confere"):
            bx.baixar(modelos, "qwen3-1.7b", cli, host=host)
        assert os.listdir(os.path.join(modelos, "llm")) == []  # nada parcial fica para trás
        with pytest.raises(bx.Recusado, match="CUDA"):
            bx.baixar(modelos, "wan2.2-ti2v-5b", cli, host=host)
        with pytest.raises(bx.Recusado, match="já vem no ISO"):
            bx.baixar(modelos, "rife-v4.6", cli, host=host)
    finally:
        httpd.shutdown()
