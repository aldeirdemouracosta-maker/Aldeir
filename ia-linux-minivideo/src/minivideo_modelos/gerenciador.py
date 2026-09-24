"""Gerenciador de modelos: catálogo, inventário, organização, verificação,
recomendação por hardware e calibração do llama.cpp.

Regra: NENHUM download automático. ``instrucoes`` só imprime o que o
usuário pode executar manualmente. Nada aqui abre conexões de rede.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

CATALOGO = os.path.join(os.path.dirname(__file__), "catalogo.json")
EXTENSOES = (".gguf", ".bin", ".param", ".safetensors", ".onnx", ".pth", ".ckpt", ".pt")
CACHE = ".inventario.json"


def catalogo() -> List[Dict]:
    with open(CATALOGO, encoding="utf-8") as fh:
        return json.load(fh)["modelos"]


def formato_por_cabecalho(path: str) -> str:
    """Identifica o formato pelos primeiros bytes (não confia só na extensão)."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(16)
    except OSError:
        return "ilegivel"
    if len(head) < 8:
        return "vazio"
    if head[:4] == b"GGUF":
        return "gguf"
    if head[:4] in (b"lmgg", b"ggml"):  # 0x67676d6c em little-endian (whisper.cpp)
        return "ggml-whisper"
    if head.startswith(b"7767517"):
        return "ncnn"
    n = int.from_bytes(head[:8], "little")
    if 2 <= n < 100_000_000 and head[8:9] == b"{":
        return "safetensors"
    if head[:2] == b"PK":
        return "zip/pytorch"
    if path.endswith(".bin") and os.path.exists(path[:-4] + ".param"):
        return "ncnn"  # pesos .bin do ncnn não têm assinatura; o par .param identifica
    return "desconhecido"


def identificar(nome: str, fmt: str, cat: List[Dict]) -> Optional[Dict]:
    for m in cat:
        if fnmatch.fnmatch(nome, m["arquivo"]) and (fmt == m["formato"] or fmt == "desconhecido"):
            return m
    return None


@dataclass
class Item:
    caminho: str
    relativo: str
    tamanho_mib: float
    formato: str
    modelo: Optional[str]
    destino_correto: Optional[str]
    problemas: List[str]

    def to_dict(self) -> Dict:
        return dict(self.__dict__)


def inventario(modelos_dir: str, profundidade: int = 5) -> List[Item]:
    cat = catalogo()
    itens: List[Item] = []
    base_depth = modelos_dir.rstrip(os.sep).count(os.sep)
    for cur, dirs, files in os.walk(modelos_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if cur.count(os.sep) - base_depth >= profundidade:
            dirs[:] = []
        for f in sorted(files):
            if not f.lower().endswith(EXTENSOES):
                continue
            p = os.path.join(cur, f)
            rel = os.path.relpath(p, modelos_dir)
            fmt = formato_por_cabecalho(p)
            size = os.path.getsize(p) / 1048576
            m = identificar(f, fmt, cat)
            if m is None and fmt == "ncnn" and f.endswith(".bin"):
                m = identificar(f[:-4] + ".param", "ncnn", cat)  # pesos do par .param/.bin
            problemas: List[str] = []
            if fmt == "vazio":
                problemas.append("arquivo vazio ou truncado")
            if f.endswith(".gguf") and fmt not in ("gguf",):
                problemas.append(f"extensão .gguf mas cabeçalho é '{fmt}' (download incompleto?)")
            if m and m.get("tamanho_mib") and fmt in ("gguf", "ggml-whisper", "safetensors") \
                    and size < 0.9 * m["tamanho_mib"]:
                problemas.append(f"menor que o esperado (~{m['tamanho_mib']} MiB): download incompleto?")
            destino = None
            if m:
                destino = os.path.join(m["destino"], f)
                if os.path.normpath(rel) != os.path.normpath(destino):
                    problemas.append(f"fora da pasta padrão: mover para Modelos/{destino}")
            itens.append(Item(p, rel, round(size, 2), fmt, m["id"] if m else None, destino, problemas))
    return itens


def organizar(modelos_dir: str, aplicar: bool = False) -> List[Dict]:
    """Move modelos reconhecidos para Modelos/<destino>/. Sem --aplicar só mostra."""
    acoes = []
    for it in inventario(modelos_dir):
        if not it.destino_correto or os.path.normpath(it.relativo) == os.path.normpath(it.destino_correto):
            continue
        alvo = os.path.join(modelos_dir, it.destino_correto)
        acao = {"de": it.relativo, "para": it.destino_correto, "feito": False, "motivo": None}
        if os.path.exists(alvo):
            acao["motivo"] = "já existe um arquivo no destino; nada foi sobrescrito"
        elif aplicar:
            os.makedirs(os.path.dirname(alvo), exist_ok=True)
            shutil.move(it.caminho, alvo)
            acao["feito"] = True
        acoes.append(acao)
    return acoes


def verificar(modelos_dir: str) -> List[Dict]:
    """sha256 de cada modelo, com cache por (tamanho, mtime) em Modelos/.inventario.json."""
    cache_path = os.path.join(modelos_dir, CACHE)
    try:
        with open(cache_path, encoding="utf-8") as fh:
            cache = json.load(fh)
    except (OSError, ValueError):
        cache = {}
    out = []
    for it in inventario(modelos_dir):
        st = os.stat(it.caminho)
        chave = f"{st.st_size}:{int(st.st_mtime)}"
        ent = cache.get(it.relativo)
        if ent and ent.get("chave") == chave:
            digest, reusado = ent["sha256"], True
        else:
            h = hashlib.sha256()
            with open(it.caminho, "rb") as fh:
                for bloco in iter(lambda: fh.read(1 << 20), b""):
                    h.update(bloco)
            digest, reusado = h.hexdigest(), False
            cache[it.relativo] = {"chave": chave, "sha256": digest}
        out.append({**it.to_dict(), "sha256": digest, "hash_do_cache": reusado})
    with open(cache_path, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, indent=2)
    return out


def recomendar(devices: List, ram_mib: Optional[float]) -> List[Dict]:
    """Escolhe modelos que cabem neste hardware, com justificativa."""
    cat = {m["id"]: m for m in catalogo()}
    vk = [d for d in devices if d.kind in ("vulkan-dgpu", "vulkan-apu") and d.usable]
    cuda = [d for d in devices if d.kind == "cuda" and d.usable]
    vram_vk = max((d.vram_mib or 0 for d in vk), default=0)
    vram_cuda = max((d.vram_mib or 0 for d in cuda), default=0)
    ram = ram_mib or 0
    rec = []
    if vk and vram_vk >= 4000:
        rec.append((cat["whisper-small"], f"GPU Vulkan com {vram_vk} MiB: small roda rápido; medium se quiser mais precisão"))
    elif vk or cuda:
        rec.append((cat["whisper-base"], "GPU com pouca VRAM: base"))
    else:
        rec.append((cat["whisper-base"] if ram < 8000 else cat["whisper-small"], "sem GPU: modelo leve na CPU"))
    if (vk and vram_vk >= 4000) or ram >= 8000 or cuda:
        rec.append((cat["qwen3-1.7b"], "Diretor/Editor por LLM: 1.7B cabe na RX 580 (quantização Q4_K_M ou Q8_0)"))
    else:
        rec.append((cat["qwen3-0.6b"], "pouca memória: 0.6B"))
    for mid in ("wan2.1-vace-1.3b", "editctrl-1.3b", "ltx-2.3", "wan2.2-ti2v-5b"):
        m = cat[mid]
        if vram_cuda >= m["vram_mib"]:
            rec.append((m, f"GPU CUDA com {vram_cuda} MiB atende o alvo de {m['vram_mib']} MiB (validar fisicamente)"))
    out = []
    for m, porque in rec:
        out.append({"id": m["id"], "agente": m["agente"], "porque": porque, "licenca": m["licenca"],
                    "destino": f"Modelos/{m['destino']}/"})
    indisponiveis = [m["id"] for m in cat.values() if "cuda" in m["requer"] and len(m["requer"]) == 1
                     and vram_cuda < m["vram_mib"]]
    if indisponiveis:
        out.append({"id": None, "agente": "gerador/editor_generativo",
                    "porque": "indisponíveis sem NVIDIA CUDA com VRAM suficiente: " + ", ".join(indisponiveis),
                    "licenca": None, "destino": None})
    return out


def instrucoes(modelo_id: str) -> str:
    m = {x["id"]: x for x in catalogo()}.get(modelo_id)
    if m is None:
        raise KeyError(f"modelo desconhecido: {modelo_id}")
    linhas = [f"{m['id']} — agente {m['agente']} · motor {m['motor']} · requer {', '.join(m['requer'])}",
              f"Licença: {m['licenca']}  (leia antes de baixar)", f"Página oficial: {m['pagina']}",
              f"Destino: Modelos/{m['destino']}/"]
    if m.get("embutido"):
        linhas.append("Já vem no ISO em /usr/share/minivideo/modelos/ — nada a baixar.")
    elif m.get("url_arquivo"):
        linhas += ["Para baixar manualmente (nada é baixado automaticamente):",
                   f"  mkdir -p \"$MINIVIDEO_HOME/Modelos/{m['destino']}\"",
                   f"  curl -L --fail -o \"$MINIVIDEO_HOME/Modelos/{m['destino']}/{m['arquivo']}\" \\",
                   f"       {m['url_arquivo']}",
                   "Depois: minivideo-modelos verificar (calcula e guarda o sha256)."]
    else:
        linhas += [f"Escolha o arquivo ({m['arquivo']}) na página oficial e salve em Modelos/{m['destino']}/.",
                   "Depois: minivideo-modelos organizar --aplicar && minivideo-modelos verificar"]
    if m.get("nota"):
        linhas.append(f"Nota: {m['nota']}")
    return "\n".join(linhas)


def calibrar(gguf: str, bench: str = "llama-bench", threads=(4, 6, 8, 10, 12), ngl=(0, 8, 16, 24, 32, 99),
             timeout: float = 1800, saida: Optional[str] = None) -> Dict:
    """Roda llama-bench (só quando o usuário pede) e guarda a melhor combinação."""
    exe = shutil.which(bench) or (bench if os.path.isfile(bench) else None)
    if exe is None:
        raise FileNotFoundError("llama-bench não encontrado")
    if formato_por_cabecalho(gguf) != "gguf":
        raise ValueError(f"{gguf} não é um arquivo GGUF válido")
    cmd = [exe, "-m", gguf, "-t", ",".join(map(str, threads)), "-ngl", ",".join(map(str, ngl)),
           "-p", "256", "-n", "64", "-o", "json"]
    t0 = time.time()
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    if out.returncode != 0:
        raise RuntimeError(f"llama-bench falhou: {out.stderr.strip()[-400:]}")
    linhas = json.loads(out.stdout)
    geracao = [r for r in linhas if r.get("n_gen", 0) > 0 and r.get("n_prompt", 0) == 0]
    prompt = [r for r in linhas if r.get("n_prompt", 0) > 0 and r.get("n_gen", 0) == 0]
    if not geracao:
        raise RuntimeError("llama-bench não retornou medições de geração")
    melhor = max(geracao, key=lambda r: r["avg_ts"])
    par = next((r for r in prompt if r["n_threads"] == melhor["n_threads"]
                and r["n_gpu_layers"] == melhor["n_gpu_layers"]), None)
    res = {"modelo": os.path.abspath(gguf), "comando": cmd, "segundos": round(time.time() - t0, 1),
           "melhor": {"threads": melhor["n_threads"], "ngl": melhor["n_gpu_layers"],
                      "geracao_tok_s": round(melhor["avg_ts"], 2),
                      "prompt_tok_s": round(par["avg_ts"], 2) if par else None},
           "medicoes": [{"threads": r["n_threads"], "ngl": r["n_gpu_layers"], "n_prompt": r["n_prompt"],
                         "n_gen": r["n_gen"], "tok_s": round(r["avg_ts"], 2)} for r in linhas]}
    if saida:
        with open(saida, "w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=2)
    return res
