"""Gera o ícone do MagicSlides (PNG e ICO) com Pillow."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]


def draw(size: int = 512) -> Image.Image:
    s = size
    grad = Image.new("RGB", (s, s))
    top, bottom = (124, 108, 255), (184, 108, 255)
    px = grad.load()
    for y in range(s):
        for x in range(s):
            t = (x + y) / (2 * s)
            px[x, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    mask = Image.new("L", (s, s), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, s - 1, s - 1), radius=int(s * 0.22), fill=255)
    icon = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    icon.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(icon)
    # "slide" branco
    m = s * 0.2
    d.rounded_rectangle((m, s * 0.3, s - m, s * 0.74), radius=int(s * 0.05), fill=(255, 255, 255, 235))
    d.rounded_rectangle((m + s * 0.07, s * 0.39, s * 0.56, s * 0.44), radius=int(s * 0.02), fill=(124, 108, 255, 255))
    d.rounded_rectangle((m + s * 0.07, s * 0.5, s * 0.66, s * 0.54), radius=int(s * 0.02), fill=(190, 184, 230, 255))
    d.rounded_rectangle((m + s * 0.07, s * 0.59, s * 0.6, s * 0.63), radius=int(s * 0.02), fill=(190, 184, 230, 255))

    # brilho mágico (estrela de 4 pontas)
    def star(cx, cy, r, fill):
        w = r * 0.28
        pts = [(cx, cy - r), (cx + w, cy - w), (cx + r, cy), (cx + w, cy + w), (cx, cy + r), (cx - w, cy + w), (cx - r, cy), (cx - w, cy - w)]
        d.polygon(pts, fill=fill)

    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((s * 0.6, s * 0.08, s * 0.92, s * 0.4), fill=(255, 240, 180, 150))
    icon = Image.alpha_composite(icon, glow.filter(ImageFilter.GaussianBlur(s * 0.04)))
    d = ImageDraw.Draw(icon)
    star(s * 0.76, s * 0.24, s * 0.14, (255, 214, 102, 255))
    star(s * 0.9, s * 0.42, s * 0.05, (255, 255, 255, 255))
    return icon


if __name__ == "__main__":
    img = draw(512)
    img.resize((256, 256), Image.LANCZOS).save(ROOT / "magicslides" / "static" / "icon.png")
    img.save(ROOT / "assets" / "icon.png")
    img.save(ROOT / "assets" / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("ícones gerados")
