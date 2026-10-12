"""Exportação para um único arquivo HTML (abre em qualquer navegador,
tem modo apresentação com as setas do teclado e pode ser impresso em PDF)."""
from __future__ import annotations

from html import escape
from typing import Any

from .core import CANVAS_H


def _num(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _color(v: Any, default: str) -> str:
    s = str(v or "")
    return s if len(s) == 7 and s.startswith("#") else default


def _element_html(e: dict[str, Any], theme: dict[str, Any]) -> str:
    x = _num(e.get("x")); y = _num(e.get("y")) / CANVAS_H * 100
    w = _num(e.get("w"), 20); h = _num(e.get("h"), 10) / CANVAS_H * 100
    pos = f"left:{x:.3f}%;top:{y:.3f}%;width:{w:.3f}%;height:{h:.3f}%"
    typ = e.get("type")
    if typ == "text":
        fs = _num(e.get("fontSize"), 20)
        bullets = bool(e.get("bullets"))
        paras = "".join(f"<div>{escape(line) or '<br>'}</div>" for line in str(e.get("text", "")).split("\n"))
        justify = {"middle": "center", "bottom": "flex-end"}.get(e.get("valign"), "flex-start")
        font = escape(str(e.get("font") or theme.get("font") or "Segoe UI"), quote=True)
        style = (f"{pos};--fs:{fs:.1f};font-weight:{700 if e.get('bold') else 400};"
                 f"font-style:{'italic' if e.get('italic') else 'normal'};color:{_color(e.get('color'), '#16181D')};"
                 f"text-align:{escape(str(e.get('align', 'left')))};justify-content:{justify};"
                 f"font-family:'{font}',system-ui,sans-serif")
        return f'<div class="el txt{" bul" if bullets else ""}" style="{style}">{paras}</div>'
    if typ == "shape":
        opacity = _num(e.get("opacity"), 1.0) if e.get("opacity") is not None else 1.0
        if e.get("shape") == "ellipse":
            radius = "50%"
        else:
            radius = f"calc({_num(e.get('radius')):.2f} * 100cqw / 100)"
        border = f"border:2px solid {_color(e.get('stroke'), '#333333')};" if e.get("stroke") else ""
        return (f'<div class="el" style="{pos};background:{_color(e.get("fill"), "#6657FF")};{border}'
                f'border-radius:{radius};opacity:{opacity:.3f}"></div>')
    if typ == "image" and str(e.get("src", "")).startswith("data:image/"):
        credit = escape(str(e.get("credit", "")), quote=True)
        return (f'<div class="el" style="{pos}"><img src="{escape(str(e.get("src")), quote=True)}" '
                f'alt="{escape(str(e.get("alt", "Imagem")), quote=True)}" title="{credit}"></div>')
    return ""


def build_html(presentation: dict[str, Any]) -> bytes:
    title = escape(str(presentation.get("meta", {}).get("title", "MagicSlides")))
    theme = presentation.get("theme", {})
    slides = []
    for i, slide in enumerate(presentation.get("slides", [])):
        bg = _color(slide.get("background") or theme.get("background"), "#FFFFFF")
        elements = "".join(_element_html(e, theme) for e in slide.get("elements", []))
        notes = escape(str(slide.get("notes") or ""), quote=True)
        slides.append(f'<section class="slide" data-i="{i}" data-notes="{notes}" style="background:{bg}">{elements}</section>')
    doc = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="generator" content="MagicSlides">
<title>{title}</title><style>
html,body{{margin:0;background:#101114;font-family:'Segoe UI',system-ui,sans-serif}}
.deck{{padding:2vh 0}}
.slide{{position:relative;width:min(96vw,170.6vh);aspect-ratio:16/9;margin:0 auto 2vh;overflow:hidden;container-type:inline-size;box-shadow:0 10px 40px #0007}}
.el{{position:absolute;box-sizing:border-box;overflow:hidden}}
.txt{{display:flex;flex-direction:column;font-size:calc(var(--fs) * 100cqw / 960);line-height:1.2;white-space:pre-wrap;overflow-wrap:anywhere}}
.txt>div{{margin:0 0 .2em}}.txt.bul>div{{margin:0 0 .45em;padding-left:1.1em;position:relative}}
.txt.bul>div::before{{content:'•';position:absolute;left:0}}
.el img{{width:100%;height:100%;object-fit:cover;display:block}}
.hint{{position:fixed;right:14px;bottom:12px;color:#aaa;font:12px system-ui;background:#0009;padding:6px 10px;border-radius:8px}}
body.present{{overflow:hidden;background:#000}}body.present .deck{{padding:0}}
body.present .slide{{display:none;position:fixed;inset:0;margin:auto;width:min(100vw,177.78vh);box-shadow:none}}
body.present .slide.on{{display:block}}body.present .hint{{display:none}}
@media print{{@page{{size:13.333in 7.5in;margin:0}}body{{background:#fff}}.deck{{padding:0}}.hint{{display:none}}
.slide{{width:13.333in;margin:0;box-shadow:none;page-break-after:always;break-after:page;print-color-adjust:exact;-webkit-print-color-adjust:exact}}}}
</style></head><body><main class="deck">{''.join(slides)}</main>
<div class="hint">Pressione <b>P</b> ou <b>F5</b> para apresentar · Ctrl+P salva em PDF</div>
<script>
(()=>{{const s=[...document.querySelectorAll('.slide')];let i=0;
const show=()=>s.forEach((e,k)=>e.classList.toggle('on',k===i));
const start=()=>{{document.body.classList.add('present');show();document.documentElement.requestFullscreen?.().catch(()=>{{}})}};
const stop=()=>{{document.body.classList.remove('present');if(document.fullscreenElement)document.exitFullscreen()}};
document.addEventListener('keydown',e=>{{const on=document.body.classList.contains('present');
if(!on&&(e.key==='p'||e.key==='P'||e.key==='F5')){{e.preventDefault();start();return}}if(!on)return;
if(['ArrowRight','PageDown',' ','Enter'].includes(e.key)){{i=Math.min(s.length-1,i+1);show()}}
else if(['ArrowLeft','PageUp','Backspace'].includes(e.key)){{i=Math.max(0,i-1);show()}}
else if(e.key==='Home'){{i=0;show()}}else if(e.key==='End'){{i=s.length-1;show()}}else if(e.key==='Escape')stop()}});
document.addEventListener('click',e=>{{if(document.body.classList.contains('present')){{i=Math.min(s.length-1,i+1);show()}}}});
document.addEventListener('fullscreenchange',()=>{{if(!document.fullscreenElement)document.body.classList.remove('present')}});}})();
</script></body></html>"""
    return doc.encode("utf-8")
