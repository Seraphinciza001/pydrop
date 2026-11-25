"""Génère les images de la fenêtre d'accueil animée (app/ui/splash/), pour chaque zoom d'écran Windows.

python build_assets/make_splash_assets.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
LOGO = Image.open(ROOT / "mob" / "SVG Mobile" / "logo.png").convert("RGBA")
OUT = ROOT / "app" / "ui" / "splash"
W, H = 560, 360            # taille de la fenêtre à 100 %
CX, CY = W // 2, 150       # centre du logo
BEAT = [1.0, 1.035, 1.07, 1.055, 1.0, 0.985, 1.025, 1.045, 1.02, 1.0]  # battement en deux temps


def background(s):
    w, h = round(W * s), round(H * s)
    img = Image.new("RGB", (w, h), (7, 11, 22))
    glow = Image.new("RGB", (w, h), (7, 11, 22))
    d = ImageDraw.Draw(glow)
    for r, c in ((230, (13, 30, 56)), (165, (17, 40, 74)), (100, (21, 50, 92))):
        r = r * s
        d.ellipse((CX * s - r, CY * s - r, CX * s + r, CY * s + r), fill=c)
    img = glow.filter(ImageFilter.GaussianBlur(52 * s))
    d = ImageDraw.Draw(img)
    step = 26 * s
    y = 13 * s
    while y < h:
        x = 13 * s
        while x < w:
            dist = ((x - CX * s) ** 2 + (y - CY * s) ** 2) ** .5 / s
            if dist < 260:
                a = 1 - dist / 260
                d.ellipse((x - s, y - s, x + s, y + s), fill=(int(7 + 49 * a * .45), int(11 + 178 * a * .45), int(22 + 226 * a * .45)))
            x += step
        y += step
    # disque sombre derrière le logo
    r = 62 * s
    d.ellipse((CX * s - r, CY * s - r, CX * s + r, CY * s + r), fill=(12, 22, 41), outline=(36, 92, 140), width=max(1, round(2 * s)))
    d.rectangle((0, 0, w - 1, h - 1), outline=(28, 46, 78), width=max(1, round(s)))
    return img


def main():
    for s in (1.0, 1.25, 1.5, 2.0):
        folder = OUT / f"s{int(s * 100)}"
        folder.mkdir(parents=True, exist_ok=True)
        background(s).save(folder / "bg.png", optimize=True)
        for i, k in enumerate(BEAT):
            size = round(84 * s * k)
            logo = LOGO.copy()
            logo.thumbnail((size, size), Image.LANCZOS)
            logo.save(folder / f"logo_{i}.png", optimize=True)
    print("images écrites dans", OUT)


if __name__ == "__main__":
    main()
