"""
PyDrop — partage de fichiers sur le réseau local.

  * Découverte automatique des ordinateurs (broadcast UDP)
  * Les téléphones se connectent depuis leur navigateur (page mob/index.html)
  * Toute connexion doit être acceptée par l'autre appareil
  * Transferts directs ordinateur -> ordinateur, ordinateur <-> téléphone

Lancement :  python app/pydrop.py            (fenêtre desktop)
             python app/pydrop.py --browser  (ouvre l'interface dans le navigateur)
"""

import argparse
import asyncio
import errno
import faulthandler
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
import zipfile
from pathlib import Path
from urllib.parse import quote

from aiohttp import ClientError, ClientSession, ClientTimeout, WSMsgType, web

try:
    import winctl  # presse-papiers, télécommande, notifications Windows
except Exception:  # autre système que Windows
    winctl = None

APP = "pydrop"
VERSION = 2
DISCOVERY_PORT = 47474
DEFAULT_PORT = 8765
ANNOUNCE_EVERY = 2.0
PEER_TIMEOUT = 9.0
REQUEST_TIMEOUT = 60.0


def resource_dir() -> Path:
    # Compatible PyInstaller (sys._MEIPASS) et exécution depuis les sources
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


ROOT = resource_dir()
UI_DIR = ROOT / "app" / "ui"
MOB_DIR = ROOT / "mob"


# ----------------------------------------------------------------------------
# Utilitaires
# ----------------------------------------------------------------------------

def windows_active_ips():
    """Détecte les adresses IPv4 uniquement sur les cartes réseau physiquement connectées (Status Up)."""
    try:
        import ctypes, socket, struct
        from ctypes import wintypes

        class SOCKET_ADDRESS(ctypes.Structure):
            _fields_ = [('lpSockaddr', ctypes.c_void_p), ('iSockaddrLength', ctypes.c_int)]

        class IP_ADAPTER_UNICAST_ADDRESS(ctypes.Structure):
            pass
        IP_ADAPTER_UNICAST_ADDRESS._fields_ = [
            ('Length', wintypes.ULONG), ('Flags', wintypes.DWORD),
            ('Next', ctypes.POINTER(IP_ADAPTER_UNICAST_ADDRESS)),
            ('Address', SOCKET_ADDRESS)
        ]

        class IP_ADAPTER_ADDRESSES(ctypes.Structure):
            pass
        IP_ADAPTER_ADDRESSES._fields_ = [
            ('Length', wintypes.ULONG), ('IfIndex', wintypes.DWORD),
            ('Next', ctypes.POINTER(IP_ADAPTER_ADDRESSES)),
            ('AdapterName', ctypes.c_char_p),
            ('FirstUnicastAddress', ctypes.POINTER(IP_ADAPTER_UNICAST_ADDRESS)),
            ('FirstAnycastAddress', ctypes.c_void_p),
            ('FirstMulticastAddress', ctypes.c_void_p),
            ('FirstDnsServerAddress', ctypes.c_void_p),
            ('DnsSuffix', wintypes.LPWSTR),
            ('Description', wintypes.LPWSTR),
            ('FriendlyName', wintypes.LPWSTR),
            ('PhysicalAddress', ctypes.c_ubyte * 8),
            ('PhysicalAddressLength', wintypes.DWORD),
            ('Flags', wintypes.DWORD),
            ('Mtu', wintypes.DWORD),
            ('IfType', wintypes.DWORD),
            ('OperStatus', wintypes.DWORD)
        ]

        GetAdaptersAddresses = ctypes.windll.iphlpapi.GetAdaptersAddresses
        size = wintypes.ULONG(16384)
        buf = ctypes.create_string_buffer(size.value)
        flags = 0x0E
        ret = GetAdaptersAddresses(socket.AF_INET, flags, None, ctypes.cast(buf, ctypes.POINTER(IP_ADAPTER_ADDRESSES)), ctypes.byref(size))
        if ret == 111:  # ERROR_BUFFER_OVERFLOW
            buf = ctypes.create_string_buffer(size.value)
            ret = GetAdaptersAddresses(socket.AF_INET, flags, None, ctypes.cast(buf, ctypes.POINTER(IP_ADAPTER_ADDRESSES)), ctypes.byref(size))
        if ret != 0:
            return None
        ips = []
        curr = ctypes.cast(buf, ctypes.POINTER(IP_ADAPTER_ADDRESSES))
        while curr:
            a = curr.contents
            # OperStatus == 1 : IfOperStatusUp (carte active et média connecté)
            # IfType != 24 : exclure le loopback
            if a.OperStatus == 1 and a.IfType != 24:
                u = a.FirstUnicastAddress
                while u:
                    sa = u.contents.Address.lpSockaddr
                    raw = ctypes.string_at(sa, 8)
                    family = struct.unpack('H', raw[:2])[0]
                    if family == socket.AF_INET:
                        ip_str = socket.inet_ntoa(raw[4:8])
                        if not (ip_str.startswith('127.') or ip_str.startswith('169.254.')):
                            ips.append(ip_str)
                    u = u.contents.Next
            curr = a.Next
        return ips
    except Exception:
        return None


def local_ips():
    if sys.platform.startswith("win"):
        w_ips = windows_active_ips()
        if w_ips is not None:
            seen, out = set(), []
            for ip in w_ips:
                if ip not in seen:
                    seen.add(ip)
                    out.append(ip)
            return out
    ips = []
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ips.append(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    seen, out = set(), []
    for ip in ips:
        if ip in seen or ip.startswith("127.") or ip.startswith("169.254."):
            continue
        seen.add(ip)
        out.append(ip)
    return out


def safe_name(name: str) -> str:
    name = os.path.basename(name.replace("\\", "/")).strip()
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(". ")
    return name[:200] or "fichier"


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    i = 1
    while True:
        candidate = path.with_name(f"{stem} ({i}){suffix}")
        if not candidate.exists():
            return candidate
        i += 1


def open_path(path: Path, select: bool = False):
    try:
        if sys.platform.startswith("win"):
            if select:
                subprocess.Popen(["explorer", "/select,", str(path)])
            else:
                os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)] if select else ["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path.parent if select else path)])
    except Exception as e:
        print("open_path:", e)


# Déjà compressés : les recompresser ferait perdre du temps pour rien
STORED_EXT = {".zip", ".rar", ".7z", ".gz", ".mp4", ".mkv", ".mov", ".avi", ".webm", ".mp3", ".m4a", ".aac",
              ".ogg", ".flac", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".apk", ".docx", ".xlsx", ".pptx"}


class JobCancelled(Exception):
    pass


class SendRefused(Exception):
    """Erreur définitive : réessayer ne servirait à rien (ex. disque plein en face)."""


# Marge gardée libre : un disque rempli à ras bord peut bloquer tout l'ordinateur
DISK_MARGIN = 200 * 1024 * 1024


def has_room(folder, needed) -> bool:
    try:
        return shutil.disk_usage(folder).free >= needed + DISK_MARGIN
    except OSError:
        return True


def is_disk_full(e) -> bool:
    return isinstance(e, OSError) and e.errno == errno.ENOSPC


def zip_folder(src: Path, dest: Path, progress, cancelled):
    """Compresse un dossier. Retourne le nombre de fichiers illisibles ignorés."""
    total = 0
    for root, _, files in os.walk(src):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    done = skipped = 0
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, allowZip64=True, strict_timestamps=False) as z:
        for root, dirs, files in os.walk(src):
            rel = os.path.relpath(root, src).replace(os.sep, "/")
            rel = "" if rel == "." else rel + "/"
            if rel and not dirs and not files:
                z.writestr(rel, b"")  # dossier vide
            for name in files:
                if cancelled():
                    raise JobCancelled()
                full = os.path.join(root, name)
                if os.path.islink(full):
                    continue
                try:
                    source = open(full, "rb")
                except OSError:
                    skipped += 1
                    continue
                with source:
                    info = zipfile.ZipInfo.from_file(full, rel + name, strict_timestamps=False)
                    stored = os.path.splitext(name)[1].lower() in STORED_EXT
                    info.compress_type = zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED
                    with z.open(info, "w") as out:
                        while chunk := source.read(1 << 20):
                            if cancelled():
                                raise JobCancelled()
                            out.write(chunk)
                            done += len(chunk)
                            progress(done, total)
    return skipped


def folder_size(src) -> int:
    total = 0
    for root, _, files in os.walk(src):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def file_sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def friendly_video_error(message: str, cookies: str = "") -> str:
    m = message.lower()
    if "not a bot" in m:
        if cookies:
            return (f"YouTube bloque ce réseau même avec la connexion de {cookies.capitalize()}. "
                    "Vérifiez que vous y êtes connecté à YouTube, ou réessayez plus tard.")
        return ("YouTube bloque temporairement ce réseau (vérification anti-robot). Sur le PC, activez "
                "« Connexion YouTube du navigateur », ou réessayez plus tard.")
    if "cookie" in m and ("could not" in m or "failed" in m or "decrypt" in m or "permission" in m):
        return (f"Impossible de lire la connexion YouTube de {cookies.capitalize() or 'ce navigateur'} : "
                "fermez-le complètement, ou choisissez Firefox.")
    if "private" in m or "sign in" in m or "login" in m:
        return "Vidéo privée ou réservée aux comptes connectés"
    if "unavailable" in m or "removed" in m or "not available" in m:
        return "Vidéo indisponible"
    if "unsupported url" in m:
        return "Ce site n'est pas pris en charge"
    if "age" in m and "confirm" in m:
        return "Vidéo soumise à une vérification d'âge"
    if "network" in m or "timed out" in m or "getaddrinfo" in m or "connection" in m:
        return "Pas d'accès à Internet depuis le PC"
    return "Téléchargement impossible : " + (message.replace("ERROR:", "").strip()[:160] or "erreur inconnue")


def describe_path(path) -> dict | None:
    p = Path(str(path))
    try:
        if p.is_dir():
            return {"path": str(p), "name": p.name or str(p), "is_dir": True, "size": 0}
        if p.is_file():
            return {"path": str(p), "name": p.name, "is_dir": False, "size": p.stat().st_size}
    except OSError:
        pass
    return None


# -- Menu Windows « Envoyer avec PyDrop » ------------------------------------
#
# Le menu lance PyDropSend.exe, un tout petit programme qui transmet le chemin à PyDrop
# (et le démarre au besoin). L'exe principal, plus lourd, mettrait plusieurs secondes.

SHELL_KEYS = (r"Software\Classes\*\shell\PyDrop", r"Software\Classes\Directory\shell\PyDrop")


def shell_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "PyDrop"


def sendto_link() -> Path:
    return Path(os.environ.get("APPDATA") or Path.home()) / "Microsoft" / "Windows" / "SendTo" / "PyDrop.lnk"


def shell_up_to_date(exe: str) -> bool:
    import winreg
    folder = shell_dir()
    try:
        if (folder / "main.txt").read_text("utf-8") != exe or not sendto_link().exists():
            return False
        if (folder / "PyDropSend.exe").stat().st_size != (ROOT / "app" / "shell" / "PyDropSend.exe").stat().st_size:
            return False
        for key in SHELL_KEYS:
            winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, key + r"\command"))
        return True
    except OSError:
        return False


def install_shell(exe: str):
    import winreg
    if shell_up_to_date(exe):
        return
    folder = shell_dir()
    folder.mkdir(parents=True, exist_ok=True)
    forwarder = folder / "PyDropSend.exe"
    try:
        shutil.copyfile(ROOT / "app" / "shell" / "PyDropSend.exe", forwarder)
    except OSError:
        if not forwarder.exists():
            raise
    (folder / "main.txt").write_text(exe, "utf-8")
    for key in SHELL_KEYS:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "Envoyer avec PyDrop")
            winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, exe)
            winreg.SetValueEx(k, "MultiSelectModel", 0, winreg.REG_SZ, "Player")
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key + r"\command", 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, f'"{forwarder}" "%1"')
    # Entrée « Envoyer vers > PyDrop »
    quoted = lambda v: "'" + str(v).replace("'", "''") + "'"
    script = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut({quoted(sendto_link())});"
              f"$s.TargetPath={quoted(forwarder)};$s.IconLocation={quoted(exe)};"
              "$s.Description='Envoyer avec PyDrop';$s.Save()")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=30, check=True)


def uninstall_shell():
    import winreg
    for key in SHELL_KEYS:
        for sub in (key + r"\command", key):
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
            except OSError:
                pass
    sendto_link().unlink(missing_ok=True)
    (shell_dir() / "port.txt").unlink(missing_ok=True)


def os_label():
    s = platform.system()
    return {"Windows": "Windows", "Darwin": "macOS", "Linux": "Linux"}.get(s, s)


# ----------------------------------------------------------------------------
# Configuration persistante
# ----------------------------------------------------------------------------

class Config:
    def __init__(self, profile: str | None):
        base = Path.home() / ".pydrop"
        if profile:
            base = base / profile
        base.mkdir(parents=True, exist_ok=True)
        self.path = base / "config.json"
        self.history_path = base / "history.json"
        data = {}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text("utf-8"))
            except Exception:
                data = {}
        self.id = data.get("id") or uuid.uuid4().hex
        self.name = data.get("name") or socket.gethostname()
        default_dir = Path.home() / "Downloads" / "PyDrop"
        self.download_dir = Path(data.get("download_dir") or default_dir)
        self.allow_browse = bool(data.get("allow_browse", True))
        self.shell_integration = bool(data.get("shell_integration", True))
        self.video_cookies = data.get("video_cookies") or ""   # navigateur dont on lit la connexion YouTube
        self.mirror_audio = data.get("mirror_audio") or "phone"  # son de l'écran partagé : phone / pc / both
        self.clip_auto = bool(data.get("clip_auto", False))      # presse-papiers envoyé tout seul aux appareils
        self.allow_remote = bool(data.get("allow_remote", True))  # télécommande depuis un téléphone connecté
        self.notif_toast = bool(data.get("notif_toast", True))    # notifications du téléphone en pop-up Windows
        self.notif_muted = list(data.get("notif_muted") or [])    # applications du téléphone masquées
        self.save()

    def save(self):
        self.path.write_text(json.dumps({
            "id": self.id,
            "name": self.name,
            "download_dir": str(self.download_dir),
            "allow_browse": self.allow_browse,
            "shell_integration": self.shell_integration,
            "video_cookies": self.video_cookies,
            "mirror_audio": self.mirror_audio,
            "clip_auto": self.clip_auto,
            "allow_remote": self.allow_remote,
            "notif_toast": self.notif_toast,
            "notif_muted": self.notif_muted,
        }, indent=2), "utf-8")

    def load_history(self):
        try:
            return json.loads(self.history_path.read_text("utf-8"))
        except Exception:
            return []

    def save_history(self, items):
        try:
            self.history_path.write_text(json.dumps(items[:100], ensure_ascii=False), "utf-8")
        except Exception:
            pass


# ----------------------------------------------------------------------------
# Découverte UDP
# ----------------------------------------------------------------------------

class Discovery(asyncio.DatagramProtocol):
    def __init__(self, node: "Node"):
        self.node = node
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        try:
            msg = json.loads(data.decode("utf-8"))
        except Exception:
            return
        if msg.get("app") != APP or msg.get("id") == self.node.cfg.id:
            return
        self.node.on_announce(msg, addr[0])

    def announce(self, bye=False, target=None):
        if not self.transport:
            return
        payload = json.dumps({**self.node.public_info(), "app": APP, "bye": bye}).encode()
        targets = [target] if target else self.node.broadcast_targets()
        for t in targets:
            try:
                self.transport.sendto(payload, (t, DISCOVERY_PORT))
            except OSError:
                pass


def make_discovery_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("", DISCOVERY_PORT))
    sock.setblocking(False)
    return sock


# ----------------------------------------------------------------------------
# Noeud PyDrop : serveur HTTP + WebSocket
# ----------------------------------------------------------------------------

@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        resp = web.Response()
    elif request.path.startswith("/api/"):
        # Les erreurs des API doivent aussi porter les en-têtes CORS pour être lisibles
        try:
            resp = await handler(request)
        except web.HTTPException as e:
            resp = web.Response(status=e.status, text=e.text or e.reason)
    else:
        resp = await handler(request)
    if request.path.startswith("/api/"):
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "*"
        resp.headers["Access-Control-Allow-Private-Network"] = "true"
    return resp


def is_local(request) -> bool:
    return request.remote in ("127.0.0.1", "::1", "localhost")


def is_local_ui(request) -> bool:
    """Vient de cet ordinateur ET de l'interface PyDrop (pas d'un site web ouvert dans un navigateur)."""
    if not is_local(request):
        return False
    origin = request.headers.get("Origin")
    return not origin or origin in (f"http://127.0.0.1:{request.url.port}", f"http://localhost:{request.url.port}")


# -- Téléchargement de vidéos par lien (yt-dlp) ---------------------------------
#
# yt-dlp et ffmpeg sont téléchargés une seule fois depuis leurs pages officielles, vérifiés
# par leur empreinte publiée, puis yt-dlp se met à jour tout seul une fois par jour.

YTDLP_BASE = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/"
FFMPEG_BASE = "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/"
FFMPEG_ZIP = "ffmpeg-master-latest-win64-gpl-shared.zip"
SCRCPY_API = "https://api.github.com/repos/Genymobile/scrcpy/releases/latest"
DENO_BASE = "https://github.com/denoland/deno/releases/latest/download/"
DENO_ZIP = "deno-x86_64-pc-windows-msvc.zip"
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)


class VideoTools:
    def __init__(self, node):
        self.node = node
        self.lock = asyncio.Lock()

    @property
    def folder(self) -> Path:
        return shell_dir() / "tools"

    async def _download(self, url, dest: Path, progress):
        timeout = ClientTimeout(total=None, sock_connect=15, sock_read=60)
        async with self.node.http.get(url, timeout=timeout) as r:
            if r.status != 200:
                raise ConnectionError(f"téléchargement impossible ({r.status})")
            total = r.content_length or 0
            done, last = 0, 0.0
            f = await self.node.loop.run_in_executor(None, open, dest, "wb")
            try:
                async for chunk in r.content.iter_chunked(1 << 20):
                    await self.node.loop.run_in_executor(None, f.write, chunk)
                    done += len(chunk)
                    if time.monotonic() - last > 0.3:
                        last = time.monotonic()
                        progress(done, total)
            finally:
                await self.node.loop.run_in_executor(None, f.close)

    async def _expected_sha(self, sums_url, name):
        async with self.node.http.get(sums_url, timeout=ClientTimeout(total=30)) as r:
            text = await r.text()
        for line in text.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == name:
                return parts[0].lower()
        raise ConnectionError(f"empreinte officielle de {name} introuvable")

    async def _fetch_verified(self, base, sums, name, dest: Path, label, progress):
        expected = await self._expected_sha(base + sums, name)
        tmp = dest.with_suffix(dest.suffix + ".part")
        await self._download(base + name, tmp, lambda d, t: progress(f"{label}… {d * 100 // t if t else 0} %", d, t))
        progress("Vérification du fichier téléchargé…", 0, 0)
        if await self.node.loop.run_in_executor(None, file_sha256, tmp) != expected:
            tmp.unlink(missing_ok=True)
            raise ConnectionError(f"{label} : fichier téléchargé corrompu, réessayez")
        os.replace(tmp, dest)

    async def ytdlp(self, progress) -> str:
        async with self.lock:
            self.folder.mkdir(parents=True, exist_ok=True)
            exe = self.folder / "yt-dlp.exe"
            stamp = self.folder / "yt-dlp.checked"
            if not exe.exists():
                await self._fetch_verified(YTDLP_BASE, "SHA2-256SUMS", "yt-dlp.exe", exe,
                                           "Installation du téléchargeur (première fois)", progress)
                stamp.write_text(str(time.time()))
            elif time.time() - float(stamp.read_text() if stamp.exists() else 0) > 24 * 3600:
                # YouTube change souvent : yt-dlp se met à jour lui-même (une fois par jour)
                progress("Mise à jour du téléchargeur…", 0, 0)
                try:
                    p = await asyncio.create_subprocess_exec(
                        str(exe), "-U", stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                    await asyncio.wait_for(p.wait(), 120)
                except Exception as e:
                    print("Mise à jour de yt-dlp impossible :", e)
                stamp.write_text(str(time.time()))
            return str(exe)

    async def js_runtime(self, progress) -> str:
        """YouTube exige désormais un moteur JavaScript : node s'il est installé, sinon deno (40 Mo)."""
        node = shutil.which("node")
        if node:
            return f"node:{node}"
        async with self.lock:
            exe = self.folder / "deno.exe"
            if not exe.exists():
                self.folder.mkdir(parents=True, exist_ok=True)
                archive = self.folder / DENO_ZIP
                async with self.node.http.get(DENO_BASE + DENO_ZIP + ".sha256sum", timeout=ClientTimeout(total=30)) as r:
                    found = re.search(r"\b([0-9a-fA-F]{64})\b", await r.text())
                if not found:
                    raise ConnectionError("empreinte officielle de deno introuvable")
                tmp = archive.with_suffix(".part")
                await self._download(DENO_BASE + DENO_ZIP, tmp, lambda d, t: progress(
                    f"Installation du moteur JavaScript (première fois, 40 Mo)… {d * 100 // t if t else 0} %", d, t))
                progress("Vérification du fichier téléchargé…", 0, 0)
                if await self.node.loop.run_in_executor(None, file_sha256, tmp) != found.group(1).lower():
                    tmp.unlink(missing_ok=True)
                    raise ConnectionError("moteur JavaScript : fichier téléchargé corrompu, réessayez")

                def extract():
                    with zipfile.ZipFile(tmp) as z, z.open("deno.exe") as src, open(exe, "wb") as out:
                        shutil.copyfileobj(src, out)
                    tmp.unlink()

                await self.node.loop.run_in_executor(None, extract)
            return f"deno:{exe}"

    async def scrcpy(self, progress) -> Path:
        """scrcpy (affichage et contrôle du téléphone) et son adb, installés une seule fois."""
        async with self.lock:
            target = self.folder / "scrcpy"
            if (target / "scrcpy.exe").exists() and (target / "adb.exe").exists():
                return target
            self.folder.mkdir(parents=True, exist_ok=True)
            async with self.node.http.get(SCRCPY_API, timeout=ClientTimeout(total=30),
                                          headers={"Accept": "application/vnd.github+json"}) as r:
                release = await r.json()
            asset = next((a for a in release.get("assets", []) if re.fullmatch(r"scrcpy-win64-v[\d.]+\.zip", a["name"])), None)
            digest = (asset or {}).get("digest") or ""
            if not asset or not digest.startswith("sha256:"):
                raise ConnectionError("version officielle de scrcpy introuvable")
            tmp = self.folder / "scrcpy.zip.part"
            await self._download(asset["browser_download_url"], tmp, lambda d, t: progress(
                f"Installation de l'affichage du téléphone (première fois, 11 Mo)… {d * 100 // t if t else 0} %", d, t))
            progress("Vérification du fichier téléchargé…", 0, 0)
            if await self.node.loop.run_in_executor(None, file_sha256, tmp) != digest[7:].lower():
                tmp.unlink(missing_ok=True)
                raise ConnectionError("scrcpy : fichier téléchargé corrompu, réessayez")

            def extract():
                shutil.rmtree(target, ignore_errors=True)
                target.mkdir(parents=True)
                with zipfile.ZipFile(tmp) as z:
                    for info in z.infolist():
                        parts = info.filename.split("/", 1)  # le zip contient un dossier « scrcpy-win64-vX »
                        if len(parts) == 2 and parts[1] and not info.is_dir():
                            dest = target / parts[1]
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            with z.open(info) as src, open(dest, "wb") as out:
                                shutil.copyfileobj(src, out)
                tmp.unlink()

            await self.node.loop.run_in_executor(None, extract)
            return target

    async def ffmpeg(self, progress) -> str:
        """Dossier contenant ffmpeg.exe (nécessaire pour la HD : image et son arrivent séparés)."""
        found = shutil.which("ffmpeg")
        if found:
            return str(Path(found).parent)
        async with self.lock:
            target = self.folder / "ffmpeg"
            if (target / "ffmpeg.exe").exists():
                return str(target)
            self.folder.mkdir(parents=True, exist_ok=True)
            archive = self.folder / FFMPEG_ZIP
            await self._fetch_verified(FFMPEG_BASE, "checksums.sha256", FFMPEG_ZIP, archive,
                                       "Installation de ffmpeg pour la HD (première fois, 90 Mo)", progress)
            progress("Installation de ffmpeg…", 0, 0)

            def extract():
                target.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(archive) as z:
                    for info in z.infolist():
                        parts = info.filename.split("/")
                        if len(parts) >= 3 and parts[-2] == "bin" and parts[-1]:
                            with z.open(info) as src, open(target / parts[-1], "wb") as out:
                                shutil.copyfileobj(src, out)
                archive.unlink()

            await self.node.loop.run_in_executor(None, extract)
            return str(target)


class Node:
    def __init__(self, cfg: Config, port: int, profile=None):
        self.cfg = cfg
        self.profile = profile
        self.port = port
        self.loop: asyncio.AbstractEventLoop | None = None
        self.window = None
        self.discovery: Discovery | None = None
        self.http: ClientSession | None = None

        self.peers = {}        # ordinateurs : id -> {id,name,type,os,ip,port,last_seen,static}
        self.clients = {}      # téléphones  : id -> {"info": {...}, "ws": ws}
        self.sessions = {}     # id appareil -> jeton de session partagé
        self.pending_out = {}  # id appareil -> req_id (demandes envoyées)
        self.pending_in = {}   # req_id -> {"from": info, "ts": t}
        self.staged = {}       # fichiers préparés pour un téléphone
        self.rx_tasks = {}     # tid -> tâche qui reçoit ce fichier
        self.rx_cancelled = set()
        self.dl_tasks = {}     # id de téléchargement -> tâche qui l'envoie
        self.browse_cancelled = set()  # téléchargements de l'explorateur annulés par le PC
        self.browse_owner = {}         # id de téléchargement -> appareil qui le prend
        self.out_jobs = {}     # tid -> envoi fait par ce PC depuis un chemin sur le disque
        self.out_queues = {}   # id appareil -> [tid…] (un envoi à la fois par appareil)
        self.out_running = set()
        self.sha_cache = {}
        self.tools = VideoTools(self)
        self.fetch_jobs = {}   # tid -> téléchargement de vidéo en cours pour un appareil
        self.mirrors = {}      # id du téléphone -> fenêtre scrcpy ouverte
        self.mirror_opts = {}  # id du téléphone -> {"mode": screen/front/back, "record": bool}
        self.notifs = []       # dernières notifications reçues des téléphones
        self.dev_commands = {} # id du téléphone -> asyncio.Queue() pour les commandes (réponses, etc.)
        self.notif_seen = {}   # empreinte -> heure (évite les doublons)
        self.last_urls = None  # suivi dynamique des adresses IP / réseau local
        self.dev_names = {}    # id -> dernier nom connu (le téléphone peut écrire sans être en ligne)
        self.clips = []        # derniers textes reçus ou envoyés (presse-papiers)
        self.clip_seq = 0      # dernier état connu du presse-papiers Windows
        self.remote_seen = {}  # id du téléphone -> dernière commande de télécommande
        self.mirror_busy = set()
        self.temp_files = set()  # fichiers créés par PyDrop, à supprimer après envoi
        self.pending_share = []  # éléments reçus du menu Windows, en attente de l'interface
        self.share_timer = None
        self.ui_sockets = set()
        self.history = cfg.load_history()
        self.stage_dir = Path(tempfile.gettempdir()) / f"pydrop-stage-{cfg.id[:8]}"
        shutil.rmtree(self.stage_dir, ignore_errors=True)
        self.stage_dir.mkdir(parents=True, exist_ok=True)

    # -- infos ---------------------------------------------------------------

    def public_info(self):
        return {"id": self.cfg.id, "name": self.cfg.name, "type": "desktop",
                "os": os_label(), "port": self.port, "v": VERSION}

    def broadcast_targets(self):
        targets = {"255.255.255.255"}
        for ip in local_ips():
            parts = ip.split(".")
            targets.add(".".join(parts[:3] + ["255"]))
        for p in self.peers.values():  # unicast aux pairs connus (réseaux sans broadcast)
            targets.add(p["ip"])
        return list(targets)

    def phone_urls(self):
        return [f"http://{ip}:{self.port}/" for ip in local_ips()]

    def device_info(self, dev_id):
        if dev_id in self.peers:
            return self.peers[dev_id]
        if dev_id in self.clients:
            return self.clients[dev_id]["info"]
        return None

    def devices(self):
        out = []
        for p in self.peers.values():
            out.append({k: p[k] for k in ("id", "name", "type", "os", "ip", "port")})
        for c in self.clients.values():
            out.append(dict(c["info"]))
        for d in out:
            d["connected"] = d["id"] in self.sessions
            d["token"] = self.sessions.get(d["id"])
            d["pending"] = d["id"] in self.pending_out
        return sorted(out, key=lambda d: d["id"])

    # -- interface locale ------------------------------------------------------

    def ui_send(self, msg):
        for ws in list(self.ui_sockets):
            if not ws.closed:
                asyncio.ensure_future(ws.send_json(msg))

    def push_devices(self):
        self.ui_send({"type": "devices", "devices": self.devices()})

    def add_history(self, item):
        self.history.insert(0, item)
        self.history = self.history[:100]
        self.cfg.save_history(self.history)

    # -- messagerie entre appareils --------------------------------------------

    async def send_to(self, dev_id, msg) -> bool:
        if dev_id in self.clients:
            ws = self.clients[dev_id]["ws"]
            if not ws.closed:
                await ws.send_json(msg)
                return True
            return False
        peer = self.peers.get(dev_id)
        if not peer:
            return False
        try:
            async with self.http.post(f"http://{peer['ip']}:{peer['port']}/api/msg",
                                      json={"from": self.public_info(), "msg": msg}) as r:
                return r.status == 200
        except Exception:
            return False

    async def on_peer_msg(self, src, msg):
        t = msg.get("type")
        sid = src["id"]
        if t == "request":
            req_id = msg.get("req_id")
            if sid in self.sessions:
                # Déjà connectés : on reconfirme sans redemander
                await self.send_to(sid, {"type": "response", "req_id": req_id, "accepted": True,
                                         "token": self.sessions[sid]})
                self.push_devices()
                return
            self.pending_in[req_id] = {"from": src, "ts": time.time()}
            self.ui_send({"type": "incoming", "req_id": req_id, "from": src})
        elif t == "response":
            if self.pending_out.get(sid) != msg.get("req_id"):
                return
            self.pending_out.pop(sid, None)
            accepted = bool(msg.get("accepted"))
            if accepted and msg.get("token"):
                self.sessions[sid] = msg["token"]
            self.ui_send({"type": "response", "peer": src, "accepted": accepted})
            self.push_devices()
        elif t == "cancel":
            if self.pending_in.pop(msg.get("req_id"), None):
                self.ui_send({"type": "incoming_cancel", "req_id": msg.get("req_id")})
        elif t == "disconnect":
            self.sessions.pop(sid, None)
            self.pending_out.pop(sid, None)
            self.ui_send({"type": "peer_disconnected", "peer": src})
            self.push_devices()
        elif t == "fetch_url":
            if sid in self.sessions:
                asyncio.ensure_future(self.fetch_video(src, msg))
        elif t == "mirror_request":
            if sid in self.sessions:
                self.set_mirror_opts(sid, msg.get("mode"), msg.get("record"))
                self.ui_send({"type": "mirror_open", "id": sid, **self.mirror_opts[sid]})
                asyncio.ensure_future(self.mirror_start(sid))
        elif t == "clip":
            if sid in self.sessions:
                self.receive_clip(src, msg.get("text"))
        elif t == "rc":
            if sid in self.sessions:
                await self.remote_control(src, msg)
        elif t == "fetch_cancel":
            for tid, j in list(self.fetch_jobs.items()):
                if j["src"] == sid and j["fid"] == msg.get("id"):
                    self.cancel_fetch(tid)
        elif t == "dl_cancel":
            # Le téléphone renonce à un fichier (proposé par le PC ou pris dans l'explorateur)
            fid = msg.get("id")
            s = self.staged.get(fid)
            if s and s["to"] == sid:
                self.cancel_staged(fid, notify_phone=False)
            elif self.browse_owner.get(fid) == sid:
                self.browse_owner.pop(fid, None)
                self.cancel_browse(fid)
        elif t == "received":
            # Un appareil confirme la bonne réception d'un fichier
            self.ui_send({"type": "peer_received", "peer": src, "name": msg.get("name")})

    # -- découverte ------------------------------------------------------------

    def on_announce(self, msg, ip):
        dev_id = msg["id"]
        if msg.get("bye"):
            if self.peers.pop(dev_id, None):
                self.pending_out.pop(dev_id, None)
                self.push_devices()
            return
        is_new = dev_id not in self.peers
        old = self.peers.get(dev_id, {})
        now = time.time()
        # Un même PC peut être vu via plusieurs interfaces : on garde la meilleure adresse
        ips = {k: v for k, v in old.get("ips", {}).items() if now - v < PEER_TIMEOUT}
        ips[ip] = now
        best = max(ips, key=lambda a: (not a.startswith("169.254."), ips[a]))
        self.peers[dev_id] = {
            "id": dev_id, "name": str(msg.get("name", "?"))[:60], "type": "desktop",
            "os": msg.get("os", ""), "ip": best, "port": int(msg.get("port", DEFAULT_PORT)),
            "last_seen": now, "static": old.get("static", False), "ips": ips,
        }
        ip = best
        if is_new or old.get("name") != self.peers[dev_id]["name"] or old.get("ip") != ip:
            self.push_devices()
        if is_new:
            # Réponse immédiate pour une découverte rapide et symétrique
            if self.discovery:
                self.discovery.announce(target=ip)
            asyncio.ensure_future(self.send_to(dev_id, {"type": "hello"}))

    async def add_static_peer(self, address):
        address = address.strip().replace("http://", "").rstrip("/")
        host, _, port = address.partition(":")
        port = int(port or DEFAULT_PORT)
        try:
            async with self.http.get(f"http://{host}:{port}/api/info",
                                     timeout=ClientTimeout(total=3)) as r:
                info = await r.json()
        except Exception:
            return False
        if info.get("id") == self.cfg.id:
            return False
        self.on_announce(info, host)
        self.peers[info["id"]]["static"] = True
        return True

    async def housekeeping(self):
        while True:
            await asyncio.sleep(1)
            now = time.time()
            changed = False
            for dev_id, p in list(self.peers.items()):
                if p.get("static"):
                    continue
                if now - p["last_seen"] > PEER_TIMEOUT:
                    del self.peers[dev_id]
                    self.pending_out.pop(dev_id, None)
                    changed = True
            for req_id, r in list(self.pending_in.items()):
                if now - r["ts"] > REQUEST_TIMEOUT:
                    del self.pending_in[req_id]
                    self.ui_send({"type": "incoming_cancel", "req_id": req_id})
                    await self.send_to(r["from"]["id"], {"type": "response", "req_id": req_id,
                                                         "accepted": False})
            for fid, s in list(self.staged.items()):
                if now - s["ts"] > 24 * 3600:
                    self.staged.pop(fid, None)
                    if s.get("own", True):
                        Path(s["path"]).unlink(missing_ok=True)
            if changed:
                self.push_devices()
            current_urls = self.phone_urls()
            if self.last_urls is None:
                self.last_urls = current_urls
            elif current_urls != self.last_urls:
                self.last_urls = current_urls
                self.ui_send({"type": "urls", "urls": current_urls})
                if current_urls:
                    if self.discovery:
                        self.discovery.announce()
                else:
                    if self.peers:
                        self.peers.clear()
                        self.pending_out.clear()
                        self.push_devices()
                    for cid, c in list(self.clients.items()):
                        if not c["info"].get("ip", "").startswith("127."):
                            asyncio.ensure_future(c["ws"].close())
            if self.discovery is None:
                try:
                    _, self.discovery = await self.loop.create_datagram_endpoint(
                        lambda: Discovery(self), sock=make_discovery_socket())
                except OSError:
                    pass

    async def announcer(self):
        while True:
            if self.discovery:
                self.discovery.announce()
            await asyncio.sleep(ANNOUNCE_EVERY)

    async def static_poller(self):
        while True:
            await asyncio.sleep(3)
            # Battement HTTP : garde la liste à jour même si l'UDP ne passe que dans un sens
            await asyncio.gather(*(self.send_to(d, {"type": "hello"}) for d in list(self.peers)),
                                 return_exceptions=True)
            for dev_id, p in list(self.peers.items()):
                if not p.get("static"):
                    continue
                try:
                    async with self.http.get(f"http://{p['ip']}:{p['port']}/api/info",
                                             timeout=ClientTimeout(total=2)) as r:
                        if r.status == 200:
                            p["last_seen"] = time.time()
                            continue
                except Exception:
                    pass
                if time.time() - p["last_seen"] > PEER_TIMEOUT:
                    p["static"] = False  # sera retiré par housekeeping

    # -- routes HTTP -----------------------------------------------------------

    async def h_info(self, request):
        return web.json_response(self.public_info())

    async def h_peers(self, request):
        me = self.public_info()
        me["ip"] = request.host.split(":")[0]
        others = [{k: p[k] for k in ("id", "name", "type", "os", "ip", "port")}
                  for p in self.peers.values()]
        return web.json_response({"self": me, "peers": others})

    async def h_msg(self, request):
        data = await request.json()
        src = data.get("from") or {}
        if not src.get("id") or src["id"] == self.cfg.id:
            return web.json_response({"ok": False}, status=400)
        # Un pair inconnu qui nous écrit (ex. broadcast bloqué) est ajouté à la liste
        self.on_announce({**src, "app": APP}, request.remote)
        await self.on_peer_msg(self.peers[src["id"]], data.get("msg") or {})
        return web.json_response({"ok": True})

    # -- réception de fichiers (reprenable) --------------------------------------
    #
    # Le fichier arrive dans « .pydrop-<tid>.part ». Si la connexion coupe, la partie reçue
    # est gardée : l'expéditeur demande /api/upload/status puis renvoie la suite (offset=…).

    def part_path(self, tid):
        return self.cfg.download_dir / f".pydrop-{tid}.part"

    def check_session(self, request):
        q = request.query
        src, token = q.get("from", ""), q.get("token", "")
        if not token or self.sessions.get(src) != token:
            raise web.HTTPForbidden(text="Connexion non autorisée")
        tid = q.get("tid", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", tid):
            raise web.HTTPBadRequest(text="Identifiant de transfert invalide")
        return src, tid

    async def h_upload_status(self, request):
        _, tid = self.check_session(request)
        part = self.part_path(tid)
        return web.json_response({"received": part.stat().st_size if part.exists() else 0,
                                  "cancelled": tid in self.rx_cancelled})

    async def h_upload_cancel(self, request):
        _, tid = self.check_session(request)
        self.cancel_rx(tid)
        return web.json_response({"ok": True})

    def cancel_rx(self, tid):
        self.rx_cancelled.add(tid)
        task = self.rx_tasks.get(tid)
        if task and not task.done():
            task.cancel()  # la tâche supprimera le fichier partiel
        else:
            self.part_path(tid).unlink(missing_ok=True)
            self.ui_send({"type": "rx_cancelled", "tid": tid})

    async def h_upload(self, request):
        src, tid = self.check_session(request)
        q = request.query
        if tid in self.rx_cancelled:
            return web.json_response({"error": "Transfert annulé", "cancelled": True}, status=410)
        name = safe_name(q.get("name", "fichier"))
        folder = safe_name(q["unpack"]) if q.get("unpack") else None
        offset = int(q.get("offset") or 0)
        size = int(q.get("size") or 0) or offset + (request.content_length or 0)
        info = self.device_info(src) or {"id": src, "name": "Appareil", "type": "desktop"}
        self.cfg.download_dir.mkdir(parents=True, exist_ok=True)

        # Une ancienne connexion pour ce même fichier traîne encore : on la termine d'abord
        old = self.rx_tasks.get(tid)
        if old and not old.done():
            old.cancel()
            await asyncio.wait({old}, timeout=5)
        part = self.part_path(tid)
        have = part.stat().st_size if part.exists() else 0
        if offset and offset != have:
            return web.json_response({"error": "Décalage invalide", "received": have}, status=409)
        if size and not has_room(self.cfg.download_dir, size - offset):
            self.ui_send({"type": "error", "message": f"Espace disque insuffisant pour recevoir {name}"})
            return web.json_response({"error": f"Espace disque insuffisant sur {self.cfg.name}"}, status=507)

        self.rx_tasks[tid] = asyncio.current_task()
        self.ui_send({"type": "rx_start", "tid": tid, "name": folder or name, "size": size, "from": info,
                      "received": offset, "is_dir": bool(folder)})
        received, last = offset, 0.0
        run = self.loop.run_in_executor  # le disque peut être lent : on ne bloque jamais le moteur
        try:
            f = await run(None, open, part, "ab" if offset else "wb")
            try:
                async for chunk in request.content.iter_chunked(1 << 20):
                    await run(None, f.write, chunk)
                    received += len(chunk)
                    now = time.monotonic()
                    if now - last > 0.15:
                        last = now
                        self.ui_send({"type": "rx_progress", "tid": tid, "received": received})
            finally:
                await run(None, f.close)
            if size and received < size:
                raise ConnectionError("transfert incomplet")
            dest = await run(None, unique_path, self.cfg.download_dir / name)
            await run(None, os.replace, part, dest)
        except BaseException as e:
            if is_disk_full(e):
                part.unlink(missing_ok=True)
                self.rx_cancelled.add(tid)
                self.ui_send({"type": "rx_error", "tid": tid, "error": "Disque plein"})
                return web.json_response({"error": f"Espace disque insuffisant sur {self.cfg.name}"}, status=507)
            if tid in self.rx_cancelled:
                part.unlink(missing_ok=True)
                self.ui_send({"type": "rx_cancelled", "tid": tid})
            elif self.rx_tasks.get(tid) is asyncio.current_task():
                # Coupure : on garde la partie reçue pour reprendre plus tard
                self.ui_send({"type": "rx_paused", "tid": tid, "received": received})
            if isinstance(e, asyncio.CancelledError):
                raise
            return web.json_response({"error": str(e) or "interrompu"}, status=500)
        finally:
            if self.rx_tasks.get(tid) is asyncio.current_task():
                del self.rx_tasks[tid]
        if folder:
            # Un dossier arrive compressé : on le décompresse puis on supprime l'archive
            self.ui_send({"type": "rx_unpack", "tid": tid})
            target = unique_path(self.cfg.download_dir / folder)

            def unpack():
                with zipfile.ZipFile(dest) as z:
                    z.extractall(target)  # extractall neutralise les chemins « .. » et absolus
                os.unlink(dest)

            try:
                await self.loop.run_in_executor(None, unpack)
                dest = target
            except (OSError, zipfile.BadZipFile) as e:
                self.ui_send({"type": "error", "message": f"Décompression impossible, archive gardée : {e}"})
        item = {"tid": tid, "name": dest.name, "path": str(dest), "size": received,
                "from": info.get("name"), "from_type": info.get("type"), "ts": time.time(),
                "dir": "in", "is_dir": dest.is_dir()}
        self.add_history(item)
        self.ui_send({"type": "rx_done", "tid": tid, "item": item})
        return web.json_response({"ok": True, "name": dest.name})

    # -- envoi d'un fichier en flux, avec reprise (en-tête Range) ------------------

    async def stream_file(self, request, path, name, size, key, notify):
        """notify(state, sent) avec state ∈ started / progress / paused / done."""
        start = 0
        m = re.match(r"bytes=(\d+)-", request.headers.get("Range", ""))
        if m:
            start = int(m.group(1))
            if start >= size:
                return web.Response(status=416, headers={"Content-Range": f"bytes */{size}",
                                                         "Access-Control-Allow-Origin": "*"})
        headers = {
            "Content-Type": "application/octet-stream",
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}",
            "Content-Length": str(size - start),
            "Accept-Ranges": "bytes",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Expose-Headers": "Content-Range, Content-Length",
        }
        if m:
            headers["Content-Range"] = f"bytes {start}-{size - 1}/{size}"
        resp = web.StreamResponse(status=206 if m else 200, headers=headers)
        old = self.dl_tasks.get(key)
        if old and not old.done():
            old.cancel()
        self.dl_tasks[key] = asyncio.current_task()
        await resp.prepare(request)
        sent, last = start, 0.0
        notify("started", sent)
        run = self.loop.run_in_executor
        try:
            f = await run(None, open, path, "rb")
            try:
                await run(None, f.seek, start)
                while chunk := await run(None, f.read, 1 << 20):
                    await resp.write(chunk)
                    sent += len(chunk)
                    now = time.monotonic()
                    if now - last > 0.3:
                        last = now
                        notify("progress", sent)
            finally:
                await run(None, f.close)
            await resp.write_eof()
        except (ConnectionError, asyncio.CancelledError):
            notify("paused", sent)
            raise
        finally:
            if self.dl_tasks.get(key) is asyncio.current_task():
                del self.dl_tasks[key]
        notify("done", sent)
        return resp

    def cancel_staged(self, fid, notify_phone=True):
        s = self.staged.pop(fid, None)
        if not s:
            return
        task = self.dl_tasks.get(fid)
        if task and not task.done():
            task.cancel()
        if s.get("own", True):
            Path(s["path"]).unlink(missing_ok=True)
        self.ui_send({"type": "tx_cancelled", "tid": s["tid"]})
        if notify_phone:
            asyncio.ensure_future(self.send_to(s["to"], {"type": "file_cancel", "id": fid}))

    # -- envoi depuis un chemin (menu Windows, dossiers) ------------------------------

    def out_ui(self, job, **patch):
        job.update(patch)
        self.ui_send({"type": "out", **{k: job.get(k) for k in (
            "tid", "name", "size", "done", "status", "phase", "note", "error", "peer", "peerType", "isDir", "kind")}})

    def send_paths(self, dev_id, paths):
        dev = self.device_info(dev_id)
        if not dev or dev_id not in self.sessions:
            self.ui_send({"type": "error", "message": "Cet appareil n'est pas connecté"})
            return
        queue = self.out_queues.setdefault(dev_id, [])
        for raw in paths:
            d = describe_path(raw)
            if not d:
                self.ui_send({"type": "error", "message": f"Introuvable : {raw}"})
                continue
            tid = uuid.uuid4().hex
            job = {"tid": tid, "dev": dev_id, "path": d["path"], "name": d["name"], "size": d["size"], "done": 0,
                   "status": "queued", "phase": "", "note": "", "error": "", "peer": dev["name"],
                   "peerType": dev["type"], "isDir": d["is_dir"], "cancelled": False, "zip": None, "task": None}
            self.out_jobs[tid] = job
            self.out_ui(job)
            queue.append(tid)
        if queue and dev_id not in self.out_running:
            self.out_running.add(dev_id)
            asyncio.ensure_future(self.out_worker(dev_id))

    async def out_worker(self, dev_id):
        queue = self.out_queues[dev_id]
        try:
            while queue:
                job = self.out_jobs.get(queue[0])
                if job and not job["cancelled"]:
                    job["task"] = asyncio.ensure_future(self.run_out_job(job))
                    try:
                        await job["task"]
                    except asyncio.CancelledError:
                        if not job["cancelled"]:
                            raise
                    except Exception as e:
                        message = "Espace disque insuffisant sur ce PC" if is_disk_full(e) else str(e) or "Échec de l'envoi"
                        self.out_ui(job, status="error", error=message)
                        self.drop_zip(job)
                queue.pop(0)
        finally:
            self.out_running.discard(dev_id)

    def drop_zip(self, job):
        path, job["zip"] = job.get("zip"), None
        if path:
            self.remove_later(Path(path))

    def remove_later(self, path, tries=20):
        # Windows refuse de supprimer un fichier encore ouvert par l'envoi qu'on vient d'arrêter
        try:
            path.unlink(missing_ok=True)
        except OSError:
            if tries:
                self.loop.call_later(0.5, self.remove_later, path, tries - 1)

    # -- vidéo par lien : le PC télécharge, puis envoie le fichier au téléphone --------

    # -- voir et contrôler le téléphone ------------------------------------------------
    #
    # Android 11+ : « Débogage sans fil ». La première fois, on associe le PC avec le code à
    # 6 chiffres affiché par le téléphone ; ensuite, on retrouve le téléphone par mDNS et on lance scrcpy.

    def mirror_ui(self, dev_id, state, message="", **extra):
        opts = self.mirror_opts.get(dev_id) or {"mode": "screen", "record": False}
        self.ui_send({"type": "mirror", "id": dev_id, "state": state, "message": message, **opts, **extra})
        # Le téléphone affiche aussi où en est l'affichage, dans son onglet « Écran »
        if dev_id in self.clients:
            asyncio.ensure_future(self.send_to(dev_id, {"type": "mirror_state", "state": state, "message": message,
                                                        "pc": self.cfg.name, **opts}))

    def set_mirror_opts(self, dev_id, mode=None, record=None):
        opts = self.mirror_opts.setdefault(dev_id, {"mode": "screen", "record": False})
        if mode in ("screen", "front", "back"):
            opts["mode"] = mode
        if record is not None:
            opts["record"] = bool(record)

    # -- presse-papiers partagé -------------------------------------------------

    def remember_clip(self, item):
        self.clips.insert(0, item)
        self.clips = self.clips[:20]

    def receive_clip(self, src, text):
        if not isinstance(text, str) or not text:
            return
        text = text[:100000]
        copied = False
        if winctl:
            copied = winctl.set_clipboard(text)
            self.clip_seq = winctl.clipboard_seq()  # pas de renvoi automatique de ce texte
        item = {"text": text, "from": src.get("name", "?"), "dir": "in", "ts": time.time()}
        self.remember_clip(item)
        self.ui_send({"type": "clip_in", "item": item, "copied": copied})

    async def send_clip(self, ids, text=None):
        if text is None:
            text = winctl.get_clipboard() if winctl else ""
        text = (text or "")[:100000]
        if not text.strip():
            self.ui_send({"type": "error", "message": "Le presse-papiers est vide : copiez d'abord un texte (Ctrl+C)"})
            return
        names = []
        for dev_id in ids:
            if dev_id in self.sessions and await self.send_to(dev_id, {"type": "clip", "text": text}):
                info = self.device_info(dev_id)
                names.append(info["name"] if info else "?")
        if not names:
            self.ui_send({"type": "error", "message": "Aucun appareil connecté pour recevoir le texte"})
            return
        item = {"text": text, "to": ", ".join(names), "dir": "out", "ts": time.time()}
        self.remember_clip(item)
        self.ui_send({"type": "clip_out", "item": item})

    async def clip_watcher(self):
        """Mode automatique : tout texte copié sur ce PC part vers les appareils connectés."""
        if not winctl:
            return
        self.clip_seq = winctl.clipboard_seq()
        while True:
            await asyncio.sleep(1.0)
            try:
                seq = winctl.clipboard_seq()
                if seq == self.clip_seq:
                    continue
                self.clip_seq = seq
                if not self.cfg.clip_auto or not self.sessions:
                    continue
                text = winctl.get_clipboard()
                if text.strip() and (not self.clips or self.clips[0]["text"] != text):
                    await self.send_clip(list(self.sessions), text)
            except Exception as e:
                print("presse-papiers :", e)

    # -- télécommande (téléphone -> ce PC) -----------------------------------------

    async def remote_control(self, src, msg):
        sid = src["id"]
        if not winctl:
            return
        if not self.cfg.allow_remote:
            await self.send_to(sid, {"type": "rc_denied", "pc": self.cfg.name})
            return
        now = time.time()
        if now - self.remote_seen.get(sid, 0) > 120:
            self.ui_send({"type": "remote_active", "name": src.get("name", "Un téléphone")})
        self.remote_seen[sid] = now
        a = msg.get("a")
        try:
            if a == "move":
                winctl.mouse_move(float(msg.get("dx", 0)), float(msg.get("dy", 0)))
            elif a == "button":
                winctl.mouse_button(msg.get("b", "left"), msg.get("act", "click"), int(msg.get("n", 1)))
            elif a == "scroll":
                winctl.mouse_scroll(float(msg.get("dy", 0)), float(msg.get("dx", 0)))
            elif a == "key":
                winctl.press(str(msg.get("k", "")))
            elif a == "text":
                winctl.type_text(str(msg.get("t", "")))
        except (TypeError, ValueError):
            pass

    # -- notifications du téléphone --------------------------------------------------

    async def h_notify(self, request):
        """Le téléphone (service Android) transmet une notification : WhatsApp, SMS…"""
        q = request.query
        src, token = q.get("from", ""), q.get("token", "")
        if not token or self.sessions.get(src) != token:
            raise web.HTTPForbidden(text="Connexion non autorisée")
        try:
            data = await request.json()
        except Exception:
            raise web.HTTPBadRequest()
        pkg = str(data.get("pkg", ""))[:200]
        title, text = str(data.get("title", ""))[:300], str(data.get("text", ""))[:2000]
        app = str(data.get("app", ""))[:80] or pkg
        if data.get("removed"):
            return web.json_response({"ok": True})
        if not (title or text) or any(m["pkg"] == pkg for m in self.cfg.notif_muted):
            return web.json_response({"ok": True, "muted": True})
        key = f"{src}|{pkg}|{title}|{text}"
        now = time.time()
        self.notif_seen = {k: t for k, t in self.notif_seen.items() if now - t < 20}
        if key in self.notif_seen:
            return web.json_response({"ok": True, "dup": True})
        self.notif_seen[key] = now
        icon = str(data.get("icon", ""))
        icon = icon if len(icon) < 200000 else ""
        can_reply = bool(data.get("can_reply"))
        notif_key = str(data.get("notif_key", ""))
        item = {"id": uuid.uuid4().hex[:12], "pkg": pkg, "app": app, "title": title, "text": text,
                "icon": icon, "ts": now, "from": self.dev_names.get(src, "Téléphone"), "dev": src,
                "can_reply": can_reply, "notif_key": notif_key}
        self.notifs.insert(0, item)
        self.notifs = self.notifs[:50]
        self.ui_send({"type": "notif", "item": item})
        if self.cfg.notif_toast and winctl:
            path = winctl.save_icon(pkg, icon)
            winctl.show_toast(app, title, text, path)
        return web.json_response({"ok": True})

    async def h_notif_poll(self, request):
        """Long-poll pour les commandes vers le téléphone (réponses WhatsApp, SMS...)."""
        q = request.query
        src, token = q.get("from", ""), q.get("token", "")
        if not token or self.sessions.get(src) != token:
            raise web.HTTPForbidden(text="Connexion non autorisée")
        queue = self.dev_commands.setdefault(src, asyncio.Queue())
        try:
            cmd = await asyncio.wait_for(queue.get(), timeout=25.0)
            return web.json_response(cmd)
        except asyncio.TimeoutError:
            return web.json_response({"ok": True})

    async def adb(self, *args, timeout=25):
        folder = await self.tools.scrcpy(lambda *_: None)
        self.adb_used = True
        try:
            p = await asyncio.create_subprocess_exec(
                str(folder / "adb.exe"), *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                env={**os.environ, "ADB_MDNS_OPENSCREEN": "1"}, cwd=str(folder),
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            out, _ = await asyncio.wait_for(p.communicate(), timeout)
            return p.returncode, out.decode("utf-8", "replace")
        except asyncio.TimeoutError:
            return -1, "délai dépassé"

    async def mdns_service(self, ip, kind, wait=6.0):
        """Adresse ip:port annoncée par le téléphone (kind : « tls-connect » ou « tls-pairing »)."""
        end = time.monotonic() + wait
        while True:
            _, out = await self.adb("mdns", "services", timeout=10)
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 3 and kind in parts[1] and parts[2].split(":")[0] == ip:
                    return parts[2]
            if time.monotonic() > end:
                return None
            await asyncio.sleep(1)

    async def mirror_start(self, dev_id):
        info = self.clients.get(dev_id, {}).get("info")
        if not info or dev_id not in self.sessions:
            self.mirror_ui(dev_id, "error", "Ce téléphone n'est pas connecté à PyDrop")
            return
        proc = self.mirrors.get(dev_id)
        if proc and proc.returncode is None:
            self.mirror_ui(dev_id, "running", "La fenêtre du téléphone est déjà ouverte")
            return
        if dev_id in self.mirror_busy:
            return
        self.mirror_busy.add(dev_id)
        ip, name = info["ip"], info["name"]
        try:
            await self.tools.scrcpy(lambda text, d, t: self.mirror_ui(dev_id, "preparing", text))
            self.mirror_ui(dev_id, "connecting", f"Recherche de {name}…")
            await self.adb("start-server", timeout=30)
            target = None
            # 1. Déjà passé en sans-fil depuis le câble (port 5555) : marche aussi en partage de connexion
            _, out = await self.adb("connect", f"{ip}:5555", timeout=8)
            if "connected to" in out.lower():
                target = f"{ip}:5555"
            # 2. Branché en USB : on l'utilise, et on passe en sans-fil pour pouvoir débrancher
            if not target:
                usb = await self.usb_device()
                if usb == "unauthorized":
                    self.mirror_ui(dev_id, "need_usb_auth", "Sur le téléphone, acceptez « Autoriser le débogage USB » "
                                                            "(cochez « Toujours autoriser »), puis réessayez.")
                    return
                if usb:
                    self.mirror_ui(dev_id, "connecting", "Câble USB détecté : passage en sans-fil…")
                    await self.adb("-s", usb, "tcpip", "5555", timeout=15)
                    # Le téléphone redémarre son service de débogage : on attend qu'il soit de retour
                    for _ in range(8):
                        await asyncio.sleep(1.5)
                        _, out = await self.adb("connect", f"{ip}:5555", timeout=8)
                        if "connected to" in out.lower():
                            target = f"{ip}:5555"
                            break
                    if not target:
                        await self.adb("-s", usb, "wait-for-device", timeout=20)
                        target = usb
            # 3. Débogage sans fil d'Android 11+ (téléphone connecté à un Wi-Fi)
            if not target:
                target = await self.mdns_service(ip, "tls-connect", wait=4)
                if target:
                    _, out = await self.adb("connect", target)
                    if "connected" not in out.lower():
                        target = None
            if not target:
                # Pas encore associé, ou débogage sans fil coupé : on guide l'utilisateur
                pairing = await self.mdns_service(ip, "tls-pairing", wait=2)
                self.mirror_ui(dev_id, "need_pair", "", pair_port=(pairing or ":").split(":")[1])
                await self.send_to(dev_id, {"type": "mirror_help"})
                return
            await self.launch_scrcpy(dev_id, target, name)
        except Exception as e:
            print("Affichage du téléphone :", repr(e))
            self.mirror_ui(dev_id, "error", str(e) or "Échec de l'affichage du téléphone")
        finally:
            self.mirror_busy.discard(dev_id)

    def audio_args(self):
        """Par défaut le son reste sur le téléphone (scrcpy, lui, le détourne vers le PC)."""
        if self.cfg.mirror_audio == "pc":
            return []
        if self.cfg.mirror_audio == "both":
            return ["--audio-dup"]  # Android 13+ : le son joue sur le téléphone ET sur le PC
        return ["--no-audio"]

    async def usb_device(self):
        """Numéro du téléphone branché en USB, « unauthorized » s'il attend l'accord, sinon None."""
        _, out = await self.adb("devices", timeout=10)
        found = None
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 2 or ":" in parts[0] or parts[0].startswith(("adb-", "emulator-")):
                continue
            if parts[1] == "device":
                return parts[0]
            if parts[1] == "unauthorized":
                found = "unauthorized"
        return found

    async def mirror_pair(self, dev_id, code, port):
        info = self.clients.get(dev_id, {}).get("info")
        if not info:
            self.mirror_ui(dev_id, "error", "Ce téléphone n'est pas connecté à PyDrop")
            return
        code = re.sub(r"\D", "", code)
        if len(code) != 6:
            self.mirror_ui(dev_id, "need_pair", "Le code d'association a 6 chiffres")
            return
        self.mirror_ui(dev_id, "connecting", "Association avec le téléphone…")
        address = f"{info['ip']}:{port}" if port.isdigit() else await self.mdns_service(info["ip"], "tls-pairing")
        if not address:
            self.mirror_ui(dev_id, "need_pair", "Fenêtre d'association introuvable : sur le téléphone, touchez "
                                                "« Associer l'appareil avec un code d'association » et laissez-la ouverte")
            return
        _, out = await self.adb("pair", address, code, timeout=30)
        if "success" not in out.lower():
            print("adb pair :", out.strip())
            self.mirror_ui(dev_id, "need_pair", "Code refusé ou fenêtre fermée. Rouvrez l'association sur le téléphone et réessayez.")
            return
        await asyncio.sleep(1.5)
        await self.mirror_start(dev_id)

    async def launch_scrcpy(self, dev_id, target, name):
        folder = await self.tools.scrcpy(lambda *_: None)
        opts = self.mirror_opts.get(dev_id) or {"mode": "screen", "record": False}
        camera = opts["mode"] in ("front", "back")
        what = {"front": "caméra avant", "back": "caméra arrière"}.get(opts["mode"], "écran")
        self.mirror_ui(dev_id, "connecting", f"Ouverture de la {what} du téléphone…" if camera
                       else "Ouverture de l'écran du téléphone…")
        if camera:
            # La caméra du téléphone dans une fenêtre du PC (Android 12+). Pas de contrôle tactile.
            args = ["--video-source=camera", f"--camera-facing={opts['mode']}", "--no-audio", "--no-control",
                    "--max-size", "1920", "--video-bit-rate", "10M",
                    "--window-title", f"{name} — {what[0].upper() + what[1:]} — PyDrop"]
        else:
            args = ["--stay-awake", "--max-size", "1600", "--video-bit-rate", "8M", "--shortcut-mod", "lctrl",
                    "--window-title", f"{name} — PyDrop", *self.audio_args()]
        record_path = None
        if opts.get("record"):
            self.cfg.download_dir.mkdir(parents=True, exist_ok=True)
            label = "Camera" if camera else "Ecran"
            record_path = unique_path(self.cfg.download_dir /
                                      f"PyDrop {label} {safe_name(name)} {time.strftime('%Y-%m-%d %Hh%M')}.mp4")
            args.append(f"--record={record_path}")
        proc = await asyncio.create_subprocess_exec(
            str(folder / "scrcpy.exe"), "-s", target, *args,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, cwd=str(folder),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.mirrors[dev_id] = proc
        errors = []
        shown = asyncio.Event()

        async def read_output():
            async for line in proc.stdout:
                text = line.decode("utf-8", "replace").strip()
                if not text:
                    continue
                errors.append(text)
                # « Texture: » = la première image est arrivée et la fenêtre est ouverte
                if "Texture:" in text:
                    shown.set()
        reader = asyncio.ensure_future(read_output())
        self.mirror_ui(dev_id, "connecting", "Ouverture de l'écran… (déverrouillez le téléphone si besoin)")
        try:
            await asyncio.wait_for(shown.wait(), 30)
            rec = " · enregistrement en cours" if record_path else ""
            self.mirror_ui(dev_id, "running", (f"La {what} de {name} est ouverte dans sa propre fenêtre" if camera
                                               else f"L'écran de {name} est ouvert dans sa propre fenêtre") + rec)
        except asyncio.TimeoutError:
            if proc.returncode is None:
                proc.kill()
                self.mirror_ui(dev_id, "error", "Le téléphone n'envoie pas son image : déverrouillez-le, puis Réessayer")
        await proc.wait()
        await reader
        self.mirrors.pop(dev_id, None)
        if record_path:
            await asyncio.sleep(0.5)
            if record_path.exists() and record_path.stat().st_size > 0:
                item = {"tid": uuid.uuid4().hex, "name": record_path.name, "size": record_path.stat().st_size,
                        "from": name, "from_type": "mobile", "ts": time.time(), "dir": "in", "path": str(record_path)}
                self.add_history(item)
                self.ui_send({"type": "recorded", "item": item})
            else:
                record_path.unlink(missing_ok=True)
        failure = next((e for e in reversed(errors) if "ERROR" in e), None)
        if failure:
            print("scrcpy :", failure)
            text = failure.replace("ERROR:", "").strip()
            if any(k in text for k in ("Could not find any ADB device", "not found", "Server connection failed", "offline")):
                text = "Téléphone introuvable : rebranchez le câble USB, puis Réessayer"
            elif "camera" in text.lower() and ("12" in text or "not supported" in text.lower()):
                text = "La caméra demande Android 12 ou plus récent"
            elif "camera" in text.lower():
                text = "Caméra indisponible : fermez l'application qui l'utilise sur le téléphone, puis Réessayer"
            self.mirror_ui(dev_id, "error", ("Affichage interrompu : " if shown.is_set() else "") + text[:160])
        elif shown.is_set():
            self.mirror_ui(dev_id, "closed", "Fenêtre du téléphone fermée")

    def cancel_fetch(self, tid):
        j = self.fetch_jobs.get(tid)
        if not j or j["cancelled"]:
            return
        j["cancelled"] = True
        if j.get("proc") and j["proc"].returncode is None:
            try:
                j["proc"].kill()
            except ProcessLookupError:
                pass
        if j.get("task") and not j["task"].done() and not j.get("proc"):
            j["task"].cancel()

    async def fetch_video(self, src, msg):
        sid = src["id"]
        fid = str(msg.get("id", ""))[:64]
        found = URL_RE.search(str(msg.get("url", "")))
        mode = "audio" if msg.get("mode") == "audio" else "video"
        keep_on_pc = msg.get("dest") == "pc"
        tid = uuid.uuid4().hex
        work = self.stage_dir / f"video-{tid}"
        job = {"tid": tid, "name": "Vidéo en ligne", "size": 0, "done": 0, "status": "active", "phase": "Préparation…",
               "note": "", "error": "", "peer": src.get("name"), "peerType": src.get("type"), "isDir": False,
               "kind": "fetch"}
        state = self.fetch_jobs[tid] = {"src": sid, "fid": fid, "cancelled": False, "proc": None,
                                        "task": asyncio.current_task()}

        def report(status="active", **kw):
            self.out_ui(job, status=status, **kw)
            asyncio.ensure_future(self.send_to(sid, {
                "type": "fetch_status", "id": fid, "state": status, "phase": job["phase"], "name": job["name"],
                "done": job["done"], "size": job["size"], "error": job["error"]}))

        def tool_progress(text, done, total):
            report(phase=text, done=done, size=total)

        try:
            if not found:
                raise SendRefused("Lien invalide")
            url = found.group(0)
            report(phase="Préparation…")
            ytdlp = await self.tools.ytdlp(tool_progress)
            runtime = await self.tools.js_runtime(tool_progress)
            if mode == "video":
                ffmpeg = await self.tools.ffmpeg(tool_progress)
                fmt = "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/bv*[height<=1080]+ba/b[height<=1080]/b"
                extra = ["--merge-output-format", "mp4", "--ffmpeg-location", ffmpeg]
            else:
                fmt, extra = "ba[ext=m4a]/ba/b", []
            if state["cancelled"]:
                raise JobCancelled()
            work.mkdir(parents=True, exist_ok=True)
            args = [ytdlp, "--no-playlist", "--newline", "--no-colors", "--encoding", "utf-8", "--quiet", "--progress",
                    "--no-simulate", "--no-mtime", "-f", fmt, *extra, "-P", str(work), "-o", "%(title).120B.%(ext)s",
                    "--js-runtimes", runtime,
                    *(["--cookies-from-browser", self.cfg.video_cookies] if self.cfg.video_cookies else []),
                    "--print", "before_dl:PYDROPTITLE %(title)s",
                    "--print", "after_move:PYDROPFILE %(filepath)s",
                    "--progress-template", "download:PYDROPPROG %(progress.downloaded_bytes)s "
                                           "%(progress.total_bytes)s %(progress.total_bytes_estimate)s",
                    url]
            proc = state["proc"] = await asyncio.create_subprocess_exec(
                *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            errors = []

            async def read_errors():
                async for line in proc.stderr:
                    text = line.decode("utf-8", "replace").strip()
                    if text:
                        errors.append(text)
            err_task = asyncio.ensure_future(read_errors())
            result, last = None, 0.0
            async for line in proc.stdout:
                text = line.decode("utf-8", "replace").strip()
                if text.startswith("PYDROPTITLE "):
                    job["name"] = text[12:] or job["name"]
                    report(phase="Téléchargement sur le PC…", done=0, size=0)
                elif text.startswith("PYDROPFILE "):
                    result = text[11:]
                elif text.startswith("PYDROPPROG ") and time.monotonic() - last > 0.3:
                    last = time.monotonic()
                    nums = [int(float(v)) if v not in ("NA", "None") else 0 for v in text.split()[1:4]]
                    report(phase="Téléchargement sur le PC…", done=nums[0], size=nums[1] or nums[2])
            await proc.wait()
            await err_task
            if state["cancelled"]:
                raise JobCancelled()
            if proc.returncode != 0 or not result or not os.path.isfile(result):
                last_err = next((e for e in reversed(errors) if "ERROR" in e), errors[-1] if errors else "")
                print(f"yt-dlp a échoué ({url}) :", last_err)
                raise SendRefused(friendly_video_error(last_err, self.cfg.video_cookies))
            size = os.path.getsize(result)
            if keep_on_pc:
                # Gardée sur ce PC, dans le dossier de réception
                self.cfg.download_dir.mkdir(parents=True, exist_ok=True)
                dest = unique_path(self.cfg.download_dir / os.path.basename(result))
                await self.loop.run_in_executor(None, shutil.move, result, dest)
                shutil.rmtree(work, ignore_errors=True)
                item = {"tid": tid, "name": dest.name, "path": str(dest), "size": size, "from": src.get("name"),
                        "from_type": src.get("type"), "ts": time.time(), "dir": "in", "is_dir": False}
                self.add_history(item)
                job["name"] = dest.name
                report(status="done", phase=f"Enregistrée sur {self.cfg.name}", done=size, size=size)
                self.ui_send({"type": "rx_done", "tid": tid, "item": item})
                return
            report(status="done", phase="Envoi au téléphone…", done=size, size=size)
            self.temp_files.add(result)
            self.send_paths(sid, [result])
        except (JobCancelled, asyncio.CancelledError):
            report(status="cancelled", phase="")
            shutil.rmtree(work, ignore_errors=True)
        except Exception as e:
            report(status="error", error=str(e) or "Échec du téléchargement", phase="")
            shutil.rmtree(work, ignore_errors=True)
        finally:
            self.fetch_jobs.pop(tid, None)

    def cancel_out(self, tid):
        job = self.out_jobs.get(tid)
        if not job or job["cancelled"]:
            return
        job["cancelled"] = True
        # Pendant la compression, le fil de travail s'arrête seul puis nettoie l'archive
        if job["task"] and not job["task"].done() and not job.get("compressing"):
            job["task"].cancel()
        token, peer = self.sessions.get(job["dev"]), self.peers.get(job["dev"])
        if token and peer:
            asyncio.ensure_future(self.http.post(
                f"http://{peer['ip']}:{peer['port']}/api/upload/cancel",
                params={"from": self.cfg.id, "token": token, "tid": tid}))
        self.out_ui(job, status="cancelled")

    async def run_out_job(self, job):
        try:
            source = Path(job["path"])
            folder = None
            if job["isDir"]:
                folder = job["name"]
                source = await self.compress_for_job(job, source)
            job.update(send_path=str(source))
            size = source.stat().st_size
            dev = self.device_info(job["dev"])
            if dev and dev["type"] == "mobile":
                await self.offer_to_phone(job, source, size, folder)
            else:
                await self.upload_to_peer(job, source, size, folder)
        except asyncio.CancelledError:
            self.drop_zip(job)
            raise
        except JobCancelled:
            self.drop_zip(job)

    async def compress_for_job(self, job, src):
        dest = self.stage_dir / f"{job['tid']}.zip"
        # On ne sait pas ce que donnera la compression : on compte le pire cas pour l'archive temporaire
        total = await self.loop.run_in_executor(None, folder_size, src)
        if not has_room(self.stage_dir, total):
            raise SendRefused("Espace disque insuffisant sur ce PC pour compresser ce dossier")
        job["zip"] = str(dest)
        last = [0.0]

        def progress(done, total):
            now = time.monotonic()
            if now - last[0] > 0.2:
                last[0] = now
                self.loop.call_soon_threadsafe(lambda: None if job["cancelled"] else self.out_ui(
                    job, status="active", phase="Compression…", done=done, size=total))

        self.out_ui(job, status="active", phase="Compression…", done=0)
        job["compressing"] = True
        try:
            skipped = await self.loop.run_in_executor(None, zip_folder, src, dest, progress, lambda: job["cancelled"])
        finally:
            job["compressing"] = False
        if skipped:
            self.ui_send({"type": "error", "message": f"{job['name']} : {skipped} fichier(s) illisible(s) ignoré(s)"})
        return dest

    async def offer_to_phone(self, job, source, size, folder):
        dev_id = job["dev"]
        if dev_id not in self.clients or dev_id not in self.sessions:
            raise ConnectionError("Le téléphone n'est plus connecté")
        fid = uuid.uuid4().hex
        name = source.name if not folder else f"{safe_name(folder)}.zip"
        self.staged[fid] = {"path": str(source), "name": name, "size": size, "to": dev_id, "ts": time.time(),
                            "tid": job["tid"], "own": bool(folder) or str(source) in self.temp_files}
        job["zip"] = None  # le fichier appartient maintenant à la liste « staged »
        self.out_ui(job, size=size, done=0, phase="En attente du téléphone…")
        await self.send_to(dev_id, {"type": "file", "id": fid, "name": name, "size": size, "url": f"/api/dl/{fid}",
                                    "video": str(source) in self.temp_files,
                                    "unpack": folder or "", "from": self.public_info()})

    async def upload_to_peer(self, job, source, size, folder):
        """Envoie vers un autre PC ; une coupure met en pause et l'envoi reprend là où il était."""
        tid, dev_id = job["tid"], job["dev"]
        while True:
            peer, token = self.peers.get(dev_id), self.sessions.get(dev_id)
            if not peer:
                self.out_ui(job, status="paused", size=size, note=f"reprise automatique au retour de {job['peer']}")
                await asyncio.sleep(2)
                continue
            if not token:
                self.out_ui(job, status="paused", size=size, note=f"Reconnectez-vous à {job['peer']} pour reprendre")
                await asyncio.sleep(2)
                continue
            base = f"http://{peer['ip']}:{peer['port']}/api/upload"
            auth = {"from": self.cfg.id, "token": token, "tid": tid}
            try:
                async with self.http.get(base + "/status", params=auth) as r:
                    if r.status == 403:
                        status, st = 403, {}
                    else:
                        status, st = r.status, await r.json()
                if status == 403:
                    self.sessions.pop(dev_id, None)
                    self.push_devices()
                    continue
                if st.get("cancelled"):
                    self.out_ui(job, status="cancelled")
                    self.drop_zip(job)
                    return
                offset = min(int(st.get("received") or 0), size)
                self.out_ui(job, status="active", phase="", note="", size=size, done=offset)

                async def body():
                    sent, last = offset, 0.0
                    with open(source, "rb") as f:
                        f.seek(offset)
                        while chunk := await self.loop.run_in_executor(None, f.read, 1 << 20):
                            yield chunk
                            sent += len(chunk)
                            now = time.monotonic()
                            if now - last > 0.15:
                                last = now
                                self.out_ui(job, done=sent)

                params = {**auth, "name": source.name if not folder else f"{safe_name(folder)}.zip",
                          "size": str(size), "offset": str(offset)}
                if folder:
                    params["unpack"] = folder
                async with self.http.post(base, params=params, data=body(),
                                          headers={"Content-Type": "application/octet-stream"},
                                          timeout=ClientTimeout(total=None, sock_connect=8)) as r:
                    status = r.status
                    if status == 507:
                        raise SendRefused((await r.json()).get("error") or "Espace disque insuffisant en face")
                if status == 200:
                    self.out_ui(job, status="done", done=size, size=size, phase="")
                    self.drop_zip(job)
                    return
                if status == 410:
                    self.out_ui(job, status="cancelled")
                    self.drop_zip(job)
                    return
                if status == 403:
                    self.sessions.pop(dev_id, None)
                    self.push_devices()
                    continue
                raise ConnectionError(f"réponse {status}")
            except FileNotFoundError:
                raise ConnectionError("Le fichier n'existe plus sur ce PC")
            except (ClientError, ConnectionError, asyncio.TimeoutError, OSError):
                self.out_ui(job, status="paused", note=f"reprise automatique au retour de {job['peer']}")
                await asyncio.sleep(2)

    async def h_local_send(self, request):
        # Appelé par PyDropSend.exe. L'en-tête et l'absence de CORS écartent les sites web.
        if not is_local(request) or request.headers.get("X-PyDrop-Local") != "1":
            raise web.HTTPForbidden()
        data = await request.json()
        self.queue_share(data.get("paths") or [])
        return web.json_response({"ok": True})

    def queue_share(self, paths):
        known = {i["path"] for i in self.pending_share}
        for raw in paths:
            d = describe_path(raw)
            if d and d["path"] not in known:
                self.pending_share.append(d)
                known.add(d["path"])
        # Plusieurs fichiers sélectionnés = plusieurs appels rapprochés : on les regroupe
        if self.share_timer:
            self.share_timer.cancel()
        self.share_timer = self.loop.call_later(0.5, self.flush_share)

    def flush_share(self):
        if not self.pending_share or not self.ui_sockets:
            return  # sinon, transmis à l'ouverture de l'interface
        self.ui_send({"type": "share", "items": self.pending_share})
        self.pending_share = []
        self.bring_to_front()

    def bring_to_front(self):
        window = self.window
        if not window:
            return

        def show():
            try:
                window.restore()
                window.on_top = True
                time.sleep(0.3)
                window.on_top = False
            except Exception as e:
                print("bring_to_front:", e)

        threading.Thread(target=show, daemon=True).start()

    async def h_stage(self, request):
        # Fichier envoyé par l'interface locale vers un téléphone : on le prépare puis on le propose
        if not is_local_ui(request):
            raise web.HTTPForbidden()
        q = request.query
        to = q.get("to", "")
        if to not in self.clients or to not in self.sessions:
            return web.json_response({"error": "Téléphone non connecté"}, status=400)
        name = safe_name(q.get("name", "fichier"))
        fid = uuid.uuid4().hex
        path = self.stage_dir / fid
        size = 0
        if not has_room(self.stage_dir, int(q.get("size") or 0)):
            return web.json_response({"error": "Espace disque insuffisant sur ce PC"}, status=507)
        run = self.loop.run_in_executor
        try:
            f = await run(None, open, path, "wb")
            try:
                async for chunk in request.content.iter_chunked(1 << 20):
                    await run(None, f.write, chunk)
                    size += len(chunk)
            finally:
                await run(None, f.close)
        except BaseException as e:
            path.unlink(missing_ok=True)
            if is_disk_full(e):
                return web.json_response({"error": "Espace disque insuffisant sur ce PC"}, status=507)
            raise
        self.staged[fid] = {"path": str(path), "name": name, "size": size, "to": to,
                            "ts": time.time(), "tid": q.get("tid") or fid, "own": True}
        await self.send_to(to, {"type": "file", "id": fid, "name": name, "size": size,
                                "url": f"/api/dl/{fid}", "from": self.public_info()})
        return web.json_response({"ok": True, "id": fid})

    async def h_download(self, request):
        fid = request.match_info["fid"]
        s = self.staged.get(fid)
        if not s or self.sessions.get(s["to"]) != request.query.get("token"):
            raise web.HTTPNotFound()
        tid, phone = s["tid"], s["to"]

        def notify(state, sent):
            if fid not in self.staged:
                return  # annulé
            if state == "done":
                self.ui_send({"type": "tx_done", "tid": tid})
            else:
                self.ui_send({"type": "tx_progress", "tid": tid, "sent": sent, "size": s["size"],
                              "paused": state == "paused"})
            # Le téléphone suit aussi l'avancement (utile quand c'est son navigateur qui télécharge)
            asyncio.ensure_future(self.send_to(phone, {"type": "dl_status", "id": fid, "state": state,
                                                       "sent": sent, "size": s["size"]}))

        return await self.stream_file(request, s["path"], s["name"], s["size"], fid, notify)

    # -- explorateur de fichiers (appareils connectés uniquement) ----------------

    def check_browse(self, request):
        q = request.query
        src, token = q.get("from", ""), q.get("token", "")
        if not token or self.sessions.get(src) != token:
            raise web.HTTPForbidden(text="Connexion non autorisée")
        if not self.cfg.allow_browse:
            raise web.HTTPForbidden(text="L'explorateur est désactivé sur cet ordinateur")
        return self.device_info(src) or {"id": src, "name": "Appareil"}

    @staticmethod
    def fs_roots():
        home = Path.home()
        roots = []
        for label, names in (("Bureau", ("Desktop", "Bureau")), ("Documents", ("Documents",)),
                             ("Téléchargements", ("Downloads", "Téléchargements")),
                             ("Images", ("Pictures", "Images")), ("Vidéos", ("Videos", "Vidéos")),
                             ("Musique", ("Music", "Musique"))):
            for n in names:
                p = home / n
                if p.is_dir():
                    roots.append({"name": label, "path": str(p), "dir": True, "kind": "place"})
                    break
        if sys.platform.startswith("win"):
            import string
            for letter in string.ascii_uppercase:
                d = f"{letter}:\\"
                if os.path.exists(d):
                    try:
                        usage = shutil.disk_usage(d)
                        free, total = usage.free, usage.total
                    except OSError:
                        free = total = 0
                    roots.append({"name": f"Disque {letter}:", "path": d, "dir": True, "kind": "drive",
                                  "free": free, "total": total})
        else:
            roots.append({"name": "Racine", "path": "/", "dir": True, "kind": "drive"})
        return roots

    async def h_fs_list(self, request):
        self.check_browse(request)
        raw = request.query.get("path", "")
        if not raw:
            return web.json_response({"path": "", "parent": None, "entries": self.fs_roots()})
        path = Path(os.path.abspath(raw))
        if not path.is_dir():
            return web.json_response({"error": "Dossier introuvable"}, status=404)

        def scan():
            out = []
            try:
                it = os.scandir(path)
            except OSError as e:
                return None, str(e)
            with it:
                for e in it:
                    try:
                        if e.name.startswith((".", "$")) or e.name in ("desktop.ini", "Thumbs.db"):
                            continue
                        st = e.stat()
                        attrs = getattr(st, "st_file_attributes", 0)
                        if attrs & 0x2 or attrs & 0x4:  # caché / système
                            continue
                        is_dir = e.is_dir()
                        out.append({"name": e.name, "path": e.path, "dir": is_dir,
                                    "size": 0 if is_dir else st.st_size, "mtime": st.st_mtime})
                    except OSError:
                        continue
                    if len(out) >= 3000:
                        break
            out.sort(key=lambda x: (not x["dir"], x["name"].lower()))
            return out, None

        entries, err = await self.loop.run_in_executor(None, scan)
        if entries is None:
            return web.json_response({"error": "Accès refusé"}, status=403)
        parent = str(path.parent) if path.parent != path else ""
        return web.json_response({"path": str(path), "name": path.name or str(path),
                                  "parent": parent, "entries": entries})

    async def h_fs_get(self, request):
        info = self.check_browse(request)
        path = Path(os.path.abspath(request.query.get("path", "")))
        if not path.is_file():
            raise web.HTTPNotFound(text="Fichier introuvable")
        dl_id = request.query.get("id", "")[:64] or uuid.uuid4().hex
        src = info["id"]
        if dl_id in self.browse_cancelled:
            return web.Response(status=410, text="Téléchargement annulé")
        size = path.stat().st_size
        if "Range" not in request.headers:
            self.ui_send({"type": "browse_download", "peer": info.get("name"), "name": path.name})

        def notify(state, sent):
            if dl_id in self.browse_cancelled:
                return
            # Le PC affiche ce que le téléphone prend…
            self.ui_send({"type": "browse_progress", "tid": dl_id, "name": path.name, "size": size,
                          "sent": sent, "state": state, "peer": info.get("name"), "peer_id": src,
                          "peer_type": info.get("type")})
            # …et le téléphone reçoit aussi la progression (son navigateur ne la donne pas à la page)
            asyncio.ensure_future(self.send_to(src, {"type": "dl_status", "id": dl_id, "state": state,
                                                     "sent": sent, "size": size}))

        self.browse_owner[dl_id] = src
        return await self.stream_file(request, path, path.name, size, dl_id, notify)

    def cancel_browse(self, dl_id):
        self.browse_cancelled.add(dl_id)
        task = self.dl_tasks.get(dl_id)
        if task and not task.done():
            task.cancel()
        self.ui_send({"type": "tx_cancelled", "tid": dl_id})
        owner = self.browse_owner.pop(dl_id, None)
        if owner:
            asyncio.ensure_future(self.send_to(owner, {"type": "file_cancel", "id": dl_id}))

    async def sha_of(self, path):
        st = os.stat(path)
        key = (str(path), st.st_size, st.st_mtime)
        if key not in self.sha_cache:
            self.sha_cache[key] = await self.loop.run_in_executor(None, file_sha256, path)
        return self.sha_cache[key]

    async def h_dl_sha(self, request):
        s = self.staged.get(request.match_info["fid"])
        if not s or self.sessions.get(s["to"]) != request.query.get("token"):
            raise web.HTTPNotFound()
        return web.json_response({"sha256": await self.sha_of(s["path"])})

    async def h_fs_sha(self, request):
        self.check_browse(request)
        path = Path(os.path.abspath(request.query.get("path", "")))
        if not path.is_file():
            raise web.HTTPNotFound()
        return web.json_response({"sha256": await self.sha_of(path)})

    async def h_qr(self, request):
        import qrcode
        import qrcode.image.svg
        url = request.query.get("url") or (self.phone_urls() or [f"http://127.0.0.1:{self.port}/"])[0]
        img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, border=1)
        svg = img.to_string(encoding="unicode")
        return web.Response(text=svg, content_type="image/svg+xml", headers={"Cache-Control": "no-cache, no-store"})

    async def h_ws_client(self, request):
        """WebSocket d'un téléphone (page mobile)."""
        q = request.query
        cid = q.get("id", "")[:64]
        if not cid:
            raise web.HTTPBadRequest()
        ws = web.WebSocketResponse(heartbeat=45)
        await ws.prepare(request)
        info = {"id": cid, "name": q.get("name", "Téléphone")[:60], "type": "mobile",
                "os": q.get("os", "")[:20], "ip": request.remote, "port": 0}
        old = self.clients.get(cid)
        if old and not old["ws"].closed:
            await old["ws"].close()
        self.clients[cid] = {"info": info, "ws": ws}
        self.dev_names[cid] = info["name"]
        # Le téléphone présente son jeton (rechargement de page) : on garde la session si valide
        token = q.get("token")
        if token and self.sessions.get(cid) != token:
            token = None
        await ws.send_json({"type": "hello", "node": self.public_info(),
                            "connected": bool(token)})
        self.push_devices()
        try:
            async for m in ws:
                if m.type != WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(m.data)
                except ValueError:
                    continue
                if data.get("type") == "rename":
                    info["name"] = str(data.get("name", ""))[:60] or info["name"]
                    self.push_devices()
                elif data.get("type") == "ping":
                    await ws.send_json({"type": "pong"})
                else:
                    await self.on_peer_msg(info, data)
        finally:
            if self.clients.get(cid, {}).get("ws") is ws:
                del self.clients[cid]
                self.pending_out.pop(cid, None)
                for req_id, r in list(self.pending_in.items()):
                    if r["from"]["id"] == cid:
                        del self.pending_in[req_id]
                        self.ui_send({"type": "incoming_cancel", "req_id": req_id})
                self.push_devices()
        return ws

    async def h_ws_ui(self, request):
        """WebSocket de l'interface desktop locale."""
        if not is_local_ui(request):
            raise web.HTTPForbidden()
        ws = web.WebSocketResponse()  # connexion locale : pas de contrôle de présence
        await ws.prepare(request)
        self.ui_sockets.add(ws)
        share_sent = bool(self.pending_share)
        await ws.send_json({
            "type": "init", "me": self.public_info(), "devices": self.devices(),
            "download_dir": str(self.cfg.download_dir), "history": self.history[:50],
            "urls": self.phone_urls(), "allow_browse": self.cfg.allow_browse,
            "shell_integration": self.cfg.shell_integration, "shell_available": self.shell_available(),
            "video_cookies": self.cfg.video_cookies, "mirror_audio": self.cfg.mirror_audio,
            "clip_auto": self.cfg.clip_auto, "allow_remote": self.cfg.allow_remote, "clips": self.clips[:20],
            "notif_toast": self.cfg.notif_toast, "notif_muted": self.cfg.notif_muted, "notifs": self.notifs[:50],
            "native_window": bool(self.window),
            "share": self.pending_share,
            "incoming": [{"req_id": k, "from": v["from"]} for k, v in self.pending_in.items()],
        })
        if share_sent:
            self.pending_share = []
            self.bring_to_front()
        try:
            async for m in ws:
                if m.type == WSMsgType.TEXT:
                    try:
                        await self.on_ui_cmd(ws, json.loads(m.data))
                    except Exception as e:
                        print("ui cmd error:", e)
        finally:
            self.ui_sockets.discard(ws)
        return ws

    async def on_ui_cmd(self, ws, cmd):
        t = cmd.get("type")
        dev = cmd.get("id")
        if t == "connect":
            req_id = uuid.uuid4().hex
            self.pending_out[dev] = req_id
            self.push_devices()
            if not await self.send_to(dev, {"type": "request", "req_id": req_id}):
                self.pending_out.pop(dev, None)
                self.ui_send({"type": "error", "message": "Appareil injoignable"})
                self.push_devices()
        elif t == "cancel":
            req_id = self.pending_out.pop(dev, None)
            if req_id:
                await self.send_to(dev, {"type": "cancel", "req_id": req_id})
            self.push_devices()
        elif t == "respond":
            r = self.pending_in.pop(cmd.get("req_id"), None)
            if not r:
                return
            src = r["from"]
            token = secrets.token_urlsafe(18) if cmd.get("accept") else None
            if token:
                self.sessions[src["id"]] = token
            await self.send_to(src["id"], {"type": "response", "req_id": cmd["req_id"],
                                           "accepted": bool(token), "token": token})
            self.push_devices()
        elif t == "disconnect":
            if self.sessions.pop(dev, None):
                await self.send_to(dev, {"type": "disconnect"})
            self.push_devices()
        elif t == "rename":
            name = str(cmd.get("name", "")).strip()[:40]
            if name:
                self.cfg.name = name
                self.cfg.save()
                self.ui_send({"type": "me", "me": self.public_info()})
                if self.discovery:
                    self.discovery.announce()
        elif t == "add_peer":
            ok = await self.add_static_peer(cmd.get("address", ""))
            if not ok:
                self.ui_send({"type": "error", "message": "Aucun PyDrop trouvé à cette adresse"})
        elif t == "open_folder":
            self.cfg.download_dir.mkdir(parents=True, exist_ok=True)
            open_path(self.cfg.download_dir)
        elif t == "open_file":
            p = Path(cmd.get("path", ""))
            if p.exists() and self.cfg.download_dir in p.parents:
                open_path(p, select=bool(cmd.get("select")))
        elif t == "choose_folder":
            await self.choose_folder()
        elif t == "sent":
            self.add_history({"tid": cmd.get("tid"), "name": cmd.get("name"), "size": cmd.get("size"),
                              "to": cmd.get("to"), "to_type": cmd.get("to_type"), "ts": time.time(),
                              "dir": "out"})
        elif t == "cancel_rx":
            self.cancel_rx(str(cmd.get("tid", "")))
        elif t == "cancel_tx":
            tid = cmd.get("tid")
            for fid, s in list(self.staged.items()):
                if s["tid"] == tid:
                    self.cancel_staged(fid)
            if tid in self.browse_owner or tid in self.dl_tasks:
                self.cancel_browse(tid)
            self.cancel_out(tid)
            self.cancel_fetch(tid)
        elif t == "send_paths":
            self.send_paths(dev, cmd.get("paths") or [])
        elif t == "pick_files":
            items = [describe_path(p) for p in await self.files_dialog()]
            items = [i for i in items if i]
            if items:
                self.ui_send({"type": "picked", "id": dev, "items": items})
        elif t == "pick_folder":
            folder = await self.folder_dialog(str(Path.home()))
            d = describe_path(folder) if folder else None
            if d:
                self.ui_send({"type": "picked", "id": dev, "items": [d]})
        elif t == "mirror_start":
            if "mode" in cmd or "record" in cmd:
                self.set_mirror_opts(dev, cmd.get("mode"), cmd.get("record"))
            asyncio.ensure_future(self.mirror_start(dev))
        elif t == "clip_send":
            ids = [i for i in (cmd.get("ids") or [dev]) if i]
            await self.send_clip(ids, cmd.get("text"))
        elif t == "clip_copy":
            if winctl and isinstance(cmd.get("text"), str):
                winctl.set_clipboard(cmd["text"])
                self.clip_seq = winctl.clipboard_seq()
        elif t == "open_url":
            url = str(cmd.get("url", ""))
            if re.fullmatch(r"https?://\S{1,2000}", url):
                webbrowser.open(url)
        elif t == "clip_auto":
            self.cfg.clip_auto = bool(cmd.get("value"))
            self.cfg.save()
            self.clip_seq = winctl.clipboard_seq() if winctl else 0
            self.ui_send({"type": "clip_auto", "value": self.cfg.clip_auto})
        elif t == "allow_remote":
            self.cfg.allow_remote = bool(cmd.get("value"))
            self.cfg.save()
            self.ui_send({"type": "allow_remote", "value": self.cfg.allow_remote})
        elif t == "notif_toast":
            self.cfg.notif_toast = bool(cmd.get("value"))
            self.cfg.save()
            self.ui_send({"type": "notif_toast", "value": self.cfg.notif_toast})
        elif t == "notif_mute":
            pkg, app = str(cmd.get("pkg", ""))[:200], str(cmd.get("app", ""))[:80]
            if pkg and not any(m["pkg"] == pkg for m in self.cfg.notif_muted):
                self.cfg.notif_muted.append({"pkg": pkg, "app": app or pkg})
                self.cfg.save()
            self.notifs = [n for n in self.notifs if n["pkg"] != pkg]
            self.ui_send({"type": "notif_muted", "value": self.cfg.notif_muted, "notifs": self.notifs[:50]})
        elif t == "notif_unmute":
            pkg = cmd.get("pkg")
            self.cfg.notif_muted = [m for m in self.cfg.notif_muted if pkg and m["pkg"] != pkg]
            self.cfg.save()
            self.ui_send({"type": "notif_muted", "value": self.cfg.notif_muted, "notifs": self.notifs[:50]})
        elif t == "notif_clear":
            self.notifs = []
        elif t == "notif_reply":
            nid = cmd.get("id")
            text = str(cmd.get("text", "")).strip()
            item = next((n for n in self.notifs if n.get("id") == nid), None)
            if item and text and item.get("notif_key"):
                dev = item.get("dev")
                payload = {"command": "reply", "key": item["notif_key"], "text": text}
                q = self.dev_commands.setdefault(dev, asyncio.Queue())
                await q.put(payload)
                await self.send_to(dev, {"type": "notif_reply", **payload})
                item["reply_sent"] = text
                self.ui_send({"type": "notif_reply_sent", "id": nid, "text": text})
        elif t == "mirror_pair":
            asyncio.ensure_future(self.mirror_pair(dev, str(cmd.get("code", "")), str(cmd.get("port", ""))))
        elif t == "mirror_audio":
            if cmd.get("value") in ("phone", "pc", "both"):
                self.cfg.mirror_audio = cmd["value"]
                self.cfg.save()
                self.ui_send({"type": "mirror_audio", "value": self.cfg.mirror_audio})
        elif t == "mirror_stop":
            proc = self.mirrors.get(dev)
            if proc and proc.returncode is None:
                proc.terminate()
        elif t == "video_cookies":
            value = cmd.get("value") or ""
            if value in ("", "firefox", "edge", "chrome", "brave"):
                self.cfg.video_cookies = value
                self.cfg.save()
                self.ui_send({"type": "video_cookies", "value": value})
        elif t == "shell_integration":
            await self.set_shell_integration(bool(cmd.get("value")))
        elif t == "allow_browse":
            self.cfg.allow_browse = bool(cmd.get("value"))
            self.cfg.save()
            self.ui_send({"type": "allow_browse", "value": self.cfg.allow_browse})
        elif t == "clear_history":
            self.history = []
            self.cfg.save_history(self.history)

    async def folder_dialog(self, directory):
        if not self.window:
            self.ui_send({"type": "error", "message": "Disponible uniquement dans l'application"})
            return None
        import webview
        dialog = getattr(webview, "FileDialog", None)
        kind = dialog.FOLDER if dialog else webview.FOLDER_DIALOG
        result = await self.loop.run_in_executor(
            None, lambda: self.window.create_file_dialog(kind, directory=directory))
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else result

    async def files_dialog(self):
        if not self.window:
            return []
        import webview
        dialog = getattr(webview, "FileDialog", None)
        kind = dialog.OPEN if dialog else webview.OPEN_DIALOG
        result = await self.loop.run_in_executor(
            None, lambda: self.window.create_file_dialog(kind, allow_multiple=True))
        return list(result or [])

    async def choose_folder(self):
        folder = await self.folder_dialog(str(self.cfg.download_dir))
        if folder:
            self.cfg.download_dir = Path(folder)
            self.cfg.save()
            self.ui_send({"type": "download_dir", "path": str(self.cfg.download_dir)})

    def on_window_drop(self, event):
        # Éléments déposés : seul pywebview connaît leur chemin complet
        paths = [f.get("pywebviewFullPath") for f in (event.get("dataTransfer") or {}).get("files", [])]
        items = [d for d in (describe_path(p) for p in paths if p) if d]
        if items:
            self.loop.call_soon_threadsafe(lambda: self.ui_send({"type": "dropped_paths", "items": items}))

    @staticmethod
    def shell_available():
        return sys.platform.startswith("win") and getattr(sys, "frozen", False)

    async def apply_shell(self):
        if not self.shell_available():
            return
        if self.cfg.shell_integration:
            # Le port d'abord : le relais peut servir sans attendre la fin de l'installation
            shell_dir().mkdir(parents=True, exist_ok=True)
            (shell_dir() / "port.txt").write_text(str(self.port), "utf-8")
            await self.loop.run_in_executor(None, install_shell, sys.executable)
        else:
            await self.loop.run_in_executor(None, uninstall_shell)

    async def set_shell_integration(self, value):
        self.cfg.shell_integration = value
        self.cfg.save()
        try:
            await self.apply_shell()
        except Exception as e:
            self.ui_send({"type": "error", "message": f"Menu Windows : {e}"})
        self.ui_send({"type": "shell_integration", "value": value})

    # -- fichiers statiques ----------------------------------------------------

    async def h_app(self, request):
        if not is_local(request):
            raise web.HTTPFound("/")
        return web.FileResponse(UI_DIR / "desktop.html", headers={"Cache-Control": "no-store"})

    async def h_static(self, request):
        rel = request.match_info.get("path") or "index.html"
        target = (MOB_DIR / rel).resolve()
        if MOB_DIR.resolve() not in target.parents and target != MOB_DIR.resolve():
            raise web.HTTPNotFound()
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            raise web.HTTPNotFound()
        headers = {"Cache-Control": "no-store"} if target.suffix == ".html" else {}
        return web.FileResponse(target, headers=headers)

    # -- démarrage / arrêt -------------------------------------------------------

    def build_app(self):
        app = web.Application(middlewares=[cors_middleware], client_max_size=4 * 1024 ** 2)
        app.router.add_get("/app", self.h_app)
        app.router.add_get("/api/info", self.h_info)
        app.router.add_get("/api/peers", self.h_peers)
        app.router.add_post("/api/msg", self.h_msg)
        app.router.add_post("/api/notify", self.h_notify)
        app.router.add_get("/api/notif/poll", self.h_notif_poll)
        app.router.add_post("/api/upload", self.h_upload)
        app.router.add_post("/local/send", self.h_local_send)
        app.router.add_get("/api/upload/status", self.h_upload_status)
        app.router.add_post("/api/upload/cancel", self.h_upload_cancel)
        app.router.add_post("/api/stage", self.h_stage)
        app.router.add_get("/api/dl/{fid}", self.h_download)
        app.router.add_get("/api/qr.svg", self.h_qr)
        app.router.add_get("/api/fs/list", self.h_fs_list)
        app.router.add_get("/api/fs/get", self.h_fs_get)
        app.router.add_get("/api/fs/sha256", self.h_fs_sha)
        app.router.add_get("/api/dl/{fid}/sha256", self.h_dl_sha)
        app.router.add_get("/ws/ui", self.h_ws_ui)
        app.router.add_get("/ws/client", self.h_ws_client)
        app.router.add_route("OPTIONS", "/api/{tail:.*}", lambda r: web.Response())
        app.router.add_get("/{path:.*}", self.h_static)
        return app

    async def start(self):
        self.loop = asyncio.get_running_loop()
        self.http = ClientSession(timeout=ClientTimeout(total=8))
        runner = web.AppRunner(self.build_app(), access_log=None)
        await runner.setup()
        last_err = None
        for port in range(self.port, self.port + 20):
            try:
                site = web.TCPSite(runner, "0.0.0.0", port)
                await site.start()
                self.port = port
                break
            except OSError as e:
                last_err = e
        else:
            raise last_err
        try:
            _, self.discovery = await self.loop.create_datagram_endpoint(
                lambda: Discovery(self), sock=make_discovery_socket())
        except OSError as e:
            print("Découverte UDP indisponible :", e)
        # Fichiers partiels abandonnés depuis plus de 2 jours
        for p in self.cfg.download_dir.glob(".pydrop-*.part"):
            try:
                if time.time() - p.stat().st_mtime > 48 * 3600:
                    p.unlink()
            except OSError:
                pass
        asyncio.ensure_future(self.announcer())
        asyncio.ensure_future(self.housekeeping())
        asyncio.ensure_future(self.static_poller())
        asyncio.ensure_future(self.clip_watcher())
        if not self.profile:
            asyncio.ensure_future(self.safe_apply_shell())
        print(f"PyDrop « {self.cfg.name} » prêt sur le port {self.port}")
        for u in self.phone_urls():
            print("  Téléphone :", u)

    async def safe_apply_shell(self):
        try:
            await self.apply_shell()
        except Exception as e:
            print("Menu Windows indisponible :", e)

    async def shutdown(self):
        if getattr(self, "adb_used", False):
            # Le service adb démarré pour l'affichage du téléphone ne doit pas rester en tâche de fond
            try:
                await asyncio.wait_for(self.adb("kill-server", timeout=5), 6)
            except Exception:
                pass
        if not self.profile and self.shell_available():
            (shell_dir() / "port.txt").unlink(missing_ok=True)
        for dev_id in list(self.sessions):
            try:
                await asyncio.wait_for(self.send_to(dev_id, {"type": "disconnect"}), 1.5)
            except Exception:
                pass
        if self.discovery:
            self.discovery.announce(bye=True)
        shutil.rmtree(self.stage_dir, ignore_errors=True)


# ----------------------------------------------------------------------------
# Point d'entrée
# ----------------------------------------------------------------------------

_boot_splash = None


def start_boot_splash():
    """Fenêtre d'accueil animée, visible dès le lancement pendant que la fenêtre principale se prépare."""
    global _boot_splash
    try:
        from boot_splash import BootSplash
        _boot_splash = BootSplash(UI_DIR / "splash")
        _boot_splash.start()
    except Exception as e:
        print("Fenêtre d'accueil indisponible :", repr(e))


def close_boot_splash(*_):
    if _boot_splash:
        _boot_splash.close()


def boot_splash_text(text):
    if _boot_splash:
        _boot_splash.text(text)


def loading_html() -> str:
    """Écran de chargement montré par la fenêtre pendant que le moteur démarre."""
    import base64
    logo = base64.b64encode((MOB_DIR / "SVG Mobile" / "logo.png").read_bytes()).decode()
    script = (MOB_DIR / "splash.js").read_text("utf-8")
    return ("<!DOCTYPE html><html><head><meta charset='utf-8'><title>PyDrop</title></head>"
            "<body style='margin:0;background:#070b16'>"
            f"<script>window.PYSPLASH_LOGO='data:image/png;base64,{logo}';</script>"
            f"<script>{script}</script><script>PySplash.step('Démarrage du moteur…')</script></body></html>")


def already_running(cfg: Config, port: int) -> bool:
    """Si PyDrop tourne déjà avec cette identité, on n'en lance pas un second."""
    import urllib.request
    for p in range(port, port + 20):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{p}/api/info", timeout=0.4) as r:
                if json.loads(r.read()).get("id") == cfg.id:
                    print("PyDrop est déjà ouvert sur le port", p)
                    return True
        except Exception:
            continue
    return False


def setup_log(cfg_dir: Path):
    """L'exe n'a pas de console : tout est écrit dans ~/.pydrop/pydrop.log pour comprendre un plantage."""
    path = cfg_dir / "pydrop.log"
    try:
        if path.exists() and path.stat().st_size > 2 * 1024 * 1024:
            path.replace(cfg_dir / "pydrop.old.log")
        log = open(path, "a", encoding="utf-8", buffering=1)
    except OSError:
        return None
    sys.stdout = sys.stderr = log
    faulthandler.enable(log)
    print(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} démarrage, {platform.platform()}, "
          f"Python {platform.python_version()}")
    return log


def fatal_box(message):
    print("ERREUR FATALE :", message)
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, str(message), "PyDrop", 0x10)
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="PyDrop — partage de fichiers en réseau local")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PYDROP_PORT", DEFAULT_PORT)))
    parser.add_argument("--profile", default=os.environ.get("PYDROP_PROFILE"),
                        help="profil séparé (pour lancer plusieurs instances sur un même PC)")
    parser.add_argument("--browser", action="store_true", help="ouvrir dans le navigateur")
    parser.add_argument("--headless", action="store_true", help="aucune interface")
    parser.add_argument("--uninstall-shell", action="store_true",
                        help="retire le menu « Envoyer avec PyDrop » (utilisé par le désinstalleur)")
    args = parser.parse_args()
    if args.uninstall_shell:
        # Le menu peut appartenir à une autre copie de PyDrop sur ce PC : on n'y touche alors pas
        owner = shell_dir() / "main.txt"
        mine = os.path.normcase(os.path.abspath(sys.executable))
        try:
            owned = os.path.normcase(os.path.abspath(owner.read_text("utf-8").strip())) == mine
        except OSError:
            owned = True
        if sys.platform.startswith("win") and owned:
            uninstall_shell()
            shutil.rmtree(shell_dir(), ignore_errors=True)
        return

    cfg = Config(args.profile)
    if winctl:
        winctl.set_app_id()
    if getattr(sys, "frozen", False):
        setup_log(cfg.path.parent)
    if not (args.browser or args.headless):
        start_boot_splash()
    if already_running(cfg, args.port):
        close_boot_splash()
        return
    node = Node(cfg, args.port, args.profile)
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    errors = []

    def run_loop():
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(node.start())
        except Exception as e:
            errors.append(e)
            ready.set()
            return
        ready.set()
        loop.set_exception_handler(lambda _, ctx: print("Erreur du moteur :", ctx.get("message"), ctx.get("exception")))
        loop.run_forever()

    threading.Thread(target=run_loop, daemon=True).start()

    use_window = not (args.browser or args.headless)
    if use_window:
        try:
            import webview
        except ImportError:
            print("pywebview absent : ouverture dans le navigateur (pip install pywebview)")
            use_window = False

    if use_window:
        # La fenêtre s'ouvre tout de suite sur l'écran de chargement, le moteur démarre derrière
        try:
            window = webview.create_window("PyDrop", html=loading_html(), width=1220, height=780,
                                           min_size=(940, 620), background_color="#070B16")
            node.window = window

            def bind_drop():
                try:
                    from webview.dom import DOMEventHandler
                    window.dom.document.events.drop += DOMEventHandler(node.on_window_drop, False, False)
                except Exception as e:
                    print("Dépôt de dossiers indisponible :", e)

            def when_ready():
                boot_splash_text("Démarrage du moteur…")
                ready.wait()
                if errors:
                    fatal_box(f"Impossible de démarrer PyDrop :\n{errors[0]}")
                    window.destroy()
                    return
                window.events.loaded += bind_drop
                window.load_url(f"http://127.0.0.1:{node.port}/app")

            # La fenêtre a affiché son propre écran de chargement : l'accueil s'efface en fondu
            window.events.loaded += close_boot_splash
            webview.start(when_ready)
            close_boot_splash()
            if not errors:
                fut = asyncio.run_coroutine_threadsafe(node.shutdown(), loop)
                try:
                    fut.result(timeout=3)
                except Exception:
                    pass
            return
        except Exception as e:
            # Pas de composant WebView2 sur ce PC, par exemple : on continue dans le navigateur
            print("Fenêtre indisponible :", repr(e))
            node.window = None

    ready.wait()
    close_boot_splash()
    if errors:
        fatal_box(f"Impossible de démarrer PyDrop :\n{errors[0]}")
        sys.exit(1)

    url = f"http://127.0.0.1:{node.port}/app"

    def stop():
        fut = asyncio.run_coroutine_threadsafe(node.shutdown(), loop)
        try:
            fut.result(timeout=3)
        except Exception:
            pass

    if not args.headless:
        webbrowser.open(url)
    print("Ctrl+C pour quitter")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop()


if __name__ == "__main__":
    main()
