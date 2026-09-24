"""Formato do prompt de cada modelo generativo.

Os valores de cada modelo (resolução, fps, quadros) vêm da documentação
oficial deles; conferir de novo antes de rodar numa máquina CUDA:
- Wan2.2 TI2V-5B: 720p (1280*704 ou 704*1280), 24 fps, quadros = 4n+1.
- Wan2.1 VACE 1.3B: 480p (832*480 ou 480*832), 16 fps, quadros = 4n+1.
- LTX (LTX-Video/LTX-2): largura/altura múltiplas de 32, quadros = 8n+1,
  prompt em parágrafo único e cronológico.

Wan e LTX usam codificadores de texto multilíngues (umT5 e Gemma), então
descrições em português funcionam; os termos de câmera e luz vão em inglês,
que é como aparecem nos dados de treino. Com o LLM local, o refinamento
reescreve tudo em inglês.
"""

from __future__ import annotations

from typing import Dict

from . import vocabulario as voc

# Tradução própria (e reduzida) da lista negativa padrão do Wan
# (wan/configs/shared_config.py, Apache-2.0).
NEGATIVO_WAN = ("oversaturated colors, overexposed, static frame, blurry details, subtitles, text, watermark, "
                "worst quality, low quality, JPEG artifacts, ugly, deformed, extra fingers, poorly drawn hands, "
                "poorly drawn face, fused fingers, cluttered background, walking backwards")
NEGATIVO_LTX = "worst quality, inconsistent motion, blurry, jittery, distorted, watermark, text"

MODELOS: Dict[str, Dict] = {
    "wan2.2-ti2v-5b": {"familia": "wan", "nome": "Wan2.2 TI2V-5B (texto/imagem → vídeo)",
                       "fps": 24, "tamanho": {"landscape": "1280*704", "portrait": "704*1280"}, "passo": 4,
                       "negativo": NEGATIVO_WAN},
    "wan2.1-vace-1.3b": {"familia": "wan", "nome": "Wan2.1 VACE 1.3B (edição/geração 480p)",
                         "fps": 16, "tamanho": {"landscape": "832*480", "portrait": "480*832"}, "passo": 4,
                         "negativo": NEGATIVO_WAN},
    "ltx-2.3": {"familia": "ltx", "nome": "LTX-2.3 (texto → vídeo com áudio)",
                "fps": 24, "tamanho": {"landscape": "1280*704", "portrait": "704*1280"}, "passo": 8,
                "negativo": NEGATIVO_LTX},
}
PADRAO = "wan2.2-ti2v-5b"


def _quadros(duracao_s: float, fps: int, passo: int) -> int:
    n = max(1, round(duracao_s * fps / passo))
    return passo * n + 1


def _tags(ficha: Dict[str, str], campos) -> list:
    out = []
    for c in campos:
        if ficha.get(c):
            en = voc.ingles(c, ficha[c])
            if en:
                out.append(en)
    return out


def montar(ficha: Dict[str, str], modelo: str = PADRAO) -> Dict:
    """Ficha → {prompt, prompt_negativo, parametros}. Determinístico."""
    if modelo not in MODELOS:
        raise ValueError(f"modelo desconhecido: {modelo} (use {', '.join(MODELOS)})")
    m = MODELOS[modelo]
    assunto, acao, cenario = (ficha.get(k, "").strip().rstrip(".") for k in ("assunto", "acao", "cenario"))
    estilo = _tags(ficha, ["estilo"])
    luz = _tags(ficha, ["periodo", "luz", "tom"])
    camera = _tags(ficha, ["plano", "angulo", "movimento"])
    if m["familia"] == "wan":
        # Wan: estilo primeiro, depois a estética em etiquetas, depois o conteúdo.
        partes = estilo + camera + luz
        cabeca = ", ".join(partes)
        corpo = ". ".join(x for x in (f"{assunto} {acao}".strip(), (f"Background: {cenario}" if cenario else ""))
                          if x)
        prompt = f"{cabeca}. {corpo}." if cabeca else f"{corpo}."
    else:
        # LTX: parágrafo único e cronológico: ação → aparência → cenário → câmera → luz.
        frases = [x for x in (f"{assunto} {acao}".strip(), (f"Background: {cenario}" if cenario else ""))
                  if x]
        if camera:
            frases.append("Camera: " + ", ".join(camera))
        if luz:
            frases.append("Lighting and color: " + ", ".join(luz))
        if estilo:
            frases.append("Style: " + ", ".join(estilo))
        prompt = ". ".join(frases) + "."
    negativo = m["negativo"]
    if ficha.get("evitar"):
        negativo = ficha["evitar"].strip() + ", " + negativo
    orient = voc.ingles("orientacao", ficha.get("orientacao", "")) or "landscape"
    dur = float(ficha.get("duracao_s") or 5)
    dur = min(max(dur, 1.0), 20.0)
    return {
        "modelo": modelo,
        "prompt": prompt.strip(),
        "prompt_negativo": negativo,
        "parametros": {"tamanho": m["tamanho"][orient], "fps": m["fps"],
                       "quadros": _quadros(dur, m["fps"], m["passo"]), "duracao_s": dur},
    }
