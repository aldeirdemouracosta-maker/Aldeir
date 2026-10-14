#!/usr/bin/env python3
"""Teste de fumaça contra um servidor de modelos REAL (Ollama, llama-server ou LM Studio).

    python scripts/smoke.py                                   # Ollama em http://127.0.0.1:11434
    python scripts/smoke.py --provider local_compatible --url http://127.0.0.1:8080
    python scripts/smoke.py --vision-url http://127.0.0.1:8081 --audio-url http://127.0.0.1:8000 --voices pf_dora

Não baixa nada. Passos sem o modelo necessário aparecem como PULADO. FALHA = contrato/HTTP quebrado;
AVISO = o modelo respondeu, mas fora do esperado (qualidade). Cole a saída de volta para análise.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402

from app.config import Settings  # noqa: E402
from app.main import build_provider, create_app  # noqa: E402

RESULTS: list[tuple[str, str, str]] = []


def report(name: str, status: str, detail: str = "") -> None:
    RESULTS.append((name, status, detail))
    print(f"[{status:7}] {name}" + (f" — {detail}" if detail else ""), flush=True)


async def run(c: httpx.AsyncClient, action: str, payload: dict, timeout: float = 180.0) -> tuple[int, dict]:
    t0 = time.perf_counter()
    r = await c.post("/run", json={"action": action, "payload": payload}, timeout=timeout)
    body = r.json()
    body["_ms"] = round((time.perf_counter() - t0) * 1000)
    return r.status_code, body


def tiny_png() -> bytes:
    import struct
    import zlib

    def chunk(t: bytes, d: bytes) -> bytes:
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"\x00" + b"\xff\x00\x00" * 16  # 16x1 vermelho
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 16, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def tone_wav() -> bytes:
    import io
    import math
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b"".join(int(6000 * math.sin(2 * math.pi * 440 * i / 16000)).to_bytes(2, "little", signed=True)
                               for i in range(16000)))
    return buf.getvalue()


async def media_steps(c, settings, agents) -> None:
    """Visão, fala e voz só rodam se o agente estiver disponível (servidor de mídia configurado)."""
    root = settings.media_dir
    root.mkdir(parents=True, exist_ok=True)
    if agents["vision"]["available"]:
        (root / "teste.png").write_bytes(tiny_png())
        code, b = await run(c, "image_describe", {"path": "teste.png", "prompt": "Descreva a imagem em uma frase."})
        report("vision (llama-server --mmproj)", "OK" if code == 200 and b.get("output", "").strip() else "FALHA",
               (b.get("output") or b.get("detail", ""))[:70])
    else:
        report("vision", "PULADO", agents["vision"]["reason"])
    if agents["speech"]["available"]:
        (root / "tom.wav").write_bytes(tone_wav())
        code, b = await run(c, "speech_transcribe", {"path": "tom.wav"})
        report("speech (contrato; um tom não tem fala)", "OK" if code == 200 else "FALHA", (b.get("output") or b.get("detail", ""))[:70])
    else:
        report("speech", "PULADO", agents["speech"]["reason"])
    if agents["voice"]["available"]:
        code, b = await run(c, "voice_speak", {"text": "Olá, mundo.", "voice": args_voice(settings)})
        path = root / b["output"] if code == 200 else None
        report("voice (gera WAV)", "OK" if path and path.read_bytes()[:4] == b"RIFF" else "FALHA", b.get("output") or b.get("detail", ""))
    else:
        report("voice", "PULADO", agents["voice"]["reason"])


def args_voice(settings) -> str:
    return settings.voice_list[0] if settings.voice_list else "default"


async def smoke(args) -> int:
    tmp = Path(tempfile.mkdtemp(prefix="swarm-smoke-"))
    settings = Settings(provider=args.provider, provider_url=args.url, state_path=tmp / "s.db",
                        media_dir=tmp / "media", job_timeout=args.timeout, queue_timeout=args.timeout,
                        vision_url=args.vision_url, vision_name=args.vision_name, audio_url=args.audio_url,
                        stt_model=args.stt_model, tts_model=args.tts_model,
                        voice_list=tuple(v for v in args.voices.split(",") if v))
    app = create_app(settings, provider=build_provider(settings))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000") as c:
        r = await c.get("/management/models")
        if r.status_code != 200:
            report("provedor acessível", "FALHA", f"HTTP {r.status_code}: {r.json().get('detail')}")
            return 1
        models = r.json()
        report("provedor acessível", "OK", f"{len(models['installed'])} instalados, {len(models['loaded'])} carregados")
        agents = {a["name"]: a for a in (await c.get("/agents")).json()}
        for name, a in sorted(agents.items()):
            print(f"           {name:10} {'disponível' if a['available'] else 'indisponível: ' + a['reason']}")

        def usable(name: str) -> bool:
            return agents[name]["available"]

        if usable("chat"):
            code, b = await run(c, "chat", {"text": "Responda apenas com a palavra: ok"})
            report("chat", "OK" if code == 200 and b.get("output", "").strip() else "FALHA", f"{b.get('_ms')} ms")
            code, b = await run(c, "summarize", {"text": "A reunião definiu lançamento em março, orçamento de 50 mil e testes na semana que vem."})
            report("summarize", "OK" if code == 200 and b.get("output", "").strip() else "FALHA", f"{b.get('_ms')} ms")
            code, b = await run(c, "translate", {"text": "Bom dia, tudo bem?", "target": "inglês"})
            out = b.get("output", "")
            report("translate", ("OK" if "morning" in out.lower() else "AVISO") if code == 200 else "FALHA", out[:60])
            sid = f"smoke-{int(time.time())}"
            await run(c, "chat", {"text": "Meu nome é Ana. Guarde isso.", "session": sid})
            code, b = await run(c, "chat", {"text": "Qual é o meu nome? Responda só o nome.", "session": sid})
            out = b.get("output", "")
            report("chat com memória de sessão", ("OK" if "ana" in out.lower() else "AVISO") if code == 200 else "FALHA", out[:60])
            await c.delete(f"/sessions/{sid}")
            ps = await asyncio.gather(*(run(c, "chat", {"text": f"Diga o número {i}"}) for i in range(4)))
            report("4 pedidos em paralelo", "OK" if all(p[0] == 200 for p in ps) else "FALHA",
                   f"códigos {[p[0] for p in ps]}, {max(p[1]['_ms'] for p in ps)} ms o mais lento")
        else:
            report("chat/summarize/translate", "PULADO", agents["chat"]["reason"])

        if usable("coder"):
            code, b = await run(c, "code_generate", {"text": "Função Python soma(a, b) que retorna a soma.", "output_mode": "code_only"})
            if code == 200:
                out = b["output"]
                report("coder code_only", "OK" if "def " in out and "```" not in out else "AVISO", f"{b['_ms']} ms")
            else:
                report("coder code_only", "AVISO" if code == 422 else "FALHA", b.get("detail", ""))
        else:
            report("coder", "PULADO", agents["coder"]["reason"])

        if usable("rag"):
            docs = settings.media_dir / "docs"
            docs.mkdir(parents=True, exist_ok=True)
            (docs / "gatos.md").write_text("O gato é um felino doméstico que gosta de dormir ao sol.\n", encoding="utf-8")
            (docs / "carros.md").write_text("O carro é um veículo com motor usado para transporte em estradas.\n", encoding="utf-8")
            code, b = await run(c, "rag_index", {"path": "docs"})
            report("rag indexar", "OK" if code == 200 else "FALHA", b.get("output") or b.get("detail", ""))
            code, b = await run(c, "rag_search", {"text": "animal que dorme", "k": 2})
            top = (b.get("output") or "").splitlines()[0] if code == 200 and b.get("output") else ""
            report("rag buscar (semântica)", ("OK" if "gatos.md" in top else "AVISO") if code == 200 else "FALHA", top[:70])
        else:
            report("rag", "PULADO", agents["rag"]["reason"])

        await media_steps(c, settings, agents)
        code, b = await run(c, "lang_detect", {"text": "The cat is on the table and it is not happy"})
        report("langid (sem modelo)", "OK" if code == 200 and b["output"].startswith("en") else "FALHA", b.get("output", ""))

        if usable("chat"):
            steps = [{"action": "lang_detect", "payload": {"text": "O gato dorme no sofá porque não quer sair"}},
                     {"action": "chat", "payload": {"text": "Em uma frase, comente este código de idioma: {{prev}}"}}]
            code, b = await run(c, "plan_run", {"steps": steps})
            report("planner plan_run (passos manuais)", "OK" if code == 200 and "ERRO" not in b["output"] else "FALHA",
                   (b.get("output") or b.get("detail", "")).replace("\n", " | ")[:90])
        if usable("planner"):
            code, b = await run(c, "plan_create", {"text": "Detecte o idioma do texto 'The cat is on the table'."})
            report("planner plan_create (modelo gera JSON)", "OK" if code == 200 else "AVISO",
                   "plano válido" if code == 200 else b.get("detail", "")[:80])

    bad = [r for r in RESULTS if r[1] == "FALHA"]
    print(f"\nresumo: {sum(r[1]=='OK' for r in RESULTS)} OK, {sum(r[1]=='AVISO' for r in RESULTS)} aviso(s), "
          f"{sum(r[1]=='PULADO' for r in RESULTS)} pulado(s), {len(bad)} falha(s)")
    return 1 if bad else 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--provider", default="ollama", choices=["ollama", "local_compatible"])
    p.add_argument("--url", default="http://127.0.0.1:11434")
    p.add_argument("--timeout", type=float, default=180.0, help="segundos por pedido")
    p.add_argument("--vision-url", default="", help="llama-server com --mmproj (opcional)")
    p.add_argument("--vision-name", default="", help="nome do modelo no servidor de visão (modo roteador)")
    p.add_argument("--audio-url", default="", help="servidor compatível com OpenAI para STT/TTS (opcional)")
    p.add_argument("--stt-model", default="")
    p.add_argument("--tts-model", default="")
    p.add_argument("--voices", default="", help="vozes disponíveis, separadas por vírgula")
    return asyncio.run(smoke(p.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
