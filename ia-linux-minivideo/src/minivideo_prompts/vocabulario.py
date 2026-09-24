"""Ficha do vídeo: o que o assistente pergunta e como cada resposta vira prompt.

As dimensões de "estética de cinema" (período, luz, tom, plano, ângulo,
movimento) seguem a ideia do extensor de prompts do Wan2.2 (Apache-2.0,
wan/utils/prompt_extend.py) e a estrutura do LTX-Video (ação → movimentos →
aparência → cenário → câmera → luz). O texto, as listas e as regras daqui
são próprios deste projeto.

Cada campo tem: pergunta em português, opções (rótulo → texto em inglês,
que é a língua em que Wan e LTX foram treinados) e palavras que o
reconhecem numa frase livre.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Tuple


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


# campo: (pergunta, obrigatório, [(rótulo, inglês, [palavras-chave normalizadas])])
CAMPOS: Dict[str, Tuple[str, bool, List[Tuple[str, str, List[str]]]]] = {
    "assunto": ("Quem ou o que aparece? (pessoa, animal, objeto, lugar)", True, []),
    "acao": ("O que acontece na cena? Descreva o movimento principal.", False, []),
    "cenario": ("Onde se passa? Descreva o ambiente ao fundo.", False, []),
    "estilo": ("Qual estilo?", False, [
        ("realista (cinema)", "photorealistic, cinematic film look", ["realista", "cinema", "filme", "real"]),
        ("documentário", "documentary style, natural handheld feel", ["documentario"]),
        ("animação 3D", "3D animated style, soft global illumination", ["3d", "pixar"]),
        ("animação 2D", "2D hand-drawn animation style", ["2d", "desenho", "anime", "cartoon"]),
        ("publicidade", "clean commercial advertising look", ["publicidade", "comercial", "propaganda", "produto"]),
    ]),
    "periodo": ("Em que momento do dia?", False, [
        ("dia", "daytime", ["dia", "manha", "tarde"]),
        ("noite", "night time", ["noite", "noturn"]),
        ("amanhecer", "dawn", ["amanhecer", "madrugada", "aurora"]),
        ("pôr do sol", "golden hour sunset", ["por do sol", "entardecer", "crepusculo", "golden hour"]),
    ]),
    "luz": ("Como é a luz?", False, [
        ("luz do sol", "natural sunlight", ["luz do sol", "sol forte", "ensolarad"]),
        ("nublado (suave)", "soft overcast light", ["nublad", "suave", "difusa"]),
        ("luz artificial", "practical artificial lighting from lamps", ["lampada", "artificial", "estudio"]),
        ("luar", "cool moonlight", ["luar", "lua"]),
        ("fogo / velas", "warm firelight", ["fogo", "vela", "fogueira", "lareira"]),
        ("neon", "colorful neon lighting", ["neon"]),
    ]),
    "tom": ("Tom de cor?", False, [
        ("quente", "warm color palette", ["quente", "dourad", "alaranjad"]),
        ("frio", "cool color palette", ["frio", "azulad"]),
        ("neutro", "natural neutral colors", ["neutro", "natural"]),
    ]),
    "plano": ("Enquadramento (tamanho do plano)?", False, [
        ("close-up", "close-up shot", ["close", "rosto", "detalhe"]),
        ("plano médio", "medium shot", ["plano medio", "cintura", "medio"]),
        ("plano aberto", "wide shot", ["aberto", "corpo inteiro", "plano geral", "panorama"]),
        ("plano muito aberto", "extreme wide shot", ["muito aberto", "paisagem"]),
    ]),
    "angulo": ("Ângulo da câmera?", False, [
        ("altura dos olhos", "eye-level angle", ["altura dos olhos", "frontal"]),
        ("de baixo", "low-angle shot", ["de baixo", "contra-plongee", "baixo para cima"]),
        ("de cima", "high-angle shot", ["de cima", "plongee", "cima para baixo"]),
        ("aéreo (drone)", "aerial drone shot", ["drone", "aere"]),
        ("sobre o ombro", "over-the-shoulder shot", ["ombro"]),
    ]),
    "movimento": ("A câmera se move?", False, [
        ("parada", "static camera", ["parada", "fixa", "tripe"]),
        ("acompanha (travelling)", "smooth tracking shot following the subject", ["acompanha", "travelling", "segue"]),
        ("panorâmica", "slow pan", ["panoramica", "pan"]),
        ("aproxima (zoom in)", "slow push-in", ["aproxima", "zoom in", "push"]),
        ("afasta (zoom out)", "slow pull-back", ["afasta", "zoom out"]),
        ("na mão", "handheld camera", ["na mao", "tremida"]),
        ("gira em volta", "orbiting camera around the subject", ["orbita", "gira em volta", "360"]),
    ]),
    "duracao_s": ("Duração em segundos? (ex.: 5)", False, []),
    "orientacao": ("Horizontal (16:9) ou vertical (9:16)?", False, [
        ("horizontal 16:9", "landscape", ["horizontal", "16:9", "paisagem youtube"]),
        ("vertical 9:16", "portrait", ["vertical", "9:16", "reels", "tiktok", "shorts", "stories"]),
    ]),
    "evitar": ("Algo que NÃO pode aparecer? (vira o prompt negativo; Enter pula)", False, []),
}

# Ordem das perguntas: primeiro o conteúdo, depois a estética.
ORDEM = ["assunto", "acao", "cenario", "estilo", "periodo", "luz", "plano", "angulo", "movimento",
         "tom", "orientacao", "duracao_s", "evitar"]


def opcoes(campo: str) -> List[Tuple[str, str, List[str]]]:
    return CAMPOS[campo][2]


def ingles(campo: str, rotulo: str) -> Optional[str]:
    for r, en, _ in opcoes(campo):
        if r == rotulo:
            return en
    return None


def reconhecer(texto: str) -> Dict[str, str]:
    """Campos de escolha reconhecidos numa frase livre (só os que têm opções)."""
    t = " " + normalizar(texto) + " "
    achados: Dict[str, str] = {}
    for campo in ORDEM:
        melhor = None
        for rotulo, _, chaves in opcoes(campo):
            for k in chaves:
                if re.search(r"(?<![a-z])" + re.escape(k), t) and (melhor is None or len(k) > melhor[1]):
                    melhor = (rotulo, len(k))
        if melhor:
            achados[campo] = melhor[0]
    m = re.search(r"(\d{1,3})\s*(s\b|seg|segundo)", t)
    if m:
        achados["duracao_s"] = str(int(m.group(1)))
    return achados


def escolher(campo: str, resposta: str) -> Optional[str]:
    """Resposta a uma pergunta de escolha: número da opção, rótulo ou palavra-chave."""
    ops = opcoes(campo)
    r = resposta.strip()
    if r.isdigit() and 1 <= int(r) <= len(ops):
        return ops[int(r) - 1][0]
    n = normalizar(r)
    for rotulo, _, chaves in ops:
        if n == normalizar(rotulo) or any(k in n for k in chaves):
            return rotulo
    return None
