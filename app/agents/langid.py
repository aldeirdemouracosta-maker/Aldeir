"""Agente LANGID: identifica o idioma de um texto, sem modelo (script Unicode + palavras funcionais).

Limite honesto: textos curtos (< ~4 palavras) e misturas de idiomas são pouco confiáveis; nesses casos
o resultado é "und" (indeterminado) em vez de um palpite.
"""
from __future__ import annotations

import re
from typing import Any

from app.agents.base import Agent

STOPWORDS = {
    "pt": "de a o que e do da em um para é com não uma os no se na por mais as dos como mas foi ao ele das tem à seu sua ou ser quando muito há nos já está eu também só pelo pela até isso ela entre era depois sem mesmo aos".split(),
    "es": "de la que el en y a los del se las por un para con no una su al lo como más pero sus le ya o este sí porque esta entre cuando muy sin sobre también me hasta hay donde quien desde todo nos durante".split(),
    "en": "the of and to in is that it was for on are as with his they at be this from have or by one had not but what all were when we there can an your which their said if do will each about how up out them then she many some so these would other into has more her two like him see time could no make than first been its who now people my made over did down only way find use may water long little very after words called just where most know".split(),
    "fr": "de la le et les des en un du une que est pour qui dans a par plus pas au sur se ne ce il sont ses ou mais avec son comme je nous vous leur cette ont être été fait aussi très tout bien sans peut elle même entre ces aux".split(),
    "de": "der die und in den von zu das mit sich des auf für ist im dem nicht ein eine als auch es an werden aus er hat dass sie nach wird bei einer um am sind noch wie einem über einen so zum war haben nur oder aber vor zur bis mehr durch man sein wurde sei".split(),
    "it": "di e il la che in a per un del è con non una le si da dei come più ma al lo sono della anche nel gli ha ci o questo suo tra se alla dal nella sul molto fra essere hanno ancora tutti quando".split(),
}
_OWNERS: dict[str, int] = {}
for _sw in STOPWORDS.values():
    for _w in set(_sw):
        _OWNERS[_w] = _OWNERS.get(_w, 0) + 1
DIACRITICS = {"pt": "ãõçâêô", "es": "ñ¿¡", "fr": "èêàçùœ", "de": "äöüß", "it": "ìòù"}
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def _script_counts(text: str) -> dict[str, int]:
    c = {"kana": 0, "han": 0, "hangul": 0, "cyrillic": 0, "latin": 0}
    for ch in text:
        o = ord(ch)
        if 0x3040 <= o <= 0x30FF:
            c["kana"] += 1
        elif 0x4E00 <= o <= 0x9FFF:
            c["han"] += 1
        elif 0xAC00 <= o <= 0xD7AF or 0x1100 <= o <= 0x11FF:
            c["hangul"] += 1
        elif 0x0400 <= o <= 0x04FF:
            c["cyrillic"] += 1
        elif ch.isalpha() and o < 0x250:
            c["latin"] += 1
    return c


def detect_language(text: str) -> tuple[str, float]:
    """(código, confiança 0..1). 'und' quando não há evidência suficiente."""
    s = _script_counts(text)
    total = sum(s.values())
    if total == 0:
        return "und", 0.0
    if s["kana"]:
        return "ja", round(min(1.0, (s["kana"] + s["han"]) / total), 2)
    if s["hangul"] / total > 0.3:
        return "ko", round(s["hangul"] / total, 2)
    if s["han"] / total > 0.3:
        return "zh", round(s["han"] / total, 2)
    if s["cyrillic"] / total > 0.3:
        return "ru", round(s["cyrillic"] / total, 2)
    words = [w.lower() for w in _WORD.findall(text)]
    if len(words) < 4:
        return "und", 0.0
    scores = {}
    for lang, sw in STOPWORDS.items():
        hits = sum(1 / _OWNERS[w] for w in words if w in sw)  # palavra exclusiva vale mais que a compartilhada
        marks = sum(1 for ch in text.lower() if ch in DIACRITICS.get(lang, ""))
        scores[lang] = hits + 0.5 * marks
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    best, second = ranked[0], ranked[1]
    if best[1] < 2 or best[1] < 1.3 * second[1]:
        return "und", 0.0
    return best[0], round(best[1] / (best[1] + second[1]), 2)


class LangIdAgent(Agent):
    name = "langid"
    actions = ("lang_detect",)
    description = "Identificação de idioma de texto (pt, en, es, fr, de, it, ja, zh, ko, ru), sem modelo."

    async def run(self, action: str, payload: dict[str, Any]) -> str:
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("payload.text é obrigatório")
        lang, conf = detect_language(text[:5000])
        return f"{lang} ({conf})"
