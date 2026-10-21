#!/usr/bin/env python3
"""Confere os índices de rosto usados em core/src/face_swap.cpp contra as listas oficiais do MediaPipe.

Requer: pip install mediapipe   (e, no Linux, libegl1/libgles2). Não precisa de imagem nem do modelo.
Uso:    python3 tools/check_face_indices.py
"""
import os
import re
import sys

from mediapipe.tasks.python import vision

src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../core/src/face_swap.cpp"), encoding="utf-8").read()


def arr(name):
    body = re.sub(r"//[^\n]*", "", re.search(r"const int %s\[\] = \{(.*?)\};" % name, src, re.S).group(1))
    return [int(x) for x in re.findall(r"\d+", body)]


oval, inner = arr("kOval"), arr("kInner")
C = vision.FaceLandmarksConnections
edges = lambda c: {frozenset((e.start, e.end)) for e in c}
verts = lambda c: {e.start for e in c} | {e.end for e in c}
ok = True


def check(cond, msg):
    global ok
    print(("OK    " if cond else "FALHA ") + msg)
    ok = ok and cond


check(set(oval) == verts(C.FACE_LANDMARKS_FACE_OVAL), "contorno = FACE_OVAL oficial")
check(all(frozenset((oval[i], oval[(i + 1) % len(oval)])) in edges(C.FACE_LANDMARKS_FACE_OVAL) for i in range(len(oval))),
      "contorno percorrido em ordem forma o laço oficial")
for n, g in (("olho esquerdo", C.FACE_LANDMARKS_LEFT_EYE), ("olho direito", C.FACE_LANDMARKS_RIGHT_EYE), ("lábios", C.FACE_LANDMARKS_LIPS),
             ("sobrancelha esquerda", C.FACE_LANDMARKS_LEFT_EYEBROW), ("sobrancelha direita", C.FACE_LANDMARKS_RIGHT_EYEBROW)):
    check(verts(g) <= set(inner), n + " completo no subconjunto")
check(max(oval + inner) < 478, "índices < 478")
sys.exit(0 if ok else 1)
