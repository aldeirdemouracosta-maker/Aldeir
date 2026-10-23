#!/usr/bin/env python3
"""Renderiza docs/mockup/hero_scene.svg em 1080x1920 e grava app/src/main/res/drawable-nodpi/hero_scene.webp
(imagem comum: mais leve e mais segura de carregar no Android do que um VectorDrawable de 485 formas).
Requer Chromium/Chrome (--chrome) e Pillow. Uso:  python3 tools/render_hero_webp.py [--chrome /caminho/chrome]"""
import argparse, os, subprocess, sys, tempfile
from PIL import Image

root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ap = argparse.ArgumentParser()
ap.add_argument("--chrome", default=os.environ.get("CHROME", "chromium"))
a = ap.parse_args()
svg = os.path.join(root, "docs/mockup/hero_scene.svg")
out = os.path.join(root, "app/src/main/res/drawable-nodpi/hero_scene.webp")
os.makedirs(os.path.dirname(out), exist_ok=True)
with tempfile.TemporaryDirectory() as d:
    html = os.path.join(d, "p.html"); png = os.path.join(d, "s.png")
    open(html, "w").write(f"<html><body style='margin:0;background:#000'><img src='file://{svg}' style='width:1080px;height:1920px;display:block'></body></html>")
    # a janela headless perde ~90 px de altura: pede mais e recorta
    subprocess.run([a.chrome, "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                    f"--screenshot={png}", "--window-size=1080,2200", "file://" + html], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    im = Image.open(png).convert("RGB")
    if im.height < 1920: sys.exit("captura menor que 1920 px: aumente a janela")
    im.crop((0, 0, 1080, 1920)).save(out, "WEBP", quality=88, method=6)
print(out, os.path.getsize(out) // 1024, "KB")
