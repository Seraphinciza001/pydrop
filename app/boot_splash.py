"""Fenêtre d'accueil animée de PyDrop, affichée dès le lancement pendant que le reste démarre.

Elle tourne dans son propre fil (Tk), la fenêtre principale (pywebview) gardant le fil principal.
    splash = BootSplash(images); splash.start(); splash.text("…"); splash.close()
"""
import math
import sys
import threading
import time
from pathlib import Path

W, H = 560, 360
CX, CY = W / 2, 150
BG = (7, 11, 22)
BLUE, ORANGE, MUTED, DIM = (56, 189, 248), (246, 139, 30), (139, 154, 179), (91, 106, 133)


def hexc(c):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(v))) for v in c)


def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def ease_out(t):
    return 1 - (1 - min(max(t, 0), 1)) ** 3


class BootSplash:
    def __init__(self, image_root: Path):
        self.image_root = image_root
        self._text = "Démarrage…"
        self._closing = False
        self._thread = None

    # -- appelé depuis le fil principal ------------------------------------------
    def start(self):
        self._thread = threading.Thread(target=self._run, name="pydrop-splash", daemon=True)
        self._thread.start()

    def text(self, value):
        self._text = value

    def close(self):
        self._closing = True

    # -- fil de la fenêtre ----------------------------------------------------------
    def _run(self):
        try:
            self._build()
            self.root.mainloop()
        except Exception as e:  # l'animation ne doit jamais empêcher PyDrop de démarrer
            print("Fenêtre d'accueil indisponible :", repr(e))
        finally:
            # Les objets Tk doivent disparaître dans ce fil-ci, sinon Tcl plante à la fermeture
            import gc
            for name in ("bg_img", "logos", "c", "root", "step_font"):
                self.__dict__.pop(name, None)
            gc.collect()

    def _scale(self):
        if not sys.platform.startswith("win"):
            return 1.0
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # même mode que la fenêtre pywebview
        except Exception:
            pass
        try:
            import ctypes
            return ctypes.windll.user32.GetDpiForSystem() / 96
        except Exception:
            return 1.0

    def _build(self):
        import tkinter as tk
        import tkinter.font as tkfont

        s = self._scale()
        folder_scale = min((1.0, 1.25, 1.5, 2.0), key=lambda v: abs(v - s))
        folder = self.image_root / f"s{int(folder_scale * 100)}"
        s = folder_scale  # tout est dessiné à l'échelle des images
        self.s = s
        root = self.root = tk.Tk()
        root.overrideredirect(True)
        root.configure(bg=hexc(BG))
        root.attributes("-alpha", 0.0)
        root.attributes("-topmost", True)
        w, h = round(W * s), round(H * s)
        x = (root.winfo_screenwidth() - w) // 2
        y = (root.winfo_screenheight() - h) // 2
        root.geometry(f"{w}x{h}+{x}+{y}")

        c = self.c = tk.Canvas(root, width=w, height=h, highlightthickness=0, bd=0, bg=hexc(BG))
        c.pack()
        self.bg_img = tk.PhotoImage(file=str(folder / "bg.png"))
        c.create_image(0, 0, image=self.bg_img, anchor="nw")

        P = lambda v: v * s
        # ondes qui partent du logo
        self.ripples = [c.create_oval(0, 0, 0, 0, outline=hexc(BG), width=max(1, round(P(2)))) for _ in range(3)]
        # anneaux qui tournent
        self.arc_outer = c.create_arc(P(CX - 96), P(CY - 96), P(CX + 96), P(CY + 96), style="arc",
                                      outline=hexc((37, 99, 160)), width=max(1, round(P(2))), extent=70)
        self.arc_blue = c.create_arc(P(CX - 80), P(CY - 80), P(CX + 80), P(CY + 80), style="arc",
                                     outline=hexc(BLUE), width=round(P(4)), extent=110)
        self.arc_orange = c.create_arc(P(CX - 80), P(CY - 80), P(CX + 80), P(CY + 80), style="arc",
                                       outline=hexc(ORANGE), width=round(P(4)), extent=45)
        # points en orbite, avec un halo
        self.dots = []
        for color, r in ((BLUE, 4), (ORANGE, 3)):
            halo = c.create_oval(0, 0, 0, 0, fill=hexc(mix(color, BG, .7)), outline="")
            dot = c.create_oval(0, 0, 0, 0, fill=hexc(color), outline="")
            self.dots.append((halo, dot, r))
        # logo qui bat
        self.logos = [tk.PhotoImage(file=str(p)) for p in sorted(folder.glob("logo_*.png"), key=lambda p: int(p.stem[5:]))]
        self.logo = c.create_image(P(CX), P(CY), image=self.logos[0])

        # titre lettre par lettre
        title_font = tkfont.Font(family="Segoe UI", size=-round(P(38)), weight="bold")
        letters = [(ch, BLUE) for ch in "Py"] + [(ch, ORANGE) for ch in "Drop"]
        total = sum(title_font.measure(ch) for ch, _ in letters)
        lx = P(CX) - total / 2
        self.letters = []
        for ch, color in letters:
            item = c.create_text(lx, P(268), text=ch, font=title_font, fill=hexc(BG), anchor="w")
            self.letters.append((item, lx, color))
            lx += title_font.measure(ch)

        self.step_font = tkfont.Font(family="Segoe UI", size=-round(P(13)))
        self.step = c.create_text(P(CX), P(300), text=self._text, font=self.step_font, fill=hexc(MUTED))
        self.shown_text = self._text

        # barre de chargement
        self.bar_x0, self.bar_x1, self.bar_y = P(CX - 95), P(CX + 95), P(320)
        c.create_line(self.bar_x0, self.bar_y, self.bar_x1, self.bar_y, fill=hexc((24, 34, 54)), width=round(P(4)), capstyle="round")
        self.bar = [c.create_line(0, 0, 0, 0, width=round(P(4)), capstyle="round", fill=hexc(col)) for col in (BLUE, ORANGE)]

        # signature
        sign_font = tkfont.Font(family="Segoe UI", size=-round(P(15)), weight="bold")
        by_font = tkfont.Font(family="Segoe UI", size=-round(P(14)))
        name = "Seraphin"
        width = by_font.measure("By ") + sign_font.measure(name)
        sx = P(CX) - width / 2
        c.create_text(sx, P(345), text="By ", font=by_font, fill=hexc(DIM), anchor="w")
        sx += by_font.measure("By ")
        for i, ch in enumerate(name):
            c.create_text(sx, P(345), text=ch, font=sign_font, fill=hexc(mix(BLUE, ORANGE, i / (len(name) - 1))), anchor="w")
            sx += sign_font.measure(ch)

        self.t0 = time.perf_counter()
        self.fade_from = None
        self._frame()

    def _frame(self):
        c, s = self.c, self.s
        P = lambda v: v * s
        t = time.perf_counter() - self.t0

        # apparition / disparition en fondu
        if self._closing and self.fade_from is None:
            self.fade_from = t
        if self.fade_from is not None:
            k = 1 - (t - self.fade_from) / .35
            if k <= 0:
                self.root.destroy()
                return
            self.root.attributes("-alpha", k)
        else:
            self.root.attributes("-alpha", min(1.0, t / .25))

        # ondes : elles grandissent et s'effacent
        for i, item in enumerate(self.ripples):
            p = ((t / 2.7) + i / 3) % 1
            r = P(64 + 50 * ease_out(p))  # elles s'arrêtent avant le titre
            color = BLUE if i != 1 else ORANGE
            c.coords(item, P(CX) - r, P(CY) - r, P(CX) + r, P(CY) + r)
            c.itemconfigure(item, outline=hexc(mix(color, (12, 26, 48), min(1, p * 1.15))))

        # anneaux qui tournent (l'orange suit le bleu)
        a = (t * 280) % 360
        c.itemconfigure(self.arc_blue, start=-a, extent=95 + 35 * math.sin(t * 2.2))
        c.itemconfigure(self.arc_orange, start=-a - 150)
        c.itemconfigure(self.arc_outer, start=(t * 110) % 360)

        # points en orbite
        for (halo, dot, r), (radius, speed) in zip(self.dots, ((106, 1 / 3.6), (124, -1 / 5.4))):
            ang = t * speed * 2 * math.pi - math.pi / 2
            x, y = P(CX) + P(radius) * math.cos(ang), P(CY) + P(radius) * math.sin(ang)
            hr, dr = P(r * 2.6), P(r)
            c.coords(halo, x - hr, y - hr, x + hr, y + hr)
            c.coords(dot, x - dr, y - dr, x + dr, y + dr)

        # battement du logo (cycle de 1,8 s)
        c.itemconfigure(self.logo, image=self.logos[int((t % 1.8) / 1.8 * len(self.logos)) % len(self.logos)])

        # titre : chaque lettre monte et s'allume, l'une après l'autre
        for i, (item, x, color) in enumerate(self.letters):
            k = ease_out((t - .15 - i * .07) / .55)
            c.coords(item, x, P(268) + P(16) * (1 - k))
            c.itemconfigure(item, fill=hexc(mix(BG, color, k)))

        # texte d'étape
        if self._text != self.shown_text:
            self.shown_text = self._text
            c.itemconfigure(self.step, text=self._text)

        # barre : un trait bleu-orange qui glisse
        span = self.bar_x1 - self.bar_x0
        head = self.bar_x0 + ((t / 1.25) % 1) * (span + P(80)) - P(40)
        for item, (off, length) in zip(self.bar, ((-P(40), P(40)), (0, P(28)))):
            x0 = max(self.bar_x0, head + off - length / 2)
            x1 = min(self.bar_x1, head + off + length / 2)
            c.coords(item, x0, self.bar_y, max(x0, x1), self.bar_y)

        self.visible = (self.root.winfo_rootx(), self.root.winfo_rooty(), self.root.winfo_width(),
                        self.root.winfo_height(), self.root.winfo_viewable())
        self.root.after(15, self._frame)
