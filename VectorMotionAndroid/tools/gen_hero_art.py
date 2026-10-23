#!/usr/bin/env python3
"""Gera a arte de herói do app a partir de UMA descrição vetorial:

  * docs/mockup/hero_scene.svg                      (usada no mockup HTML)
  * (o app usa app/src/main/res/drawable-nodpi/hero_scene.webp, gerado por tools/render_hero_webp.py)

Cena: pistoleiro de sobretudo e óculos escuros, de cabeça para baixo em "bullet time", atirando com duas
submetralhadoras contra um ciborgue de jaqueta e óculos escuros com uma escopeta calibre 12; chuva, cidade
neon, chuva de código verde, fagulhas, cartuchos e estilhaços. Personagens são silhuetas genéricas
inspiradas no gênero (sem rosto/semelhança de atores ou marcas).

Uso:  python3 tools/gen_hero_art.py
"""
import math
import os
import random

W, H = 540, 960
rnd = random.Random(2026)
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

defs = []    # gradientes
nodes = []   # (d, fill, alpha, stroke, sw, salpha, grad)
_gid = [0]


def f(v):
    return ("%.1f" % v).rstrip("0").rstrip(".")


def grad(kind, params, stops):
    _gid[0] += 1
    gid = "g%d" % _gid[0]
    defs.append((gid, kind, params, stops))
    return gid


def lin(x1, y1, x2, y2, stops):
    return grad("linear", (x1, y1, x2, y2), stops)


def rad(cx, cy, r, stops):
    return grad("radial", (cx, cy, r), stops)


def P(d, fill=None, alpha=1.0, stroke=None, sw=0.0, salpha=1.0, g=None):
    nodes.append((d, fill, alpha, stroke, sw, salpha, g))


def poly(pts, close=True):
    s = "M" + " L".join("%s,%s" % (f(x), f(y)) for x, y in pts)
    return s + (" Z" if close else "")


def line(pts):
    return poly(pts, close=False)


def ellipse(cx, cy, rx, ry):
    return "M%s,%s a%s,%s 0 1,0 %s,0 a%s,%s 0 1,0 %s,0 Z" % (
        f(cx - rx), f(cy), f(rx), f(ry), f(2 * rx), f(rx), f(ry), f(-2 * rx))


def rect(x, y, w, h):
    return "M%s,%s h%s v%s h%s Z" % (f(x), f(y), f(w), f(h), f(-w))


def rot_rect(cx, cy, w, h, ang):
    c, s = math.cos(ang), math.sin(ang)
    pts = []
    for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)):
        pts.append((cx + dx * c - dy * s, cy + dx * s + dy * c))
    return poly(pts)


def glow(cx, cy, r, color, a=0.6):
    """Halo suave (aproxima o 'blur' que o VectorDrawable não tem)."""
    c = color.lstrip("#")
    g = rad(cx, cy, r, [(0, "#%02X%s" % (int(a * 255), c)), (0.45, "#%02X%s" % (int(a * 90), c)), (1, "#00%s" % c)])
    P(ellipse(cx, cy, r, r), g=g)


def star(cx, cy, r1, r2, n, rot=0.0):
    pts = []
    for i in range(n * 2):
        a = rot + i * math.pi / n
        r = r1 if i % 2 == 0 else r2
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return poly(pts)


# --------------------------------------------------------------------------- cenário
def background():
    P(rect(0, 0, W, 660), g=lin(0, 0, 0, 660, [(0, "#FF04060B"), (0.55, "#FF0A1820"), (1, "#FF16242C")]))
    for _ in range(9):  # nuvens de tempestade
        cx, cy, r = rnd.uniform(-20, 560), rnd.uniform(20, 300), rnd.uniform(90, 190)
        glow(cx, cy, r, "#3C5662", 0.22)
    # chuva de código (Matrix) por trás da cidade
    tiers = {0.10: [], 0.22: [], 0.42: []}
    for x in range(6, W, 13):
        y = rnd.uniform(-60, 340)
        n = rnd.randint(5, 18)
        for i in range(n):
            a = 0.10 if i < n * 0.5 else (0.22 if i < n - 1 else 0.42)
            tiers[a].append(rect(x, y + i * 11, 4.5, 7))
    for a, items in tiers.items():
        P(" ".join(items), fill="#35FF86", alpha=a)


def city(base, n, hmin, hmax, color, wins, seed):
    r = random.Random(seed)
    x = -10
    lit = {"#FFC15A": [], "#59E3FF": [], "#FF4D8D": [], "#FF2B2B": []}
    body = []
    while x < W + 10:
        w = r.uniform(24, 64)
        h = r.uniform(hmin, hmax)
        top = base - h
        body.append(rect(x, top, w, h + 4))
        if r.random() < 0.35:
            body.append(rect(x + w * 0.35, top - r.uniform(10, 34), w * 0.3, 40))
        if r.random() < 0.3:
            body.append(rect(x + w * 0.48, top - r.uniform(26, 60), 1.6, 70))
        if wins:
            for wx in range(int(x + 4), int(x + w - 4), 8):
                for wy in range(int(top + 6), int(base - 4), 10):
                    if r.random() < wins:
                        lit[r.choice(list(lit))].append(rect(wx, wy, 3.4, 4.6))
        x += w + r.uniform(-2, 6)
    P(" ".join(body), fill=color)
    for c, items in lit.items():
        if items:
            P(" ".join(items), fill=c, alpha=0.8)


def neon():
    signs = [(24, 330, 54, 14, "#FF2B2B"), (432, 300, 70, 12, "#FF4D8D"),
             (470, 410, 40, 10, "#59E3FF"), (90, 440, 46, 10, "#FFC15A"), (300, 360, 36, 9, "#35FF86")]
    for x, y, w, h, c in signs:
        glow(x + w / 2, y + h / 2, w * 1.1, c, 0.55)
        P(rect(x, y, w, h), fill=c, alpha=0.95)


def ground():
    P(rect(0, 640, W, 320), g=lin(0, 640, 0, 960, [(0, "#FF0B1218"), (0.4, "#FF0E171D"), (1, "#FF05080C")]))
    # reflexos de néon no chão molhado
    for x, c in ((50, "#FF2B2B"), (455, "#FF4D8D"), (490, "#59E3FF"), (110, "#FFC15A"), (318, "#35FF86")):
        P(rect(x - 6, 650, 12, 160), g=lin(0, 650, 0, 810, [(0, "#66" + c[1:]), (1, "#00" + c[1:])]))
    for _ in range(26):  # poças e brilho
        x, y = rnd.uniform(0, W), rnd.uniform(680, 940)
        P(line([(x, y), (x + rnd.uniform(30, 90), y)]), stroke="#8FB4C8", sw=0.8, salpha=rnd.uniform(0.08, 0.25))


def center_glow():
    glow(300, 470, 300, "#FF8A2A", 0.40)
    glow(300, 470, 150, "#FFE3A0", 0.30)


# --------------------------------------------------------------------------- personagens
BODY = "#05070A"
RIM_R = "#FF3B3B"
RIM_C = "#59E3FF"


def limb(pts, w, color=BODY):
    P(line(pts), stroke=color, sw=w)


def rimlimb(pts, w, rim=RIM_C, body="#0C121A", ra=0.6):
    """Membro com contorno de luz (separa a silhueta do fundo escuro)."""
    P(line(pts), stroke=rim, sw=w + 2.6, salpha=ra)
    P(line(pts), stroke=body, sw=w)


def terminator():
    # luz vermelha de fundo (vaza pelos contornos)
    glow(410, 560, 190, "#FF1F1F", 0.28)
    # pernas + botas
    rimlimb([(396, 640), (388, 722), (384, 792)], 27, RIM_R, BODY, 0.55)
    rimlimb([(424, 640), (432, 722), (440, 792)], 27, RIM_R, BODY, 0.35)
    P(poly([(364, 790), (402, 790), (410, 808), (360, 808)]), fill="#020304")
    P(poly([(422, 790), (460, 790), (468, 808), (418, 808)]), fill="#020304")
    # jaqueta
    P("M350,480 C358,462 390,454 410,454 C434,454 464,462 472,482 L482,566 L474,668 L346,668 L338,566 Z", fill=BODY)
    P(line([(350, 480), (338, 566), (346, 668)]), stroke=RIM_R, sw=1.6, salpha=0.8)
    P(line([(472, 482), (482, 566)]), stroke=RIM_R, sw=1.2, salpha=0.4)
    P(line([(396, 460), (410, 520), (424, 460)]), stroke="#1E252C", sw=2)      # gola em V
    # cabeça, pescoço e cabelo
    P(rect(399, 438, 22, 22), fill="#080A0D")
    P(ellipse(410, 424, 21, 27), fill="#0A0C10")
    P("M389,414 C390,392 430,392 431,414 C424,402 396,402 389,414 Z", fill="#020304")
    glow(410, 428, 34, "#FF1A1A", 0.55)                                    # brilho do olho
    P(rect(388, 419, 44, 11), fill="#000000")                              # óculos escuros
    P(line([(391, 421.5), (426, 421.5)]), stroke="#FFFFFF", sw=1, salpha=0.55)
    P(ellipse(401, 430.5, 4, 1.2), fill="#FF2A2A", alpha=0.9)
    P(ellipse(419, 430.5, 4, 1.2), fill="#FF2A2A", alpha=0.9)
    P(line([(389, 412), (386, 440), (396, 452)]), stroke=RIM_R, sw=1.2, salpha=0.7)
    # escopeta calibre 12 apontada para o herói
    P(line([(404, 566), (262, 480)]), stroke="#0B0F14", sw=7)               # cano + tubo
    P(line([(404, 559), (266, 476)]), stroke="#8FA3B5", sw=0.9, salpha=0.7)
    P(line([(332, 526), (352, 538)]), stroke="#05070A", sw=12)              # bomba (pump)
    P(line([(404, 566), (440, 586)]), stroke="#05070A", sw=13)              # coronha
    # braços
    rimlimb([(356, 492), (346, 552), (334, 524)], 23, RIM_R, BODY, 0.55)
    rimlimb([(466, 492), (470, 566), (402, 566)], 23, RIM_R, BODY, 0.35)
    P(line([(356, 492), (346, 552)]), stroke=RIM_R, sw=1.2, salpha=0.55)
    # cartucho ejetado
    P(rot_rect(386, 548, 9, 4, -0.7), fill="#E5483A")
    P(line([(386, 548), (402, 536)]), stroke="#FFC15A", sw=0.8, salpha=0.5)


def muzzle(cx, cy, size, ang, color="#FFB347"):
    glow(cx, cy, size * 2.3, color, 0.7)
    P(star(cx, cy, size * 1.5, size * 0.4, 8, ang), fill=color, alpha=0.95)
    P(star(cx, cy, size * 0.9, size * 0.25, 6, ang + 0.4), fill="#FFFBE8")


def hero():
    """Pistoleiro de cabeça para baixo (pés para cima) em bullet time, duas submetralhadoras."""
    glow(190, 340, 190, "#35FF86", 0.16)
    # linhas de velocidade atrás dele
    for i in range(9):
        y = 250 + i * 22 + rnd.uniform(-6, 6)
        P(line([(150 - rnd.uniform(0, 40), y), (-10, y + rnd.uniform(-14, 14))]), stroke="#CFE9FF", sw=0.8, salpha=0.16)
    # abas do sobretudo voando para trás (esquerda), como faixas
    for tip, base in (((12, 352), ((150, 300), (176, 340))), ((24, 296), ((158, 296), (190, 322))),
                      ((30, 410), ((150, 322), (186, 356))), ((62, 250), ((170, 292), (196, 312)))):
        (x1, y1), (x2, y2) = base
        P("M%s,%s Q%s,%s %s,%s Q%s,%s %s,%s Z" % (f(x1), f(y1), f((x1 + tip[0]) / 2), f(y1 - 26), f(tip[0]), f(tip[1]),
                                                 f((x2 + tip[0]) / 2), f(y2 + 14), f(x2), f(y2)), fill="#0C121A")
        P(line([(x1, y1), ((x1 + tip[0]) / 2, y1 - 26), tip]), stroke=RIM_C, sw=1, salpha=0.5)
    # pernas para o alto
    rimlimb([(162, 318), (126, 246), (78, 186)], 21)
    rimlimb([(190, 308), (218, 232), (192, 156)], 21)
    P(poly([(52, 180), (92, 168), (104, 192), (68, 206)]), fill="#020304", stroke=RIM_C, sw=1, salpha=0.6)
    P(poly([(174, 146), (208, 134), (218, 160), (186, 172)]), fill="#020304", stroke=RIM_C, sw=1, salpha=0.6)
    # tronco + sobretudo no peito
    rimlimb([(172, 316), (214, 396)], 40)
    P(line([(160, 330), (198, 306)]), stroke="#1C2630", sw=3)       # cinto
    # cabeça (para baixo), cabelo e óculos
    P(ellipse(236, 430, 18, 22), fill="#0C121A", stroke=RIM_C, sw=1.4, salpha=0.8)
    P("M218,440 C218,458 254,458 252,440 C246,450 226,450 218,440 Z", fill="#020304")
    P(rot_rect(240, 428, 32, 9, 0.52), fill="#000000", stroke="#59E3FF", sw=0.8, salpha=0.9)
    P(line([(226, 423), (250, 433)]), stroke="#FFFFFF", sw=1, salpha=0.8)
    glow(244, 430, 26, "#35FF86", 0.3)
    # braços para frente, uma submetralhadora em cada mão, apontadas ao alvo
    targets = [((214, 398), (264, 366), (314, 370), (404, 520)),
               ((220, 412), (262, 428), (314, 426), (402, 540))]
    muz = []
    for sh, el, hand, tgt in targets:
        rimlimb([sh, el, hand], 17)
        a = math.atan2(tgt[1] - hand[1], tgt[0] - hand[0])
        ex, ey = hand[0] + 40 * math.cos(a), hand[1] + 40 * math.sin(a)
        P(line([hand, (ex, ey)]), stroke="#0D1117", sw=9)
        P(line([(hand[0] + 6, hand[1] + 4), (ex, ey - 2)]), stroke="#9AB0C4", sw=0.9, salpha=0.7)
        P(line([(hand[0] + 6, hand[1] + 6), (hand[0] + 2, hand[1] + 28)]), stroke="#0D1117", sw=7)   # carregador
        muz.append((ex, ey, a, tgt))
        muzzle(ex + 4 * math.cos(a), ey + 4 * math.sin(a), 11, a)
    return muz


def tracers(muz):
    for ex, ey, a, tgt in muz:
        for i, off in enumerate((-14, -4, 6, 16, 28)):
            tx, ty = tgt[0] + off * 0.8, tgt[1] + off
            hit = i in (1, 2, 3)
            if not hit:
                tx, ty = tgt[0] + 90 + off * 3, tgt[1] + 160 + off * 4        # erram e atingem o cenário
            P(line([(ex, ey), (tx, ty)]), stroke="#FF8A2A", sw=5, salpha=0.20)
            P(line([(ex, ey), (tx, ty)]), stroke="#FFF3C8", sw=1.3, salpha=0.95)
            mx, my = ex + (tx - ex) * 0.55, ey + (ty - ey) * 0.55          # anéis de "bullet time"
            P(ellipse(mx, my, 7, 2.6), stroke="#CFE9FF", sw=0.7, salpha=0.5)
            P(ellipse(mx, my, 12, 4.2), stroke="#CFE9FF", sw=0.5, salpha=0.3)


def sparks(cx, cy, n, rmin, rmax, big=True):
    glow(cx, cy, rmax * 0.8, "#FFA040", 0.55)
    if big:
        P(star(cx, cy, rmax * 0.45, rmax * 0.1, 7, rnd.uniform(0, 3)), fill="#FFF3C8", alpha=0.95)
    for _ in range(n):
        a = rnd.uniform(0, 2 * math.pi)
        r1 = rnd.uniform(rmin * 0.3, rmin)
        r2 = rnd.uniform(rmin, rmax)
        P(line([(cx + r1 * math.cos(a), cy + r1 * math.sin(a)), (cx + r2 * math.cos(a), cy + r2 * math.sin(a))]),
          stroke=rnd.choice(["#FFD166", "#FF9F3A", "#FFFFFF", "#FF6A2A"]), sw=rnd.uniform(0.6, 1.8), salpha=rnd.uniform(0.6, 1))


def shards(cx, cy, n, spread, smin, smax, rim="#9FB4C6"):
    for _ in range(n):
        x = cx + rnd.gauss(0, spread)
        y = cy + rnd.gauss(0, spread * 0.8)
        s = rnd.uniform(smin, smax)
        k = rnd.randint(3, 5)
        a0 = rnd.uniform(0, 6.28)
        pts = []
        for i in range(k):
            a = a0 + i * 2 * math.pi / k + rnd.uniform(-0.4, 0.4)
            r = s * rnd.uniform(0.4, 1.0)
            pts.append((x + r * math.cos(a), y + r * math.sin(a)))
        P(poly(pts), fill="#1B232B", alpha=0.95, stroke=rim, sw=0.6, salpha=0.8)


def casings(muz):
    for ex, ey, a, tgt in muz:
        for i in range(7):
            x = ex - 40 - i * 15 + rnd.uniform(-8, 8)
            y = ey - 20 - i * 10 + rnd.uniform(-10, 10)
            P(line([(x, y), (x + 20, y + 11)]), stroke="#FFD166", sw=0.8, salpha=0.25)
            P(rot_rect(x, y, 5.5, 2.4, rnd.uniform(0, 3.1)), fill="#E8B84A")


def rain():
    d = []
    for _ in range(170):
        x, y = rnd.uniform(-20, W + 20), rnd.uniform(-20, H)
        d.append("M%s,%s l%s,%s" % (f(x), f(y), f(-5), f(rnd.uniform(18, 40))))
    P(" ".join(d), stroke="#C8DDF0", sw=0.7, salpha=0.28)


def foreground():
    # estilhaços grandes em primeiro plano, com luz de contorno
    P(poly([(0, 860), (46, 826), (88, 870), (60, 960), (0, 960)]), fill="#06090C", stroke="#59E3FF", sw=1.2, salpha=0.6)
    P(poly([(540, 840), (500, 808), (452, 858), (470, 960), (540, 960)]), fill="#06090C", stroke="#FF3B3B", sw=1.2, salpha=0.6)
    shards(120, 800, 18, 90, 4, 10)
    shards(440, 790, 18, 90, 4, 10, "#FF9F7A")


def build():
    background()
    city(640, 0, 150, 330, "#0A1219", 0.22, 1)
    city(668, 0, 110, 250, "#070C12", 0.30, 2)
    neon()
    ground()
    center_glow()
    terminator()
    muz = hero()
    tracers(muz)
    casings(muz)
    for ex, ey, a, tgt in muz:
        sparks(tgt[0] + rnd.uniform(-6, 6), tgt[1] + rnd.uniform(-6, 6), 22, 14, 44)
    sparks(262, 480, 14, 8, 30, big=False)           # clarão da escopeta
    sparks(520, 700, 30, 10, 60)                     # impactos que erraram
    sparks(468, 640, 24, 8, 46)
    for cx, cy in ((400, 520), (360, 600), (470, 560), (300, 520), (500, 700), (150, 700), (250, 760)):
        shards(cx, cy, 10, 55, 2.5, 7)
    shards(300, 480, 40, 200, 1.5, 4)
    foreground()
    rain()
    glow(270, 960, 380, "#000000", 0.0)


# --------------------------------------------------------------------------- saídas
def argb_to_svg(c):
    c = c.lstrip("#")
    if len(c) == 8:
        return "#" + c[2:], int(c[:2], 16) / 255.0
    return "#" + c, 1.0


def write_svg(path):
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" preserveAspectRatio="xMidYMid slice">' % (W, H), "<defs>"]
    for gid, kind, p, stops in defs:
        if kind == "linear":
            out.append('<linearGradient id="%s" gradientUnits="userSpaceOnUse" x1="%s" y1="%s" x2="%s" y2="%s">' % ((gid,) + tuple(f(v) for v in p)))
        else:
            out.append('<radialGradient id="%s" gradientUnits="userSpaceOnUse" cx="%s" cy="%s" r="%s">' % ((gid,) + tuple(f(v) for v in p)))
        for off, col in stops:
            c, a = argb_to_svg(col)
            out.append('<stop offset="%s" stop-color="%s" stop-opacity="%.2f"/>' % (f(off), c, a))
        out.append("</linearGradient>" if kind == "linear" else "</radialGradient>")
    out.append("</defs>")
    for d, fill, alpha, stroke, sw, salpha, g in nodes:
        a = ['d="%s"' % d]
        if g:
            a.append('fill="url(#%s)"' % g)
        elif fill:
            a.append('fill="%s"' % fill)
            if alpha < 1:
                a.append('fill-opacity="%.2f"' % alpha)
        else:
            a.append('fill="none"')
        if stroke:
            a.append('stroke="%s" stroke-width="%s" stroke-linecap="round" stroke-linejoin="round"' % (stroke, f(sw)))
            if salpha < 1:
                a.append('stroke-opacity="%.2f"' % salpha)
        out.append("<path %s/>" % " ".join(a))
    out.append("</svg>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))


def write_vd(path):
    out = ['<?xml version="1.0" encoding="utf-8"?>',
           '<vector xmlns:android="http://schemas.android.com/apk/res/android"',
           '    xmlns:aapt="http://schemas.android.com/aapt"',
           '    android:width="%ddp" android:height="%ddp"' % (W, H),
           '    android:viewportWidth="%d" android:viewportHeight="%d">' % (W, H)]
    for d, fill, alpha, stroke, sw, salpha, g in nodes:
        for chunk in split_path(d):
            a = ['android:pathData="%s"' % chunk]
            body = ""
            if g:
                gid, kind, p, stops = next(x for x in defs if x[0] == g)
                if kind == "linear":
                    gx = 'android:type="linear" android:startX="%s" android:startY="%s" android:endX="%s" android:endY="%s"' % tuple(f(v) for v in p)
                else:
                    gx = 'android:type="radial" android:centerX="%s" android:centerY="%s" android:gradientRadius="%s"' % tuple(f(v) for v in p)
                items = "".join('<item android:offset="%s" android:color="#%s"/>' % (f(o), c.lstrip("#")) for o, c in stops)
                body = '<aapt:attr name="android:fillColor"><gradient %s>%s</gradient></aapt:attr>' % (gx, items)
            elif fill:
                a.append('android:fillColor="%s"' % fill)
                if alpha < 1:
                    a.append('android:fillAlpha="%.2f"' % alpha)
            if stroke:
                a.append('android:strokeColor="%s" android:strokeWidth="%s" android:strokeLineCap="round" android:strokeLineJoin="round"' % (stroke, f(sw)))
                if salpha < 1:
                    a.append('android:strokeAlpha="%.2f"' % salpha)
            if body:
                out.append("<path %s>%s</path>" % (" ".join(a), body))
            else:
                out.append("<path %s/>" % " ".join(a))
    out.append("</vector>")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))


def split_path(d, limit=12000):
    """Divide pathData enorme em pedaços nos limites de subcaminho ('M')."""
    if len(d) <= limit:
        return [d]
    parts, cur = [], ""
    for seg in d.replace(" M", "\nM").split("\n"):
        if len(cur) + len(seg) > limit and cur:
            parts.append(cur)
            cur = ""
        cur += (" " if cur else "") + seg
    if cur:
        parts.append(cur)
    return parts


if __name__ == "__main__":
    build()
    os.makedirs(os.path.join(ROOT, "docs/mockup"), exist_ok=True)
    write_svg(os.path.join(ROOT, "docs/mockup/hero_scene.svg"))
    # o app usa o WebP gerado por tools/render_hero_webp.py (um VectorDrawable de 485 formas é pesado e arriscado)
    print("paths:", len(nodes), "gradientes:", len(defs))
