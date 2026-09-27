"""Geração do roteiro da apresentação.

Provedores:
- "anthropic": Claude, pela SDK oficial `anthropic`, com saída estruturada.
- "openai": qualquer servidor compatível com /v1/chat/completions
  (Ollama, LM Studio, llama.cpp server, OpenAI, Groq, OpenRouter...).
- "offline": sem IA — monta o roteiro a partir do texto/tópicos colados.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

from .layouts import LAYOUTS, normalize_outline


class AIError(RuntimeError):
    pass


def _str() -> dict[str, Any]:
    return {"type": "string"}


def _arr(items: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": items}


def _obj(props: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


OUTLINE_SCHEMA = _obj({
    "title": _str(),
    "subtitle": _str(),
    "slides": _arr(_obj({
        "layout": {"type": "string", "enum": LAYOUTS},
        "title": _str(),
        "subtitle": _str(),
        "bullets": _arr(_str()),
        "body": _str(),
        "quote": _str(),
        "quote_author": _str(),
        "stats": _arr(_obj({"value": _str(), "label": _str()})),
        "columns": _arr(_obj({"heading": _str(), "bullets": _arr(_str())})),
        "image_query": _str(),
        "notes": _str(),
    })),
})

SYSTEM_PROMPT = """You are MagicSlides, an expert presentation designer and writer.
You turn a topic, notes or a long text into a clear, well-structured slide deck.

Return ONLY a JSON object with this shape:
{"title": str, "subtitle": str, "slides": [ {"layout": str, "title": str, "subtitle": str,
 "bullets": [str], "body": str, "quote": str, "quote_author": str,
 "stats": [{"value": str, "label": str}], "columns": [{"heading": str, "bullets": [str]}],
 "image_query": str, "notes": str} ]}
Use empty strings/arrays for fields a slide does not use.

Layouts available:
- "title": first slide only. title + subtitle. May have image_query.
- "section": divider between parts. title + optional subtitle.
- "bullets": title + 3-5 short bullets.
- "image-right" / "image-left": title + 2-4 bullets next to a photo. image_query required.
- "image-full": full-bleed photo with title + one short sentence in body. image_query required.
- "two-column": comparison; exactly 2 columns, each with heading + 2-4 bullets.
- "stats": 2-4 key numbers (value like "73%", "3x", "R$ 2 mi") with short labels; optional body.
- "steps": a process/timeline; 3-5 bullets, each a short step.
- "quote": a relevant real quote with its author (only if you are sure it is accurate).
- "closing": last slide: conclusion / call to action / thanks.

Rules:
- The first slide must use "title"; the last should use "closing".
- Vary layouts; use photos (image-right, image-left, image-full) on roughly half of the slides.
- Bullets: max ~12 words each. No markdown, no numbering, no emojis.
- image_query: 2-5 concrete, visual keywords IN ENGLISH for a stock-photo search
  (e.g. "solar panels rooftop", "students classroom"). Never abstract words only.
- notes: 2-4 sentences of speaker notes expanding the slide.
- Never invent statistics: if unsure, prefer bullets over "stats", or state figures as approximate.
- Write all visible text (titles, bullets, notes) in the language the user asks for."""


def build_user_prompt(text: str, slides: int, language: str, tone: str) -> str:
    return (
        f"Create a presentation with exactly {slides} slides.\n"
        f"Language for all visible text: {language}.\n"
        f"Tone/style: {tone or 'clear and professional'}.\n\n"
        "The user's input below may be a short topic, an outline or a long text. "
        "If it is a text/outline, base the slides on its content and structure.\n"
        "<user_input>\n" + text.strip()[:60000] + "\n</user_input>"
    )


# ----------------------------------------------------------------- Claude ---

_FALLBACK_MODELS = ("claude-opus-5", "claude-opus-5-5", "claude-fable-5-1")


def generate_anthropic(text: str, slides: int, language: str, tone: str, cfg: dict[str, Any]) -> dict[str, Any]:
    try:
        import anthropic
    except ImportError as exc:
        raise AIError("O pacote 'anthropic' não está instalado. Rode: pip install anthropic") from exc

    key = cfg.get("anthropic_api_key") or None
    model = cfg.get("anthropic_model") or "claude-opus-5"
    effort = cfg.get("anthropic_effort") or "medium"
    kwargs: dict[str, Any] = dict(
        model=model,
        max_tokens=32000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_prompt(text, slides, language, tone)}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": OUTLINE_SCHEMA}},
    )
    use_fallbacks = model in _FALLBACK_MODELS
    try:
        client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()
        if use_fallbacks:
            # Se o modelo recusar por política, a API refaz o pedido no modelo
            # de fallback recomendado, dentro da mesma chamada.
            with client.beta.messages.stream(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs) as stream:
                message = stream.get_final_message()
        else:
            with client.messages.stream(**kwargs) as stream:
                message = stream.get_final_message()
    except anthropic.AuthenticationError as exc:
        raise AIError("Chave da Anthropic inválida. Confira em Configurações.") from exc
    except anthropic.PermissionDeniedError as exc:
        raise AIError(f"Sem permissão para usar o modelo {model}.") from exc
    except anthropic.NotFoundError as exc:
        raise AIError(f"Modelo não encontrado: {model}.") from exc
    except anthropic.RateLimitError as exc:
        raise AIError("Limite de uso da API atingido. Aguarde um pouco e tente de novo.") from exc
    except anthropic.APIStatusError as exc:
        raise AIError(f"Erro da API Anthropic ({exc.status_code}): {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise AIError("Não foi possível conectar à API da Anthropic. Verifique a internet.") from exc
    except anthropic.AnthropicError as exc:
        raise AIError(f"Falha ao chamar o Claude: {exc}. Informe a chave em Configurações.") from exc

    if message.stop_reason == "refusal":
        raise AIError("O modelo recusou este pedido. Tente reformular o tema.")
    if message.stop_reason == "max_tokens":
        raise AIError("A resposta ficou longa demais. Peça menos slides ou um texto menor.")
    text_out = "".join(b.text for b in message.content if getattr(b, "type", "") == "text")
    return parse_json_object(text_out)


# ------------------------------------------------------- OpenAI compatível ---

def generate_openai_compatible(text: str, slides: int, language: str, tone: str, cfg: dict[str, Any]) -> dict[str, Any]:
    base = (cfg.get("openai_base_url") or "").rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise AIError("URL do servidor de IA inválida (ex.: http://localhost:11434/v1).")
    model = cfg.get("openai_model") or ""
    if not model:
        raise AIError("Informe o nome do modelo (ex.: llama3.1, qwen2.5, gpt-4o-mini).")
    body: dict[str, Any] = {
        "model": model,
        "temperature": 0.6,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(text, slides, language, tone)},
        ],
        "response_format": {"type": "json_object"},
    }
    headers = {"Content-Type": "application/json"}
    if cfg.get("openai_api_key"):
        headers["Authorization"] = f"Bearer {cfg['openai_api_key']}"

    def call(payload: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(base + "/chat/completions", data=json.dumps(payload).encode("utf-8"),
                                     headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=600) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        try:
            result = call(body)
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 422):  # servidor sem suporte a response_format
                body.pop("response_format", None)
                result = call(body)
            else:
                raise
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        if exc.code == 401:
            raise AIError("Chave de API recusada pelo servidor de IA.") from exc
        raise AIError(f"Servidor de IA respondeu {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AIError(f"Não foi possível conectar a {base}. O Ollama/LM Studio está aberto?") from exc
    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AIError("Resposta inesperada do servidor de IA.") from exc
    return parse_json_object(content or "")


def parse_json_object(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        value = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise AIError("A IA não devolveu um JSON válido. Tente novamente.")
        try:
            value = json.loads(text[start:end + 1])
        except ValueError as exc:
            raise AIError("A IA não devolveu um JSON válido. Tente novamente.") from exc
    if not isinstance(value, dict):
        raise AIError("A IA não devolveu um objeto JSON.")
    return value


# ---------------------------------------------------------------- offline ---

_BULLET = re.compile(r"^\s*(?:[-*•·–]|\d+[.)])\s+")
_HEADING = re.compile(r"^\s*#{1,6}\s+")


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?;])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def generate_offline(text: str, slides: int, language: str = "", tone: str = "") -> dict[str, Any]:
    """Sem IA: estrutura o texto colado. Títulos (# ou linhas curtas sem
    ponto final) viram slides; listas viram tópicos; parágrafos são quebrados
    em frases. Um tema curto gera um esqueleto para o usuário completar."""
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n")]
    non_empty = [ln for ln in lines if ln.strip()]
    if len(non_empty) <= 1 and len(text.strip()) <= 160:
        return _skeleton(text.strip() or "Minha apresentação", slides)

    title = _HEADING.sub("", non_empty[0]).strip() if non_empty else "Apresentação"
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw in non_empty[1:]:
        line = raw.strip()
        is_heading = bool(_HEADING.match(line)) or (
            not _BULLET.match(line) and len(line) <= 70 and not line.endswith((".", "!", "?", ";", ":", ","))
            and (current is None or current["items"])
        )
        if is_heading:
            current = {"title": _HEADING.sub("", line).strip(), "items": []}
            sections.append(current)
            continue
        if current is None:
            current = {"title": title, "items": []}
            sections.append(current)
        if _BULLET.match(line):
            current["items"].append(_BULLET.sub("", line))
        else:
            current["items"].extend(_sentences(line))

    out_slides: list[dict[str, Any]] = [{"layout": "title", "title": title, "subtitle": "",
                                          "image_query": title}]
    cycle = ["image-right", "bullets", "image-left", "bullets"]
    for i, sec in enumerate(sections):
        items = sec["items"]
        chunks = [items[j:j + 5] for j in range(0, len(items), 5)] or [[]]
        for k, chunk in enumerate(chunks):
            layout = cycle[(i + k) % len(cycle)] if chunk else "section"
            t = sec["title"] + (f" ({k + 1})" if len(chunks) > 1 else "")
            out_slides.append({"layout": layout, "title": t, "bullets": chunk,
                               "image_query": f"{title} {sec['title']}"})
    out_slides = out_slides[:max(1, slides - 1)]
    out_slides.append({"layout": "closing", "title": "Obrigado!", "subtitle": title})
    return {"title": title, "subtitle": "", "slides": out_slides}


def _skeleton(topic: str, slides: int) -> dict[str, Any]:
    plan = [
        ("image-right", f"O que é {topic}", ["Definição em uma frase", "Onde aparece no dia a dia", "Por que vale a pena conhecer"]),
        ("bullets", "Por que isso importa", ["Impacto principal", "Quem é afetado", "O que muda na prática"]),
        ("two-column", "Vantagens e desafios", []),
        ("steps", "Como funciona", ["Primeiro passo", "Segundo passo", "Terceiro passo", "Resultado"]),
        ("image-left", "Exemplos práticos", ["Exemplo 1", "Exemplo 2", "Exemplo 3"]),
        ("image-full", topic, []),
        ("bullets", "Próximos passos", ["Ação imediata", "Ação de médio prazo", "Como medir o sucesso"]),
    ]
    out = [{"layout": "title", "title": topic, "subtitle": "Apresentação criada com MagicSlides", "image_query": topic}]
    for i in range(max(0, slides - 2)):
        layout, title, bullets = plan[i % len(plan)]
        spec: dict[str, Any] = {"layout": layout, "title": title, "bullets": bullets, "image_query": topic,
                                "notes": "Rascunho gerado sem IA: substitua os tópicos pelo seu conteúdo."}
        if layout == "two-column":
            spec["columns"] = [{"heading": "Vantagens", "bullets": ["Vantagem 1", "Vantagem 2"]},
                               {"heading": "Desafios", "bullets": ["Desafio 1", "Desafio 2"]}]
        if layout == "image-full":
            spec["body"] = "Uma imagem que resume a ideia central."
        out.append(spec)
    out.append({"layout": "closing", "title": "Obrigado!", "subtitle": topic})
    return {"title": topic, "subtitle": "", "slides": out}


# ------------------------------------------------------------------ entrada ---

def generate_outline(text: str, slides: int, language: str, tone: str, cfg: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Devolve (roteiro normalizado, nome do provedor usado)."""
    text = (text or "").strip()
    if not text:
        raise AIError("Descreva o tema ou cole um texto para gerar a apresentação.")
    slides = max(3, min(40, int(slides or 8)))
    provider = cfg.get("provider", "offline")
    if provider == "anthropic":
        raw = generate_anthropic(text, slides, language, tone, cfg)
        used = f"Claude ({cfg.get('anthropic_model')})"
    elif provider == "openai":
        raw = generate_openai_compatible(text, slides, language, tone, cfg)
        used = f"{cfg.get('openai_model')} @ {cfg.get('openai_base_url')}"
    else:
        raw = generate_offline(text, slides, language, tone)
        used = "Modo offline (sem IA)"
    return normalize_outline(raw, max_slides=slides), used
