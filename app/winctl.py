"""
Outils Windows de PyDrop, sans dépendance externe (ctypes) :

  * presse-papiers (lire / écrire du texte) ;
  * télécommande : souris, molette, touches, saisie de texte (SendInput) ;
  * notifications Windows (toasts) pour les notifications du téléphone.
"""

import base64
import ctypes
import os
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path
from xml.sax.saxutils import escape

IS_WIN = sys.platform == "win32"
APP_ID = "Seraphin.PyDrop"

# ---------------------------------------------------------------- presse-papiers

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

if IS_WIN:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL


def _open_clipboard():
    # Une autre application peut l'avoir ouvert un instant : on réessaie
    for _ in range(20):
        if user32.OpenClipboard(None):
            return True
        time.sleep(0.02)
    return False


def clipboard_seq() -> int:
    return int(user32.GetClipboardSequenceNumber()) if IS_WIN else 0


def get_clipboard() -> str:
    if not IS_WIN or not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
        return ""
    if not _open_clipboard():
        return ""
    try:
        h = user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ""
        p = kernel32.GlobalLock(h)
        if not p:
            return ""
        try:
            return ctypes.wstring_at(p)
        finally:
            kernel32.GlobalUnlock(h)
    finally:
        user32.CloseClipboard()


def set_clipboard(text: str) -> bool:
    if not IS_WIN:
        return False
    data = ctypes.create_unicode_buffer(text)
    size = ctypes.sizeof(data)
    if not _open_clipboard():
        return False
    try:
        user32.EmptyClipboard()
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not h:
            return False
        p = kernel32.GlobalLock(h)
        ctypes.memmove(p, data, size)
        kernel32.GlobalUnlock(h)
        if not user32.SetClipboardData(CF_UNICODETEXT, h):
            kernel32.GlobalFree(h)
            return False
        return True  # Windows possède maintenant la mémoire
    finally:
        user32.CloseClipboard()


# ---------------------------------------------------------------- souris et clavier

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_WHEEL, MOUSEEVENTF_HWHEEL = 0x0800, 0x1000
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0001, 0x0002, 0x0004

ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


if IS_WIN:
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT

# Touches nommées (codes virtuels Windows) ; True = touche « étendue »
KEYS = {
    "vol_up": (0xAF, False), "vol_down": (0xAE, False), "mute": (0xAD, False),
    "play": (0xB3, False), "next": (0xB0, False), "prev": (0xB1, False),
    "left": (0x25, True), "up": (0x26, True), "right": (0x27, True), "down": (0x28, True),
    "pgup": (0x21, True), "pgdn": (0x22, True), "home": (0x24, True), "end": (0x23, True),
    "enter": (0x0D, False), "esc": (0x1B, False), "back": (0x08, False), "tab": (0x09, False),
    "space": (0x20, False), "del": (0x2E, True), "f5": (0x74, False), "f11": (0x7A, False),
    "win": (0x5B, True), "alt": (0x12, False), "ctrl": (0x11, False), "shift": (0x10, False),
    "d": (0x44, False), "b": (0x42, False),
}
# Raccourcis : une suite de touches maintenues ensemble
COMBOS = {
    "desktop": ["win", "d"],             # afficher le bureau
    "alttab": ["alt", "tab"],            # application précédente
    "slideshow_here": ["shift", "f5"],   # diaporama depuis la diapositive actuelle
    "black": ["b"],                      # écran noir pendant une présentation
}


def _send(inputs):
    if not IS_WIN or not inputs:
        return
    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def _mouse(flags, dx=0, dy=0, data=0):
    i = INPUT(type=INPUT_MOUSE)
    i.u.mi = MOUSEINPUT(int(dx), int(dy), ctypes.c_uint32(int(data)).value, flags, 0, 0)
    return i


def _key(vk, up=False, extended=False):
    i = INPUT(type=INPUT_KEYBOARD)
    flags = (KEYEVENTF_KEYUP if up else 0) | (KEYEVENTF_EXTENDEDKEY if extended else 0)
    i.u.ki = KEYBDINPUT(vk, 0, flags, 0, 0)
    return i


def _unicode(ch, up=False):
    i = INPUT(type=INPUT_KEYBOARD)
    i.u.ki = KEYBDINPUT(0, ord(ch), KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0), 0, 0)
    return i


def mouse_move(dx, dy):
    dx, dy = max(-400, min(400, int(dx))), max(-400, min(400, int(dy)))
    if dx or dy:
        _send([_mouse(MOUSEEVENTF_MOVE, dx, dy)])


def mouse_button(button="left", action="click", count=1):
    down, up = ((MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP) if button == "right"
                else (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP))
    if action == "down":
        _send([_mouse(down)])
    elif action == "up":
        _send([_mouse(up)])
    else:
        _send([_mouse(f) for _ in range(max(1, min(3, int(count)))) for f in (down, up)])


def mouse_scroll(dy=0, dx=0):
    events = []
    if dy:
        events.append(_mouse(MOUSEEVENTF_WHEEL, data=max(-1200, min(1200, int(dy)))))
    if dx:
        events.append(_mouse(MOUSEEVENTF_HWHEEL, data=max(-1200, min(1200, int(dx)))))
    _send(events)


def press(name) -> bool:
    names = COMBOS.get(name) or ([name] if name in KEYS else None)
    if not names:
        return False
    keys = [KEYS[n] for n in names]
    _send([_key(vk, False, ext) for vk, ext in keys] + [_key(vk, True, ext) for vk, ext in reversed(keys)])
    return True


def type_text(text: str):
    events = []
    for ch in text[:2000]:
        if ch == "\n":
            vk, ext = KEYS["enter"]
            events += [_key(vk, False, ext), _key(vk, True, ext)]
        elif ch == "\r":
            continue
        elif ord(ch) > 0xFFFF:  # émoji : deux unités UTF-16
            b = ch.encode("utf-16-le")
            for k in range(0, 4, 2):
                unit = chr(int.from_bytes(b[k:k + 2], "little"))
                events += [_unicode(unit), _unicode(unit, True)]
        else:
            events += [_unicode(ch), _unicode(ch, True)]
    _send(events)


# ---------------------------------------------------------------- notifications Windows

def set_app_id():
    """Rattache les fenêtres et notifications à l'identité « PyDrop » (raccourci du menu Démarrer)."""
    if IS_WIN:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass


def _toast_app_id():
    # L'installateur crée un raccourci « PyDrop » portant cet identifiant : Windows affiche alors
    # « PyDrop » et son icône. Sans lui (version de développement), on passe par PowerShell.
    start = Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/PyDrop.lnk"
    common = Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs/PyDrop.lnk"
    if getattr(sys, "frozen", False) and (start.exists() or common.exists()):
        return APP_ID
    return r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"


_icons_dir = Path(tempfile.gettempdir()) / "pydrop-notif-icons"


def save_icon(key: str, png_b64: str) -> str:
    """Enregistre l'icône de l'application du téléphone ; renvoie son chemin (ou « »)."""
    if not png_b64:
        return ""
    try:
        _icons_dir.mkdir(exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in key)[:80] or "app"
        path = _icons_dir / f"{safe}.png"
        if not path.exists():
            path.write_bytes(base64.b64decode(png_b64))
        return str(path)
    except Exception:
        return ""


def show_toast(app: str, title: str, text: str, icon_path: str = ""):
    """Notification Windows. Sans attente : PowerShell s'en occupe en arrière-plan."""
    if not IS_WIN:
        return
    image = (f'<image placement="appLogoOverride" hint-crop="circle" src="{escape(Path(icon_path).as_uri())}"/>'
             if icon_path else "")
    lines = [t for t in (title, text) if t]
    body = "".join(f"<text>{escape(t[:400])}</text>" for t in lines[:2])
    xml = (f'<toast><visual><binding template="ToastGeneric">{body}{image}'
           f'<text placement="attribution">{escape(app[:60])} · via PyDrop</text>'
           f'</binding></visual><audio src="ms-winsoundevent:Notification.IM"/></toast>')
    ps_xml = xml.replace("'", "''")
    app_id = _toast_app_id().replace("'", "''")
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null;"
        "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] | Out-Null;"
        "$x = New-Object Windows.Data.Xml.Dom.XmlDocument;"
        f"$x.LoadXml('{ps_xml}');"
        f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{app_id}').Show("
        "[Windows.UI.Notifications.ToastNotification]::new($x))"
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode()
    try:
        subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                          "-WindowStyle", "Hidden", "-EncodedCommand", encoded],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as e:
        print("notification Windows :", e)
