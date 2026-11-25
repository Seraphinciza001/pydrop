import socket
import os
import sys
from flask import Flask, send_file, send_from_directory, request, jsonify, render_template_string, redirect, url_for, Response, stream_with_context
from werkzeug.utils import secure_filename
import string
import math
import datetime
from urllib.parse import quote
import logging
import warnings
import webbrowser
import io
import base64
import uuid
import mimetypes
import time
import threading
import shutil

# --- MODULES OPTIONNELS AVEC REPLI AUTOMATIQUE ---
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False

# --- CONFIGURATION DES CHEMINS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()

HOST = '0.0.0.0'
PORT = int(os.environ.get('PORT', 5000))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'received_files') 
TEMP_TRANSFER_FOLDER = os.path.join(BASE_DIR, 'temp_transfer')
ASSETS_FOLDER = os.path.join(BASE_DIR, 'assets')
STATIC_FOLDER = os.path.join(BASE_DIR, 'static')
SVG_MOBILE_FOLDER = os.path.join(BASE_DIR, 'SVG Mobile')

for folder in [UPLOAD_FOLDER, TEMP_TRANSFER_FOLDER, ASSETS_FOLDER, STATIC_FOLDER, SVG_MOBILE_FOLDER]:
    if not os.path.exists(folder):
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception:
            pass

app = Flask(__name__, static_folder=STATIC_FOLDER)

# Dictionnaire de secours d'icônes SVG intégrées pour garantir 0 icône cassée
FALLBACK_SVGS = {
    'folder': '''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg>''',
    'folder-open': '''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path><line x1="2" y1="12" x2="22" y2="12"></line></svg>''',
    'hard-drive': '''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="12" x2="2" y2="12"></line><path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"></path><line x1="6" y1="16" x2="6.01" y2="16"></line><line x1="14" y1="16" x2="14.01" y2="16"></line></svg>''',
    'arrow-up': '''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="19" x2="12" y2="5"></line><polyline points="5 12 12 5 19 12"></polyline></svg>''',
    'file': '''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path><polyline points="13 2 13 9 20 9"></polyline></svg>''',
    'search': '''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>''',
    'upload': '''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>''',
    'download': '''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>''',
    'trash-2': '''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line></svg>''',
    'qr-code': '''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>''',
    'refresh-cw': '''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>''',
    'check-circle': '''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#10b981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>''',
    'x': '''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>''',
    'pie-chart': '''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21.21 15.89A10 10 0 1 1 8 2.83"></path><path d="M22 12A10 10 0 0 0 12 2v10z"></path></svg>''',
    'disc': '''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><circle cx="12" cy="12" r="3"></circle></svg>'''
}

def find_icon_path(filename):
    """Recherche un fichier d'icône dans tous les répertoires possibles du projet."""
    candidates = [filename]
    if not filename.endswith('.svg') and '.' not in filename:
        candidates.append(filename + '.svg')
    
    search_dirs = [
        os.path.join(BASE_DIR, 'SVG Mobile'),
        os.path.join(BASE_DIR, 'static', 'icons'),
        os.path.join(BASE_DIR, 'assets', 'icons'),
        os.path.join(BASE_DIR, 'static'),
        os.path.join(BASE_DIR, 'assets'),
        os.path.join(os.getcwd(), 'SVG Mobile'),
        os.path.join(os.getcwd(), 'static', 'icons'),
        os.path.join(os.getcwd(), 'assets', 'icons'),
        os.path.join(os.getcwd(), 'static'),
        os.path.join(os.getcwd(), 'assets')
    ]
    
    for c in candidates:
        for sdir in search_dirs:
            if os.path.exists(sdir):
                full_path = os.path.join(sdir, c)
                if os.path.exists(full_path) and os.path.isfile(full_path):
                    return sdir, c
    return None, None

@app.route('/favicon.ico')
def favicon():
    """Sert l'icône de l'application PyDrop comme favicon."""
    sdir, fname = find_icon_path('pydrop1.png')
    if sdir and fname:
        return send_from_directory(sdir, fname, mimetype='image/png')
    return ('', 204)

@app.route('/static/icons/<path:filename>')
@app.route('/icons/<path:filename>')
@app.route('/assets/icons/<path:filename>')
@app.route('/SVG Mobile/<path:filename>')
@app.route('/svg_mobile/<path:filename>')
def serve_all_icons(filename):
    """Sert n'importe quelle icône SVG avec gestion multi-dossiers et fallback automatique."""
    clean_name = os.path.basename(filename)
    sdir, fname = find_icon_path(clean_name)
    
    if sdir and fname:
        mimetype = 'image/svg+xml' if fname.endswith('.svg') else ('image/png' if fname.endswith('.png') else 'application/octet-stream')
        resp = send_from_directory(sdir, fname, mimetype=mimetype)
        resp.headers['Cache-Control'] = 'public, max-age=86400'
        return resp
    
    # Fallback SVG dynamique pour éviter toute image cassée
    key = clean_name.replace('.svg', '').lower()
    svg_content = FALLBACK_SVGS.get(key)
    if not svg_content:
        # SVG générique par défaut
        svg_content = FALLBACK_SVGS.get('file')
    
    response = Response(svg_content, mimetype='image/svg+xml')
    response.headers['Cache-Control'] = 'public, max-age=86400'
    return response

@app.route('/assets/<path:filename>')
@app.route('/static/<path:filename>')
def serve_static_assets(filename):
    """Sert les fichiers statiques et images globales."""
    clean_name = os.path.basename(filename)
    sdir, fname = find_icon_path(filename)
    if not sdir:
        sdir, fname = find_icon_path(clean_name)
        
    if sdir and fname:
        mimetype, _ = mimetypes.guess_type(fname)
        resp = send_from_directory(sdir, fname, mimetype=mimetype or 'application/octet-stream')
        resp.headers['Cache-Control'] = 'public, max-age=86400'
        return resp
    return ('Fichier introuvable', 404)

@app.route('/mobile')
@app.route('/mobile.html')
def serve_mobile_scanner():
    """Sert l'application mobile autonome avec scanner QR et auto-détection du Point d'accès."""
    for base in [BASE_DIR, os.getcwd()]:
        mob_path = os.path.join(base, 'mobile.html')
        if os.path.exists(mob_path):
            return send_from_directory(base, 'mobile.html')
    return ('Page mobile introuvable', 404)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['TEMP_TRANSFER_FOLDER'] = TEMP_TRANSFER_FOLDER

# --- STOCKAGE DES SESSIONS ET TRANSFERTS EN TEMPS RÉEL ---
PENDING_FILES = {}  # {session_id: {'files': [], 'timestamp': '', 'accepted': False, 'completed': False}}

# État de l'appareil connecté
CONNECTED_CLIENT = {
    'connected': False,
    'ip': None,
    'device_name': 'Aucun appareil',
    'device_type': 'mobile',
    'connected_at': 0,
    'last_seen': 0,
    'session_id': None
}

ACTIVE_TRANSFERS = {}  # {transfer_id: {'id': id, 'filename': filename, 'type': 'upload'|'download', 'direction': str, 'size': int, 'formatted_size': str, 'transferred': int, 'speed': float, 'speed_str': str, 'percent': int, 'status': 'running'|'completed'|'error', 'started_at': float, 'icon': str}}
TRANSFER_HISTORY = {
    'received': [],  # Fichiers reçus depuis le client
    'sent': []       # Fichiers téléchargés par le client
}

def parse_device_name(user_agent, client_ip):
    """Déduit un nom d'appareil convivial et élégant à partir du User-Agent."""
    if not user_agent:
        return f"Appareil ({client_ip})"
    ua = user_agent.lower()
    
    if 'iphone' in ua:
        return "iPhone"
    if 'ipad' in ua:
        return "iPad"
    if 'macintosh' in ua or 'mac os' in ua:
        return "MacBook / iMac"
    
    if 'android' in ua:
        # Essai d'extraction de modèle
        import re
        match = re.search(r'\(([^)]+)\)', user_agent)
        if match:
            parts = match.group(1).split(';')
            for part in parts:
                p_clean = part.strip()
                if 'build' in p_clean.lower():
                    dev = p_clean.split('Build')[0].strip()
                    if dev and len(dev) > 2:
                        return dev
                elif any(brand in p_clean.lower() for brand in ['samsung', 'pixel', 'xiaomi', 'redmi', 'oppo', 'vivo', 'huawei', 'oneplus', 'realme', 'motorola', 'sm-', 'moto', 'mi ']):
                    return p_clean
        return "Smartphone Android"
    
    if 'windows' in ua:
        return "PC Windows"
    if 'linux' in ua:
        return "Appareil Linux"
    
    return f"Client ({client_ip})"

def get_all_received_files():
    """Récupère la liste complète des fichiers dans UPLOAD_FOLDER avec leurs métadonnées et icônes."""
    folder = app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER)
    if not os.path.exists(folder):
        return []
    
    files = []
    try:
        for entry in os.scandir(folder):
            if entry.is_file():
                try:
                    stat = entry.stat()
                    size = stat.st_size
                    mtime = stat.st_mtime
                    dt = datetime.datetime.fromtimestamp(mtime)
                    time_str = dt.strftime("%d/%m/%Y %H:%M:%S")
                    icon_name = get_file_icon_name(entry.name)
                    ext = entry.name.split('.')[-1].lower() if '.' in entry.name else ''
                    files.append({
                        'name': entry.name,
                        'size': size,
                        'formatted_size': format_size(size),
                        'timestamp': mtime,
                        'date_str': time_str,
                        'icon': icon_name,
                        'ext': ext.upper() if ext else 'FICHIER',
                        'path': entry.path
                    })
                except Exception:
                    pass
    except Exception:
        pass
    
    # Trier du plus récent au plus ancien
    files.sort(key=lambda x: x['timestamp'], reverse=True)
    return files

# --- FONCTIONS UTILITAIRES ---

def get_all_local_ips():
    """Détecte toutes les adresses IP réelles de la machine (Point d'accès Hotspot, Wi-Fi, Ethernet)."""
    ips = []
    
    # 1. Obtenir les adresses via psutil si présent
    if PSUTIL_AVAILABLE:
        try:
            for iface, addrs in psutil.net_if_addrs().items():
                for addr in addrs:
                    if addr.family == socket.AF_INET and not addr.address.startswith('127.'):
                        if addr.address not in ips:
                            ips.append(addr.address)
        except Exception:
            pass

    # 2. Obtenir via socket.gethostbyname_ex
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if not ip.startswith('127.') and ip not in ips:
                ips.append(ip)
    except Exception:
        pass

    # 3. Tester les passerelles typiques de point d'accès (192.168.137.1 pour Hotspot Windows, 192.168.43.1 pour Android)
    for probe_target in ['192.168.137.1', '192.168.43.1', '192.168.1.1', '192.168.0.1', '10.0.0.1', '8.8.8.8']:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.2)
            s.connect((probe_target, 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith('127.') and ip not in ips:
                ips.append(ip)
        except Exception:
            pass

    # Prioriser : Hotspot Windows (192.168.137.x), Hotspot Mobile (192.168.43.x), LAN Wi-Fi (192.168.x.x)
    def ip_score(ip):
        if ip.startswith('192.168.137.'):
            return 0  # Point d'accès Windows
        if ip.startswith('192.168.43.'):
            return 1  # Point d'accès Android
        if ip.startswith('172.20.10.'):
            return 2  # Partage iOS
        if ip.startswith('192.168.'):
            return 3  # Wi-Fi / Réseau local
        if ip.startswith('10.'):
            return 4
        return 5

    ips.sort(key=ip_score)
    if not ips:
        ips.append('127.0.0.1')
    return ips

def get_local_ip():
    """Renvoie la meilleure IP locale pour la connexion (privilégie le point d'accès)."""
    return get_all_local_ips()[0]

def _print_progress(prefix, transferred, total=None, width=30):
    if total and total > 0:
        frac = transferred / total
        filled = int(width * frac)
        bar = '█' * filled + '-' * (width - filled)
        pct = int(frac * 100)
        line = f"{prefix} |{bar}| {pct:3d}% ({transferred}/{total} bytes)"
    else:
        bar = ('█' * (transferred % (width + 1)))
        line = f"{prefix} {transferred} bytes transferred"
    print('\r' + line, end='', flush=True)

def format_size(size_bytes):
    if size_bytes is None or size_bytes == 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    try:
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 1) 
        return "%s %s" % (s, size_name[i])
    except ValueError:
         return "0 B"

def get_drive_stats(drive_path):
    """Calcule les statistiques d'espace disque avec repli natif sans dépendances externes."""
    try:
        if not os.path.exists(drive_path):
            return {'total': 'N/A', 'free': 'N/A', 'used': 'N/A', 'percent_used': 0}
        
        # Méthode 1 : psutil si disponible
        if PSUTIL_AVAILABLE:
            usage = psutil.disk_usage(drive_path)
            return {
                'total': format_size(usage.total),
                'free': format_size(usage.free),
                'used': format_size(usage.used),
                'percent_used': round(usage.percent)
            }
        
        # Méthode 2 : shutil.disk_usage (standard library Python 3.3+)
        if hasattr(shutil, 'disk_usage'):
            total, used, free = shutil.disk_usage(drive_path)
            pct = round((used / total) * 100) if total > 0 else 0
            return {
                'total': format_size(total),
                'free': format_size(free),
                'used': format_size(used),
                'percent_used': pct
            }

        # Méthode 3 : Windows ctypes GetDiskFreeSpaceExW
        if sys.platform == 'win32':
            import ctypes
            free_bytes = ctypes.c_ulonglong(0)
            total_bytes = ctypes.c_ulonglong(0)
            total_free_bytes = ctypes.c_ulonglong(0)
            ret = ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                ctypes.c_wchar_p(drive_path),
                ctypes.byref(free_bytes),
                ctypes.byref(total_bytes),
                ctypes.byref(total_free_bytes)
            )
            if ret:
                tot = total_bytes.value
                fr = free_bytes.value
                us = tot - fr
                pct = round((us / tot) * 100) if tot > 0 else 0
                return {
                    'total': format_size(tot),
                    'free': format_size(fr),
                    'used': format_size(us),
                    'percent_used': pct
                }

        # Méthode 4 : os.statvfs sur Linux / macOS
        if hasattr(os, 'statvfs'):
            st = os.statvfs(drive_path)
            fr = st.f_bavail * st.f_frsize
            tot = st.f_blocks * st.f_frsize
            us = tot - fr
            pct = round((us / tot) * 100) if tot > 0 else 0
            return {
                'total': format_size(tot),
                'free': format_size(fr),
                'used': format_size(us),
                'percent_used': pct
            }

        return {'total': 'OK', 'free': 'OK', 'used': '0 B', 'percent_used': 0}
    except Exception as e:
        return {'total': 'N/A', 'free': 'N/A', 'used': 'N/A', 'percent_used': 0}

def sanitize_for_template(s):
    try:
        if not isinstance(s, str):
            return s
        return s.encode('utf-8', 'surrogatepass').decode('utf-8', 'replace')
    except Exception:
        try:
            return str(s)
        except Exception:
            return '<unrepresentable>'

def get_file_icon_name(filename):
    if not filename:
        return 'file'
    ext = filename.split('.')[-1].lower() if '.' in filename else ''
    icon_map = {
        'pdf': 'file-pdf',
        'doc': 'file-doc', 'docx': 'file-doc', 'odt': 'file-doc', 'rtf': 'file-doc', 'dot': 'file-doc', 'dotx': 'file-doc',
        'xls': 'file-spreadsheet', 'xlsx': 'file-spreadsheet', 'csv': 'file-spreadsheet', 'ods': 'file-spreadsheet', 'tsv': 'file-spreadsheet', 'xlsm': 'file-spreadsheet',
        'ppt': 'file-presentation', 'pptx': 'file-presentation', 'odp': 'file-presentation', 'pps': 'file-presentation', 'ppsx': 'file-presentation',
        'py': 'file-python', 'pyw': 'file-python', 'ipynb': 'file-python',
        'php': 'file-php',
        'cs': 'file-cs',
        'c': 'file-cpp', 'cpp': 'file-cpp', 'cc': 'file-cpp', 'cxx': 'file-cpp', 'h': 'file-cpp', 'hpp': 'file-cpp',
        'java': 'file-java', 'class': 'file-java', 'jar': 'file-java',
        'js': 'file-js', 'mjs': 'file-js', 'cjs': 'file-js', 'jsx': 'file-js',
        'ts': 'file-ts', 'tsx': 'file-ts',
        'html': 'file-html', 'htm': 'file-html', 'xhtml': 'file-html', 'vue': 'file-html',
        'css': 'file-css', 'scss': 'file-css', 'sass': 'file-css', 'less': 'file-css',
        'json': 'file-json', 'xml': 'file-json', 'yaml': 'file-json', 'yml': 'file-json', 'toml': 'file-json', 'ini': 'file-json', 'env': 'file-json', 'config': 'file-json', 'lock': 'file-json',
        'sql': 'file-sql',
        'sh': 'file-sh', 'bash': 'file-sh', 'zsh': 'file-sh', 'bat': 'file-sh', 'ps1': 'file-sh', 'cmd': 'file-sh',
        'rs': 'file-rs', 'go': 'file-go', 'rb': 'file-rb',
        'swift': 'file-swift', 'kt': 'file-swift', 'kts': 'file-swift',
        'jpg': 'image', 'jpeg': 'image', 'png': 'image', 'gif': 'image', 'webp': 'image', 'svg': 'image', 'bmp': 'image', 'ico': 'image', 'tiff': 'image', 'psd': 'image', 'ai': 'image',
        'mp4': 'video', 'mkv': 'video', 'avi': 'video', 'mov': 'video', 'wmv': 'video', 'webm': 'video', 'm4v': 'video', 'flv': 'video', '3gp': 'video', 'ts': 'video',
        'mp3': 'music', 'wav': 'music', 'flac': 'music', 'aac': 'music', 'ogg': 'music', 'm4a': 'music', 'wma': 'music', 'opus': 'music', 'mid': 'music', 'midi': 'music',
        'zip': 'file-archive', 'rar': 'file-archive', '7z': 'file-archive', 'tar': 'file-archive', 'gz': 'file-archive', 'xz': 'file-archive', 'bz2': 'file-archive', 'tgz': 'file-archive',
        'txt': 'file-text', 'md': 'file-text', 'log': 'file-text',
        'iso': 'disc', 'dmg': 'disc', 'img': 'disc', 'vhd': 'disc',
        'exe': 'settings', 'msi': 'settings', 'deb': 'settings', 'rpm': 'settings',
        'apk': 'smartphone', 'aab': 'smartphone', 'ipa': 'smartphone'
    }
    return icon_map.get(ext, 'file')

def get_system_shortcuts():
    """Récupère les raccourcis vers les dossiers principaux de l'utilisateur (Bureau, Téléchargements, Documents, Images, Vidéos)"""
    home = os.path.expanduser('~')
    user_profile = os.environ.get('USERPROFILE', home)
    
    categories = [
        {
            'id': 'desktop',
            'name': 'Bureau',
            'sub': 'Desktop',
            'icon': 'monitor',
            'color': '#0366d6',
            'candidates': [
                os.path.join(user_profile, 'Desktop'),
                os.path.join(user_profile, 'Bureau'),
                os.path.join(user_profile, 'OneDrive', 'Desktop'),
                os.path.join(user_profile, 'OneDrive', 'Bureau'),
                os.path.join(home, 'Desktop'),
                os.path.join(home, 'Bureau'),
            ]
        },
        {
            'id': 'downloads',
            'name': 'Téléchargements',
            'sub': 'Downloads',
            'icon': 'download',
            'color': '#f68b1e',
            'candidates': [
                os.path.join(user_profile, 'Downloads'),
                os.path.join(user_profile, 'Téléchargements'),
                os.path.join(user_profile, 'Telechargements'),
                os.path.join(home, 'Downloads'),
                os.path.join(home, 'Téléchargements'),
                os.path.join(home, 'Telechargements'),
            ]
        },
        {
            'id': 'documents',
            'name': 'Documents',
            'sub': 'Documents',
            'icon': 'file-text',
            'color': '#3b82f6',
            'candidates': [
                os.path.join(user_profile, 'Documents'),
                os.path.join(user_profile, 'OneDrive', 'Documents'),
                os.path.join(user_profile, 'Mes Documents'),
                os.path.join(home, 'Documents'),
                os.path.join(home, 'Mes Documents'),
            ]
        },
        {
            'id': 'pictures',
            'name': 'Images',
            'sub': 'Photos & Images',
            'icon': 'image',
            'color': '#10b981',
            'candidates': [
                os.path.join(user_profile, 'Pictures'),
                os.path.join(user_profile, 'Images'),
                os.path.join(user_profile, 'OneDrive', 'Pictures'),
                os.path.join(user_profile, 'OneDrive', 'Images'),
                os.path.join(user_profile, 'Mes Images'),
                os.path.join(home, 'Pictures'),
                os.path.join(home, 'Images'),
            ]
        },
        {
            'id': 'videos',
            'name': 'Vidéos',
            'sub': 'Films & Vidéos',
            'icon': 'video',
            'color': '#8b5cf6',
            'candidates': [
                os.path.join(user_profile, 'Videos'),
                os.path.join(user_profile, 'Vidéos'),
                os.path.join(user_profile, 'Mes Vidéos'),
                os.path.join(home, 'Videos'),
                os.path.join(home, 'Vidéos'),
            ]
        },
    ]

    shortcuts = []
    for cat in categories:
        target_path = None
        for candidate in cat['candidates']:
            if candidate and os.path.exists(candidate) and os.path.isdir(candidate):
                target_path = candidate
                break
        
        if not target_path:
            target_path = cat['candidates'][0]
            try:
                if not os.path.exists(target_path):
                    os.makedirs(target_path, exist_ok=True)
            except Exception:
                pass
        
        if sys.platform == 'win32':
            url_path = target_path.replace('\\', '/')
        else:
            url_path = target_path[1:] if target_path.startswith('/') else target_path

        item_count = None
        try:
            if os.path.exists(target_path) and os.path.isdir(target_path):
                item_count = len(os.listdir(target_path))
        except Exception:
            item_count = None

        shortcuts.append({
            'id': cat['id'],
            'name': cat['name'],
            'sub': cat['sub'],
            'icon': cat['icon'],
            'color': cat['color'],
            'path': target_path,
            'url_path': url_path,
            'item_count': item_count
        })

    return shortcuts

def configure_console(make_full_green_text=True, clear_screen=True, title="Transfert - Serveur"):
    try:
        if clear_screen:
            os.system('cls' if os.name == 'nt' else 'clear')
    except Exception:
        pass
    try:
        if os.name == 'nt':
            os.system(f'title {title}')
        else:
            sys.stdout.write(f"\x1b]0;{title}\x07")
    except Exception:
        pass
    try:
        import colorama
        colorama.init()
        if make_full_green_text:
            sys.stdout.write(colorama.Fore.GREEN + colorama.Style.BRIGHT)
        return
    except Exception:
        pass
    try:
        if os.name == 'nt':
            import ctypes
            STD_OUTPUT_HANDLE = -11
            handle = ctypes.windll.kernel32.GetStdHandle(STD_OUTPUT_HANDLE)
            ctypes.windll.kernel32.SetConsoleTextAttribute(handle, 0x0A)
            return
    except Exception:
        pass
    try:
        if make_full_green_text:
            sys.stdout.write('\033[92m')
    except Exception:
        pass

def generer_qr_code_base64(url):
    """Génère un QR code et le retourne en base64 pour l'afficher dans une page HTML avec repli SVG pur."""
    if QRCODE_AVAILABLE:
        try:
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data(url)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="#0366d6", back_color="#0a0e1a")
            buffered = io.BytesIO()
            img.save(buffered, format="PNG")
            return base64.b64encode(buffered.getvalue()).decode()
        except Exception as e:
            print(f"Avertissement QR: {e}")

    # Repli SVG autonome sans dépendance externe
    try:
        # Encodage SVG basique ou SVG visuel
        svg_qr = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 260" width="250" height="250">
            <rect width="260" height="260" fill="#0a0e1a" rx="16"/>
            <!-- Repères QR -->
            <rect x="20" y="20" width="60" height="60" rx="8" fill="none" stroke="#0366d6" stroke-width="8"/>
            <rect x="36" y="36" width="28" height="28" fill="#f68b1e" rx="4"/>
            <rect x="180" y="20" width="60" height="60" rx="8" fill="none" stroke="#0366d6" stroke-width="8"/>
            <rect x="196" y="36" width="28" height="28" fill="#f68b1e" rx="4"/>
            <rect x="20" y="180" width="60" height="60" rx="8" fill="none" stroke="#0366d6" stroke-width="8"/>
            <rect x="36" y="196" width="28" height="28" fill="#f68b1e" rx="4"/>
            <!-- Motif matriciel moderne -->
            <g fill="#38bdf8" opacity="0.85">
                <rect x="100" y="25" width="12" height="12" rx="2"/>
                <rect x="125" y="25" width="12" height="12" rx="2"/>
                <rect x="150" y="25" width="12" height="12" rx="2"/>
                <rect x="100" y="55" width="12" height="12" rx="2"/>
                <rect x="140" y="55" width="12" height="12" rx="2"/>
                <rect x="25" y="100" width="12" height="12" rx="2"/>
                <rect x="55" y="100" width="12" height="12" rx="2"/>
                <rect x="100" y="100" width="20" height="20" fill="#f68b1e" rx="4"/>
                <rect x="135" y="100" width="12" height="12" rx="2"/>
                <rect x="160" y="100" width="12" height="12" rx="2"/>
                <rect x="190" y="100" width="12" height="12" rx="2"/>
                <rect x="220" y="100" width="12" height="12" rx="2"/>
                <rect x="100" y="135" width="12" height="12" rx="2"/>
                <rect x="130" y="135" width="12" height="12" rx="2"/>
                <rect x="160" y="135" width="12" height="12" rx="2"/>
                <rect x="220" y="135" width="12" height="12" rx="2"/>
                <rect x="25" y="140" width="12" height="12" rx="2"/>
                <rect x="60" y="140" width="12" height="12" rx="2"/>
                <rect x="100" y="180" width="12" height="12" rx="2"/>
                <rect x="140" y="180" width="12" height="12" rx="2"/>
                <rect x="180" y="180" width="12" height="12" rx="2"/>
                <rect x="210" y="180" width="12" height="12" rx="2"/>
                <rect x="100" y="215" width="12" height="12" rx="2"/>
                <rect x="135" y="215" width="12" height="12" rx="2"/>
                <rect x="170" y="215" width="12" height="12" rx="2"/>
                <rect x="205" y="215" width="12" height="12" rx="2"/>
            </g>
        </svg>'''
        return "svg," + base64.b64encode(svg_qr.encode('utf-8')).decode('utf-8')
    except Exception:
        return None

def cleanup_old_sessions():
    """Nettoie les sessions de plus de 30 minutes"""
    while True:
        time.sleep(60)  # Vérifier toutes les minutes
        now = datetime.datetime.now()
        to_delete = []
        for sid, session in PENDING_FILES.items():
            try:
                created = datetime.datetime.fromisoformat(session['timestamp'])
                if (now - created).total_seconds() > 1800:  # 30 minutes
                    to_delete.append(sid)
            except:
                to_delete.append(sid)
        
        for sid in to_delete:
            # Nettoyer les fichiers temporaires
            session = PENDING_FILES.get(sid, {})
            for f in session.get('files', []):
                try:
                    if os.path.exists(f['path']):
                        os.remove(f['path'])
                except:
                    pass
            # Supprimer le dossier de session
            session_dir = os.path.join(TEMP_TRANSFER_FOLDER, sid)
            if os.path.exists(session_dir):
                try:
                    shutil.rmtree(session_dir)
                except:
                    pass
            if sid in PENDING_FILES:
                del PENDING_FILES[sid]

# Démarrer le thread de nettoyage
cleanup_thread = threading.Thread(target=cleanup_old_sessions, daemon=True)
cleanup_thread.start()

# --- ROUTES FLASK ---

@app.route('/api/ping', methods=['HEAD', 'GET'])
def ping():
    return '', 200

# --- INTERCEPTEUR POUR DÉTECTION AUTOMATIQUE DES APPAREILS CONNECTÉS ---
@app.before_request
def track_client_activity():
    """Détecte uniquement lorsqu'un véritable appareil externe ou mobile se connecte au serveur."""
    ip = request.remote_addr
    path = request.path
    
    # Ne jamais déclencher sur les requêtes de surveillance d'état, de QR code ou de ressources statiques du PC
    if path.startswith(('/qr', '/QR', '/Qr', '/api/connection_status', '/static', '/SVG Mobile', '/assets', '/favicon.ico')):
        return
        
    # Liste des adresses IP locales de la machine hôte
    host_ips = {'127.0.0.1', 'localhost', '::1'}
    try:
        host_ips.update(get_all_local_ips())
        host_ips.add(get_local_ip())
    except Exception:
        pass
        
    ua = request.headers.get('User-Agent', '')
    is_mobile_ua = any(kw in ua for kw in ['Mobile', 'Android', 'iPhone', 'iPad', 'PyDrop', 'Dart', 'okhttp', 'Ktor'])
    
    # Si la requête vient d'une IP externe OU possède un user-agent mobile/app explicite
    is_external = ip and (ip not in ('127.0.0.1', 'localhost', '::1'))
    
    if is_external or is_mobile_ua:
        dev_name = parse_device_name(ua, ip)
        CONNECTED_CLIENT['connected'] = True
        CONNECTED_CLIENT['ip'] = ip
        CONNECTED_CLIENT['device_name'] = dev_name
        CONNECTED_CLIENT['last_seen'] = time.time()
        if not CONNECTED_CLIENT['connected_at']:
            CONNECTED_CLIENT['connected_at'] = time.time()

# --- ROUTES QR CODE & SUCCÈS DE CONNEXION ---

@app.route('/qr')
@app.route('/QR')
@app.route('/Qr')
def qr_page():
    """Page QR Code épurée, ultra-moderne, avec radar de pulsation et détection automatique de connexion."""
    ip_addr = get_local_ip()
    url = f"http://{ip_addr}:{PORT}"
    qr_base64 = generer_qr_code_base64(url) or ""
    
    html_qr = """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
        <link rel="icon" type="image/png" href="/static/pydrop1.png">
        <title>PyDrop - Connexion</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            :root {
                --primary: #0284c7;
                --primary-glow: rgba(2, 132, 199, 0.4);
                --accent: #f59e0b;
                --success: #10b981;
                --success-glow: rgba(16, 185, 129, 0.5);
                --bg: #0b0f19;
                --card-bg: rgba(17, 24, 39, 0.85);
                --border: rgba(255, 255, 255, 0.08);
                --text: #f8fafc;
                --text-muted: #94a3b8;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: var(--bg);
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                padding: 24px 16px;
                color: var(--text);
                position: relative;
                overflow-x: hidden;
            }
            /* Halo d'ambiance d'arrière-plan */
            .ambient-glow {
                position: absolute;
                width: 600px;
                height: 600px;
                border-radius: 50%;
                background: radial-gradient(circle, rgba(2, 132, 199, 0.12) 0%, rgba(245, 158, 11, 0.04) 50%, transparent 70%);
                filter: blur(80px);
                pointer-events: none;
                z-index: 0;
            }
            .main-wrapper {
                position: relative;
                z-index: 1;
                width: 100%;
                max-width: 440px;
                display: flex;
                flex-direction: column;
                align-items: center;
                text-align: center;
                gap: 20px;
            }
            /* En-tête avec Logo et Nom */
            .brand-header {
                display: flex;
                align-items: center;
                gap: 14px;
                padding: 8px 16px;
                border-radius: 999px;
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid var(--border);
                backdrop-filter: blur(12px);
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
            }
            .brand-logo {
                width: 40px;
                height: 40px;
                border-radius: 10px;
                object-fit: contain;
                filter: drop-shadow(0 4px 10px rgba(2, 132, 199, 0.35));
            }
            .brand-title {
                font-size: 26px;
                font-weight: 800;
                letter-spacing: -0.03em;
                display: flex;
            }
            .brand-title .part-py { color: #38bdf8; }
            .brand-title .part-drop { color: #fbbf24; }

            /* Carte Centrale */
            .qr-card {
                position: relative;
                width: 100%;
                background: var(--card-bg);
                border: 1px solid var(--border);
                border-radius: 28px;
                padding: 32px 24px;
                box-shadow: 0 20px 40px -15px rgba(0, 0, 0, 0.7), 0 0 0 1px rgba(255, 255, 255, 0.05);
                backdrop-filter: blur(16px);
                display: flex;
                flex-direction: column;
                align-items: center;
                transition: all 0.5s cubic-bezier(0.16, 1, 0.3, 1);
            }

            /* Boîte du code QR */
            .qr-wrapper {
                background: #ffffff;
                padding: 16px;
                border-radius: 20px;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
                display: flex;
                justify-content: center;
                align-items: center;
                margin-bottom: 24px;
                position: relative;
                transition: all 0.4s ease;
            }
            .qr-wrapper img, .qr-wrapper canvas {
                display: block;
                width: 220px;
                height: 220px;
                border-radius: 8px;
            }

            /* Le cercle qui bat (Onde de pulsation radar) */
            .pulse-section {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 12px;
                margin-bottom: 22px;
            }
            .radar-pulse-container {
                position: relative;
                width: 44px;
                height: 44px;
                display: flex;
                justify-content: center;
                align-items: center;
            }
            .radar-center-dot {
                width: 12px;
                height: 12px;
                border-radius: 50%;
                background: #38bdf8;
                box-shadow: 0 0 14px #38bdf8;
                z-index: 2;
                position: relative;
                animation: pulseCenter 2s infinite ease-in-out;
            }
            .radar-ring {
                position: absolute;
                width: 100%;
                height: 100%;
                border-radius: 50%;
                border: 2px solid rgba(56, 189, 248, 0.8);
                animation: radarRipple 2.2s cubic-bezier(0.2, 0.8, 0.4, 1) infinite;
            }
            .radar-ring:nth-child(2) {
                animation-delay: 0.7s;
            }
            .radar-ring:nth-child(3) {
                animation-delay: 1.4s;
            }
            @keyframes radarRipple {
                0% {
                    transform: scale(0.3);
                    opacity: 0.9;
                }
                100% {
                    transform: scale(2.2);
                    opacity: 0;
                }
            }
            @keyframes pulseCenter {
                0%, 100% { transform: scale(1); filter: brightness(1); }
                50% { transform: scale(1.25); filter: brightness(1.3); }
            }

            .pulse-label {
                font-size: 14px;
                font-weight: 500;
                color: var(--text-muted);
                letter-spacing: 0.01em;
            }

            /* Boîte IP du bas */
            .ip-box {
                width: 100%;
                background: rgba(0, 0, 0, 0.45);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 16px;
                padding: 12px 16px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 10px;
                transition: border-color 0.2s;
            }
            .ip-box:hover {
                border-color: rgba(56, 189, 248, 0.3);
            }
            .ip-info {
                text-align: left;
                overflow: hidden;
            }
            .ip-label {
                font-size: 11px;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: #64748b;
                margin-bottom: 2px;
            }
            .ip-text {
                font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
                font-size: 15px;
                font-weight: 600;
                color: #f1f5f9;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .btn-copy {
                background: rgba(255, 255, 255, 0.07);
                border: 1px solid rgba(255, 255, 255, 0.1);
                color: #cbd5e1;
                padding: 8px 12px;
                border-radius: 10px;
                font-size: 12px;
                font-weight: 600;
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                gap: 6px;
                transition: all 0.2s;
                white-space: nowrap;
            }
            .btn-copy:hover {
                background: rgba(255, 255, 255, 0.15);
                color: #ffffff;
            }

            /* LIENS SECONDAIRES */
            .quick-actions {
                display: flex;
                gap: 12px;
                margin-top: 10px;
            }
            .quick-btn {
                font-size: 13px;
                color: #94a3b8;
                text-decoration: none;
                padding: 6px 14px;
                border-radius: 20px;
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.06);
                transition: all 0.2s;
            }
            .quick-btn:hover {
                color: #ffffff;
                background: rgba(255, 255, 255, 0.08);
            }

            /* ÉTAT DE SUCCÈS CONNECTÉ */
            .connected-overlay {
                display: none;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: 16px;
                animation: popSuccess 0.5s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards;
            }
            @keyframes popSuccess {
                0% { opacity: 0; transform: scale(0.85); }
                100% { opacity: 1; transform: scale(1); }
            }
            .success-sphere {
                width: 90px;
                height: 90px;
                border-radius: 50%;
                background: linear-gradient(135deg, #10b981, #059669);
                box-shadow: 0 0 35px var(--success-glow);
                display: flex;
                justify-content: center;
                align-items: center;
                position: relative;
            }
            .success-sphere svg {
                width: 48px;
                height: 48px;
                color: #ffffff;
            }
            .success-sphere::after {
                content: '';
                position: absolute;
                width: 100%;
                height: 100%;
                border-radius: 50%;
                border: 2px solid #10b981;
                animation: successWave 1.8s infinite ease-out;
            }
            @keyframes successWave {
                0% { transform: scale(1); opacity: 0.9; }
                100% { transform: scale(1.6); opacity: 0; }
            }
            .success-title {
                font-size: 24px;
                font-weight: 800;
                color: #34d399;
                letter-spacing: -0.02em;
            }
            .success-subtitle {
                font-size: 15px;
                color: #cbd5e1;
                font-weight: 500;
            }
            .redirect-progress-bar {
                width: 100%;
                height: 6px;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 999px;
                overflow: hidden;
                margin-top: 10px;
            }
            .redirect-fill {
                height: 100%;
                background: #10b981;
                width: 0%;
                transition: width 1.6s linear;
            }
        </style>
    </head>
    <body>
        <div class="ambient-glow"></div>
        
        <div class="main-wrapper">
            <!-- En-tête : Logo PyDrop -->
            <div class="brand-header">
                <img src="/static/pydrop1.png" alt="PyDrop" class="brand-logo" onerror="this.src='/static/logo.png'">
                <div class="brand-title">
                    <span class="part-py">Py</span><span class="part-drop">Drop</span>
                </div>
            </div>

            <!-- Carte Principale -->
            <div class="qr-card" id="mainCard">
                <!-- Vue Normale : QR Code & Cercle pulsant -->
                <div id="qrContent" style="width: 100%; display: flex; flex-direction: column; align-items: center;">
                    <!-- Code QR -->
                    <div class="qr-wrapper" id="qrContainer">
                        {% if qr_base64 %}
                        <img src="data:image/png;base64,{{ qr_base64 }}" alt="QR Code" id="qrImg">
                        {% else %}
                        <div id="qrcodeCanvas"></div>
                        {% endif %}
                    </div>

                    <!-- Le cercle qui bat -->
                    <div class="pulse-section">
                        <div class="radar-pulse-container">
                            <div class="radar-ring"></div>
                            <div class="radar-ring"></div>
                            <div class="radar-ring"></div>
                            <div class="radar-center-dot"></div>
                        </div>
                        <div class="pulse-label" id="pulseLabel">En attente de connexion...</div>
                    </div>

                    <!-- Adresse IP du serveur en bas -->
                    <div class="ip-box">
                        <div class="ip-info">
                            <div class="ip-label">Adresse de connexion</div>
                            <div class="ip-text" id="serverIpText">{{ url }}</div>
                        </div>
                        <button class="btn-copy" id="btnCopy" onclick="copyIp()">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                            <span id="copyLabel">Copier</span>
                        </button>
                    </div>
                </div>

                <!-- Vue Succès : Connexion réussie + Redirection -->
                <div class="connected-overlay" id="connectedOverlay">
                    <div class="success-sphere">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round">
                            <polyline points="20 6 9 17 4 12"></polyline>
                        </svg>
                    </div>
                    <div class="success-title">Connexion réussie !</div>
                    <div class="success-subtitle" id="connectedDeviceText">Appareil connecté</div>
                    <div class="redirect-progress-bar">
                        <div class="redirect-fill" id="redirectFill"></div>
                    </div>
                </div>
            </div>

            <!-- Liens d'accès direct -->
            <div class="quick-actions">
                <a href="/transfers" class="quick-btn">Accéder aux transferts</a>
                <a href="/mobile" class="quick-btn">Ouvrir le scanner</a>
            </div>
        </div>

        <script src="/static/qrcode.min.js"></script>
        <script>
            const SERVER_URL = "{{ url }}";
            let isConnectedState = false;

            // Génération QR client de repli si besoin
            try {
                if (!document.getElementById('qrImg') && typeof QRCode !== 'undefined') {
                    new QRCode(document.getElementById("qrcodeCanvas"), {
                        text: SERVER_URL,
                        width: 220,
                        height: 220,
                        colorDark: "#0f172a",
                        colorLight: "#ffffff",
                        correctLevel: "H"
                    });
                }
            } catch (e) {}

            // Copie d'adresse IP
            function copyIp() {
                navigator.clipboard.writeText(SERVER_URL).then(() => {
                    const label = document.getElementById('copyLabel');
                    label.textContent = "Copié !";
                    setTimeout(() => { label.textContent = "Copier"; }, 2000);
                }).catch(() => {});
            }

            // Détection de connexion en temps réel (Polling)
            async function checkConnection() {
                if (isConnectedState) return;
                try {
                    const res = await fetch('/api/connection_status?t=' + Date.now());
                    if (res.ok) {
                        const data = await res.json();
                        if (data.connected) {
                            triggerSuccessAnimation(data.device || {});
                        }
                    }
                } catch (err) {}
            }

            // Déclenchement de l'animation de succès et redirection
            function triggerSuccessAnimation(device) {
                if (isConnectedState) return;
                isConnectedState = true;

                const qrContent = document.getElementById('qrContent');
                const overlay = document.getElementById('connectedOverlay');
                const devText = document.getElementById('connectedDeviceText');
                const fill = document.getElementById('redirectFill');

                if (device && (device.device_name || device.ip)) {
                    devText.textContent = `${device.device_name || 'Appareil'} (${device.ip || ''})`;
                } else {
                    devText.textContent = "Appareil prêt au transfert";
                }

                // Transition fluide
                qrContent.style.display = 'none';
                overlay.style.display = 'flex';

                setTimeout(() => {
                    fill.style.width = '100%';
                }, 50);

                // Redirection vers le centre de transferts après 1.7s
                setTimeout(() => {
                    window.location.href = '/transfers';
                }, 1800);
            }

            // Vérification périodique toutes les 700ms
            setInterval(checkConnection, 700);
        </script>
    </body>
    </html>
    """
    return render_template_string(html_qr, qr_base64=qr_base64, url=url)

# ==============================================
# ROUTE TABLEAU DE BORD DES TRANSFERTS (/transfers)
# ==============================================

@app.route('/transfers')
@app.route('/dashboard')
def transfers_page():
    """Tableau de bord des transferts en temps réel : fichiers reçus, fichiers pris, progression."""
    received_files = get_all_received_files()
    local_ip = get_local_ip()
    server_url = f"http://{local_ip}:{PORT}"
    
    html_transfers = """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link rel="icon" type="image/png" href="/static/pydrop1.png">
        <title>PyDrop - Centre de Transferts</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            :root {
                --primary: #0284c7;
                --primary-glow: rgba(2, 132, 199, 0.3);
                --accent: #f59e0b;
                --success: #10b981;
                --bg: #0b0f19;
                --card-bg: #131b2e;
                --card-header: #17223b;
                --border: rgba(255, 255, 255, 0.08);
                --text: #f8fafc;
                --text-muted: #94a3b8;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                background: var(--bg);
                color: var(--text);
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                overflow-x: hidden;
            }
            /* NAVBAR */
            .navbar {
                background: rgba(15, 23, 42, 0.9);
                backdrop-filter: blur(12px);
                border-bottom: 1px solid var(--border);
                padding: 14px 24px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                position: sticky;
                top: 0;
                z-index: 100;
            }
            .nav-brand {
                display: flex;
                align-items: center;
                gap: 12px;
                text-decoration: none;
                color: inherit;
            }
            .nav-logo {
                width: 36px;
                height: 36px;
                border-radius: 8px;
            }
            .nav-title {
                font-size: 20px;
                font-weight: 800;
            }
            .nav-title .part-py { color: #38bdf8; }
            .nav-title .part-drop { color: #fbbf24; }
            
            .nav-actions {
                display: flex;
                align-items: center;
                gap: 12px;
            }
            .device-badge {
                display: flex;
                align-items: center;
                gap: 8px;
                background: rgba(16, 185, 129, 0.12);
                border: 1px solid rgba(16, 185, 129, 0.3);
                color: #34d399;
                padding: 6px 14px;
                border-radius: 999px;
                font-size: 13px;
                font-weight: 600;
            }
            .device-dot {
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: #10b981;
                box-shadow: 0 0 8px #10b981;
                animation: dotPulse 1.8s infinite;
            }
            @keyframes dotPulse {
                0%, 100% { opacity: 1; transform: scale(1); }
                50% { opacity: 0.5; transform: scale(0.8); }
            }
            .btn-action {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid var(--border);
                color: #cbd5e1;
                padding: 8px 14px;
                border-radius: 10px;
                font-size: 13px;
                font-weight: 600;
                text-decoration: none;
                cursor: pointer;
                display: inline-flex;
                align-items: center;
                gap: 6px;
                transition: all 0.2s;
            }
            .btn-action:hover {
                background: rgba(255, 255, 255, 0.12);
                color: #ffffff;
            }

            /* MAIN CONTENT */
            .main-container {
                max-width: 1100px;
                width: 100%;
                margin: 0 auto;
                padding: 28px 20px;
                display: flex;
                flex-direction: column;
                gap: 28px;
            }

            /* SECTION TITLES */
            .section-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 14px;
            }
            .section-title {
                font-size: 18px;
                font-weight: 700;
                display: flex;
                align-items: center;
                gap: 10px;
                color: #f1f5f9;
            }
            .badge-count {
                background: rgba(56, 189, 248, 0.15);
                color: #38bdf8;
                font-size: 12px;
                font-weight: 700;
                padding: 2px 8px;
                border-radius: 12px;
            }

            /* CARTES DES TRANSFERTS EN COURS */
            .transfers-live-card {
                background: var(--card-bg);
                border: 1px solid var(--border);
                border-radius: 20px;
                padding: 20px;
                box-shadow: 0 10px 25px rgba(0, 0, 0, 0.4);
            }
            .empty-transfers {
                text-align: center;
                padding: 30px 20px;
                color: var(--text-muted);
                font-size: 14px;
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 10px;
            }
            .empty-icon {
                width: 48px;
                height: 48px;
                opacity: 0.4;
            }

            .transfer-item {
                background: rgba(0, 0, 0, 0.25);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 14px;
                padding: 16px;
                margin-bottom: 12px;
                display: flex;
                flex-direction: column;
                gap: 10px;
                animation: slideDown 0.3s ease;
            }
            @keyframes slideDown {
                from { opacity: 0; transform: translateY(-8px); }
                to { opacity: 1; transform: translateY(0); }
            }
            .transfer-top {
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .transfer-file-info {
                display: flex;
                align-items: center;
                gap: 12px;
            }
            .transfer-file-name {
                font-weight: 600;
                font-size: 15px;
                color: #f8fafc;
            }
            .transfer-direction {
                font-size: 12px;
                font-weight: 600;
                padding: 2px 8px;
                border-radius: 6px;
                background: rgba(56, 189, 248, 0.15);
                color: #38bdf8;
            }
            .transfer-meta {
                font-size: 13px;
                color: var(--text-muted);
                display: flex;
                gap: 16px;
            }
            .progress-track {
                width: 100%;
                height: 8px;
                background: rgba(255, 255, 255, 0.08);
                border-radius: 999px;
                overflow: hidden;
                position: relative;
            }
            .progress-bar-fill {
                height: 100%;
                background: linear-gradient(90deg, #0284c7, #38bdf8, #f59e0b);
                border-radius: 999px;
                transition: width 0.2s ease;
            }

            /* GRILLE / LISTE DES FICHIERS REÇUS */
            .files-card {
                background: var(--card-bg);
                border: 1px solid var(--border);
                border-radius: 20px;
                overflow: hidden;
                box-shadow: 0 10px 25px rgba(0, 0, 0, 0.4);
            }
            .files-table {
                width: 100%;
                border-collapse: collapse;
                text-align: left;
            }
            .files-table th {
                background: var(--card-header);
                padding: 14px 20px;
                font-size: 12px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: var(--text-muted);
                border-bottom: 1px solid var(--border);
            }
            .files-table td {
                padding: 14px 20px;
                font-size: 14px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.04);
                vertical-align: middle;
            }
            .files-table tr:hover td {
                background: rgba(255, 255, 255, 0.02);
            }
            .file-name-cell {
                display: flex;
                align-items: center;
                gap: 12px;
                font-weight: 600;
                color: #f1f5f9;
            }
            .file-svg-icon {
                width: 28px;
                height: 28px;
                flex-shrink: 0;
            }
            .file-date {
                color: var(--text-muted);
                font-size: 13px;
            }
            .file-size {
                font-family: ui-monospace, SFMono-Regular, monospace;
                font-size: 13px;
                color: #cbd5e1;
            }
            .file-actions {
                display: flex;
                gap: 8px;
                justify-content: flex-end;
            }
            .btn-table-action {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.08);
                color: #cbd5e1;
                padding: 6px 12px;
                border-radius: 8px;
                font-size: 12px;
                font-weight: 600;
                text-decoration: none;
                cursor: pointer;
                transition: all 0.2s;
            }
            .btn-table-action:hover {
                background: rgba(56, 189, 248, 0.2);
                color: #38bdf8;
                border-color: rgba(56, 189, 248, 0.4);
            }

            /* ZONE D'ENVOI RAPIDE PC -> MOBILE */
            .quick-send-zone {
                border: 2px dashed rgba(56, 189, 248, 0.3);
                border-radius: 16px;
                padding: 24px;
                text-align: center;
                background: rgba(2, 132, 199, 0.03);
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 10px;
                cursor: pointer;
                transition: all 0.2s;
            }
            .quick-send-zone:hover {
                border-color: #38bdf8;
                background: rgba(2, 132, 199, 0.08);
            }
        </style>
    </head>
    <body>
        <!-- NAVBAR -->
        <header class="navbar">
            <a href="/qr" class="nav-brand">
                <img src="/static/pydrop1.png" alt="PyDrop" class="nav-logo" onerror="this.src='/static/logo.png'">
                <div class="nav-title">
                    <span class="part-py">Py</span><span class="part-drop">Drop</span>
                </div>
            </a>

            <div class="nav-actions">
                <div class="device-badge" id="navDeviceBadge">
                    <span class="device-dot"></span>
                    <span id="navDeviceName">En attente d'appareil</span>
                </div>
                <button class="btn-action" onclick="openReceivedFolder()">
                    <img src="/static/icons/folder.svg" style="width:16px;height:16px;" alt="">
                    <span>Dossier Reçus</span>
                </button>
                <a href="/" class="btn-action">
                    <img src="/static/icons/hard-drive.svg" style="width:16px;height:16px;" alt="">
                    <span>Explorateur PC</span>
                </a>
                <a href="/qr" class="btn-action" style="color:#fbbf24;">
                    <img src="/static/icons/qr-code.svg" style="width:16px;height:16px;" alt="">
                    <span>Code QR</span>
                </a>
            </div>
        </header>

        <!-- MAIN CONTAINER -->
        <main class="main-container">
            <!-- SECTION 1 : TRANSFERTS EN COURS -->
            <section>
                <div class="section-header">
                    <h2 class="section-title">
                        <img src="/static/icons/refresh-cw.svg" style="width:20px;height:20px;" alt="">
                        <span>Transferts en Direct</span>
                        <span class="badge-count" id="activeCount">0</span>
                    </h2>
                </div>

                <div class="transfers-live-card" id="activeTransfersContainer">
                    <div class="empty-transfers" id="emptyTransfersMsg">
                        <img src="/static/icons/check-circle.svg" class="empty-icon" alt="">
                        <div>Aucun transfert en cours. Tout est prêt !</div>
                    </div>
                    <div id="activeTransfersList"></div>
                </div>
            </section>

            <!-- SECTION 2 : FICHIERS REÇUS DU CLIENT -->
            <section>
                <div class="section-header">
                    <h2 class="section-title">
                        <img src="/static/icons/download.svg" style="width:20px;height:20px;" alt="">
                        <span>Fichiers Reçus depuis le Client</span>
                        <span class="badge-count" id="receivedCount">{{ received_files|length }}</span>
                    </h2>
                    <button class="btn-action" onclick="refreshTransfers()">
                        <img src="/static/icons/refresh-cw.svg" style="width:14px;height:14px;" alt="">
                        <span>Actualiser</span>
                    </button>
                </div>

                <div class="files-card">
                    <table class="files-table">
                        <thead>
                            <tr>
                                <th>Nom du fichier</th>
                                <th>Taille</th>
                                <th>Date de réception</th>
                                <th style="text-align: right;">Actions</th>
                            </tr>
                        </thead>
                        <tbody id="receivedFilesTableBody">
                            {% for f in received_files %}
                            <tr id="row-{{ f.name }}">
                                <td>
                                    <div class="file-name-cell">
                                        <img src="/static/icons/{{ f.icon }}.svg" class="file-svg-icon" alt="{{ f.ext }}">
                                        <span>{{ f.name }}</span>
                                    </div>
                                </td>
                                <td class="file-size">{{ f.formatted_size }}</td>
                                <td class="file-date">{{ f.date_str }}</td>
                                <td>
                                    <div class="file-actions">
                                        <button class="btn-table-action" onclick="openLocalFile('{{ f.name }}')">Ouvrir</button>
                                        <a href="/download_received/{{ f.name }}" class="btn-table-action" download>Télécharger</a>
                                    </div>
                                </td>
                            </tr>
                            {% else %}
                            <tr id="noReceivedRow">
                                <td colspan="4" style="text-align:center; padding:30px; color:#64748b;">
                                    Aucun fichier reçu pour le moment. Envoyez un fichier depuis le smartphone !
                                </td>
                            </tr>
                            {% endfor %}
                        </tbody>
                    </table>
                </div>
            </section>

            <!-- SECTION 3 : ENVOI RAPIDE PC -> MOBILE -->
            <section>
                <div class="section-header">
                    <h2 class="section-title">
                        <img src="/static/icons/upload.svg" style="width:20px;height:20px;" alt="">
                        <span>Envoyer un fichier vers le Client</span>
                    </h2>
                </div>

                <form id="pcUploadForm" action="/upload" method="post" enctype="multipart/form-data">
                    <input type="file" id="pcFileInput" name="file" multiple style="display:none;" onchange="handlePcUpload(this)">
                    <div class="quick-send-zone" onclick="document.getElementById('pcFileInput').click()">
                        <img src="/static/icons/paperclip.svg" style="width:32px;height:32px;opacity:0.7;" alt="">
                        <div style="font-weight:600;font-size:15px;">Cliquez ou glissez-déposez des fichiers ici</div>
                        <div style="font-size:13px;color:#94a3b8;">Pour les mettre à disposition du téléphone connecté</div>
                    </div>
                </form>
            </section>
        </main>

        <script>
            // Ouvrir le dossier local sur le PC
            async function openReceivedFolder() {
                try {
                    await fetch('/api/open_folder', { method: 'POST' });
                } catch (e) {}
            }

            // Ouvrir un fichier sur le PC
            async function openLocalFile(filename) {
                try {
                    const res = await fetch('/api/open_file', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ filename: filename })
                    });
                } catch (e) {}
            }

            // Upload depuis le PC
            function handlePcUpload(input) {
                if (input.files && input.files.length > 0) {
                    document.getElementById('pcUploadForm').submit();
                }
            }

            // Actualisation dynamique en temps réel
            async function refreshTransfers() {
                try {
                    const res = await fetch('/api/transfers_status?t=' + Date.now());
                    if (!res.ok) return;
                    const data = await res.json();

                    // Mise à jour du badge appareil
                    const navDev = document.getElementById('navDeviceName');
                    if (data.device && (data.device.device_name || data.device.ip)) {
                        navDev.textContent = `${data.device.device_name || 'Appareil'} (${data.device.ip || ''})`;
                    }

                    // Mise à jour des transferts actifs
                    const activeList = data.active_transfers || [];
                    const activeCountEl = document.getElementById('activeCount');
                    const emptyMsg = document.getElementById('emptyTransfersMsg');
                    const activeListContainer = document.getElementById('activeTransfersList');
                    
                    activeCountEl.textContent = activeList.length;

                    if (activeList.length === 0) {
                        emptyMsg.style.display = 'flex';
                        activeListContainer.innerHTML = '';
                    } else {
                        emptyMsg.style.display = 'none';
                        activeListContainer.innerHTML = activeList.map(t => `
                            <div class="transfer-item">
                                <div class="transfer-top">
                                    <div class="transfer-file-info">
                                        <img src="/static/icons/${t.icon || 'file'}.svg" style="width:24px;height:24px;" alt="">
                                        <span class="transfer-file-name">${t.filename}</span>
                                        <span class="transfer-direction">${t.direction || (t.type === 'upload' ? 'Téléphone → PC' : 'PC → Téléphone')}</span>
                                    </div>
                                    <div style="font-weight:700;color:#38bdf8;">${t.percent || 0}%</div>
                                </div>
                                <div class="progress-track">
                                    <div class="progress-bar-fill" style="width: ${t.percent || 0}%;"></div>
                                </div>
                                <div class="transfer-meta">
                                    <span>${t.formatted_size || ''}</span>
                                    <span>Vitesse : ${t.speed_str || 'En cours...'}</span>
                                    <span>Statut : ${t.status === 'completed' ? 'Terminé' : 'En transfert'}</span>
                                </div>
                            </div>
                        `).join('');
                    }

                    // Mise à jour des fichiers reçus
                    if (data.received_files) {
                        const recCount = document.getElementById('receivedCount');
                        recCount.textContent = data.received_files.length;
                        
                        const tbody = document.getElementById('receivedFilesTableBody');
                        if (data.received_files.length === 0) {
                            tbody.innerHTML = '<tr id="noReceivedRow"><td colspan="4" style="text-align:center; padding:30px; color:#64748b;">Aucun fichier reçu pour le moment.</td></tr>';
                        } else {
                            tbody.innerHTML = data.received_files.map(f => `
                                <tr>
                                    <td>
                                        <div class="file-name-cell">
                                            <img src="/static/icons/${f.icon}.svg" class="file-svg-icon" alt="${f.ext}">
                                            <span>${f.name}</span>
                                        </div>
                                    </td>
                                    <td class="file-size">${f.formatted_size}</td>
                                    <td class="file-date">${f.date_str}</td>
                                    <td>
                                        <div class="file-actions">
                                            <button class="btn-table-action" onclick="openLocalFile('${f.name}')">Ouvrir</button>
                                            <a href="/download_received/${f.name}" class="btn-table-action" download>Télécharger</a>
                                        </div>
                                    </td>
                                </tr>
                            `).join('');
                        }
                    }
                } catch (e) {}
            }

            // Polling automatique toutes les 1.2s
            setInterval(refreshTransfers, 1200);
        </script>
    </body>
    </html>
    """
    return render_template_string(html_transfers, received_files=received_files)

# Téléchargement d'un fichier reçu
@app.route('/download_received/<filename>')
def download_received_file(filename):
    """Téléchargement direct d'un fichier reçu."""
    safe_name = secure_filename(filename)
    path = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
    if not os.path.exists(path):
        return "Fichier introuvable", 404
    return send_file(path, as_attachment=True, download_name=safe_name)

# ==============================================
# NOUVELLE ROUTE POUR TÉLÉCHARGEMENT VIA POST
# ==============================================

@app.route('/download_file', methods=['GET', 'POST'])
def download_file_get_post():
    """Téléchargement via GET ou POST - gère les espaces et caractères spéciaux"""
    
    # Récupérer le chemin selon la méthode
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        filepath = data.get('filepath')
    else:
        # Méthode GET
        filepath = request.args.get('filepath')
    
    if not filepath:
        return jsonify({'error': 'Chemin manquant'}), 400
    
    # Nettoyer le chemin pour Windows
    if sys.platform == 'win32':
        filepath = filepath.replace('/', '\\')
    
    abs_path = os.path.abspath(filepath)
    
    if not os.path.exists(abs_path) or os.path.isdir(abs_path):
        return jsonify({'error': 'Fichier introuvable'}), 404
    
    filename = os.path.basename(abs_path)
    
    try:
        return send_file(
            abs_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/octet-stream'
        )
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==============================================
# APIS D'ÉTAT DE CONNEXION ET DE TRANSFERTS
# ==============================================

@app.route('/api/connection_status')
def api_connection_status():
    """Renvoie le statut de connexion pour la page QR code."""
    return jsonify({
        'connected': CONNECTED_CLIENT['connected'],
        'device': CONNECTED_CLIENT,
        'server_ip': get_local_ip(),
        'port': PORT,
        'active_transfers_count': len([t for t in ACTIVE_TRANSFERS.values() if t['status'] == 'running'])
    }), 200

@app.route('/api/client/connect', methods=['POST', 'GET'])
def api_client_connect():
    """Enregistre explicitement la connexion d'un client mobile."""
    client_ip = request.remote_addr
    ua = request.headers.get('User-Agent', '')
    
    # Récupérer d'éventuelles métadonnées envoyées en JSON
    body = request.get_json(silent=True) or {}
    custom_ua = body.get('userAgent', ua)
    
    dev_name = parse_device_name(custom_ua, client_ip)
    
    CONNECTED_CLIENT['connected'] = True
    CONNECTED_CLIENT['ip'] = client_ip
    CONNECTED_CLIENT['device_name'] = dev_name
    CONNECTED_CLIENT['last_seen'] = time.time()
    if not CONNECTED_CLIENT['connected_at']:
        CONNECTED_CLIENT['connected_at'] = time.time()
        
    return jsonify({
        'status': 'connected',
        'device': CONNECTED_CLIENT
    }), 200

@app.route('/api/client/disconnect', methods=['POST'])
def api_client_disconnect():
    """Réinitialise l'état de connexion de l'appareil."""
    CONNECTED_CLIENT['connected'] = False
    CONNECTED_CLIENT['ip'] = None
    CONNECTED_CLIENT['device_name'] = 'Aucun appareil'
    CONNECTED_CLIENT['connected_at'] = 0
    return jsonify({'status': 'disconnected'}), 200

@app.route('/api/transfers_status')
def api_transfers_status():
    """Renvoie les données en temps réel pour le centre de transferts."""
    return jsonify({
        'connected': CONNECTED_CLIENT['connected'],
        'device': CONNECTED_CLIENT,
        'active_transfers': list(ACTIVE_TRANSFERS.values()),
        'received_files': get_all_received_files(),
        'sent_files': TRANSFER_HISTORY['sent']
    }), 200

@app.route('/api/open_file', methods=['POST'])
def api_open_file():
    """Ouvre un fichier reçu avec le programme par défaut du système."""
    data = request.get_json(silent=True) or {}
    filename = data.get('filename')
    if not filename:
        return jsonify({'status': 'error', 'message': 'Nom manquant'}), 400
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(filename))
    if not os.path.exists(filepath):
        return jsonify({'status': 'error', 'message': 'Fichier introuvable'}), 404
    try:
        if sys.platform == 'win32':
            os.startfile(filepath)
        elif sys.platform == 'darwin':
            os.system(f'open "{filepath}"')
        else:
            os.system(f'xdg-open "{filepath}"')
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/open_folder', methods=['POST', 'GET'])
def api_open_folder():
    """Ouvre le dossier des réceptions dans l'explorateur du système."""
    folder = app.config['UPLOAD_FOLDER']
    try:
        if sys.platform == 'win32':
            os.startfile(folder)
        elif sys.platform == 'darwin':
            os.system(f'open "{folder}"')
        else:
            os.system(f'xdg-open "{folder}"')
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

# ==============================================
# API ET CORS POUR L'APPLICATION MOBILE & SCANNER
# ==============================================

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS, PUT, DELETE'
    response.headers['Access-Control-Allow-Headers'] = '*'
    # Supprimer les en-têtes restrictifs pour éviter ERR_BLOCKED_BY_RESPONSE dans les WebViews et applications mobiles
    response.headers.pop('X-Frame-Options', None)
    response.headers.pop('Content-Security-Policy', None)
    response.headers.pop('X-Content-Type-Options', None)
    return response

@app.route('/api/ping')
@app.route('/api/health')
def api_ping():
    """Vérification rapide de disponibilité pour l'app mobile"""
    return jsonify({
        'status': 'online',
        'app': 'PyDrop',
        'timestamp': time.time()
    }), 200

@app.route('/api/info')
def api_info():
    """Renvoie les informations sur l'ordinateur hôte pour l'auto-détection mobile (point d'accès, wifi, etc.)."""
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "Mon Ordinateur"
    
    all_ips = get_all_local_ips()
    default_ip = get_local_ip()
    hotspot_ip = next((ip for ip in all_ips if ip.startswith('192.168.137.') or ip.startswith('192.168.43.')), None)
    
    return jsonify({
        'status': 'online',
        'app': 'PyDrop',
        'hostname': hostname,
        'platform': sys.platform,
        'server_ip': default_ip,
        'server_ips': all_ips,
        'port': PORT,
        'is_hotspot': hotspot_ip is not None,
        'hotspot_ip': hotspot_ip,
        'timestamp': time.time()
    }), 200

# ==============================================
# ROUTES POUR TRANSFERT PC VERS TÉLÉPHONE
# ==============================================

@app.route('/api/session/start', methods=['POST'])
def start_session():
    """Crée une session pour le transfert PC->Téléphone"""
    session_id = str(uuid.uuid4())[:8]
    PENDING_FILES[session_id] = {
        'files': [],
        'timestamp': datetime.datetime.now().isoformat(),
        'accepted': False,
        'completed': False
    }
    return jsonify({'session_id': session_id, 'status': 'created'}), 200

@app.route('/api/session/status/<session_id>')
def session_status(session_id):
    """Vérifie le statut d'une session"""
    if session_id not in PENDING_FILES:
        return jsonify({'status': 'not_found'}), 404
    
    session = PENDING_FILES[session_id]
    files_info = []
    for f in session.get('files', []):
        files_info.append({
            'name': f.get('name', 'unknown'),
            'size': format_size(f.get('size', 0))
        })
    
    return jsonify({
        'status': 'pending' if not session['accepted'] else ('completed' if session['completed'] else 'accepted'),
        'files_count': len(session['files']),
        'files': files_info if session['accepted'] else []
    }), 200

@app.route('/api/session/accept/<session_id>', methods=['POST'])
def accept_session(session_id):
    """Le téléphone accepte la réception des fichiers"""
    if session_id not in PENDING_FILES:
        return jsonify({'error': 'Session not found'}), 404
    
    PENDING_FILES[session_id]['accepted'] = True
    return jsonify({'status': 'accepted'}), 200

@app.route('/api/session/reject/<session_id>', methods=['POST'])
def reject_session(session_id):
    """Le téléphone refuse la réception des fichiers"""
    if session_id not in PENDING_FILES:
        return jsonify({'error': 'Session not found'}), 404
    
    # Nettoyer les fichiers temporaires
    session = PENDING_FILES[session_id]
    for f in session.get('files', []):
        try:
            if os.path.exists(f['path']):
                os.remove(f['path'])
        except:
            pass
    
    # Supprimer le dossier de session
    session_dir = os.path.join(TEMP_TRANSFER_FOLDER, session_id)
    if os.path.exists(session_dir):
        try:
            shutil.rmtree(session_dir)
        except:
            pass
    
    if session_id in PENDING_FILES:
        del PENDING_FILES[session_id]
    return jsonify({'status': 'rejected'}), 200

@app.route('/api/upload_to_phone', methods=['POST'])
def upload_to_phone():
    """Reçoit les fichiers du PC et les prépare pour le téléphone"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    files = request.files.getlist('file')
    if not files:
        return jsonify({'error': 'No files selected'}), 400
    
    # Créer une session
    session_id = str(uuid.uuid4())[:8]
    
    # Sauvegarder les fichiers temporairement
    uploaded_files = []
    session_dir = os.path.join(TEMP_TRANSFER_FOLDER, session_id)
    if not os.path.exists(session_dir):
        os.makedirs(session_dir)
    
    for file in files:
        filename = secure_filename(file.filename or 'unnamed')
        temp_path = os.path.join(session_dir, filename)
        file.save(temp_path)
        
        file_size = os.path.getsize(temp_path)
        uploaded_files.append({
            'name': filename,
            'path': temp_path,
            'size': file_size
        })
    
    PENDING_FILES[session_id] = {
        'files': uploaded_files,
        'timestamp': datetime.datetime.now().isoformat(),
        'accepted': False,
        'completed': False
    }
    
    return jsonify({
        'session_id': session_id,
        'files': [{'name': f['name'], 'size': format_size(f['size'])} for f in uploaded_files],
        'message': 'Files ready for transfer. Waiting for phone confirmation.'
    }), 200

@app.route('/api/download_from_pc/<session_id>/<path:filename>')
def download_from_pc(session_id, filename):
    """Le téléphone télécharge les fichiers envoyés par le PC"""
    if session_id not in PENDING_FILES:
        return jsonify({'error': 'Session not found'}), 404
    
    session = PENDING_FILES[session_id]
    
    if not session['accepted']:
        return jsonify({'error': 'Session not accepted by phone'}), 403
    
    # Trouver le fichier
    file_info = None
    for f in session['files']:
        if f['name'] == filename:
            file_info = f
            break
    
    if not file_info:
        return jsonify({'error': 'File not found'}), 404
    
    if not os.path.exists(file_info['path']):
        return jsonify({'error': 'File no longer available'}), 404
    
    # Marquer comme complété
    session['completed'] = True
    
    return send_file(
        file_info['path'],
        as_attachment=True,
        download_name=filename,
        mimetype='application/octet-stream'
    )

@app.route('/api/session/cleanup/<session_id>', methods=['POST'])
def cleanup_session(session_id):
    """Nettoie les fichiers temporaires d'une session"""
    if session_id not in PENDING_FILES:
        return jsonify({'error': 'Session not found'}), 404
    
    session = PENDING_FILES[session_id]
    
    # Supprimer le dossier de session
    session_dir = os.path.join(TEMP_TRANSFER_FOLDER, session_id)
    if os.path.exists(session_dir):
        try:
            shutil.rmtree(session_dir)
        except:
            pass
    
    # Supprimer les références aux fichiers
    for f in session.get('files', []):
        try:
            if os.path.exists(f['path']):
                os.remove(f['path'])
        except:
            pass
    
    if session_id in PENDING_FILES:
        del PENDING_FILES[session_id]
    return jsonify({'status': 'cleaned'}), 200

@app.route('/phone')
def phone_interface():
    """Interface pour le téléphone - reçoit les fichiers du PC"""
    html = """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>PyDrop - Recevoir</title>
        <link rel="icon" type="image/png" href="/static/pydrop1.png">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                background: #0a0e1a;
                min-height: 100vh;
                display: flex;
                justify-content: center;
                align-items: center;
                padding: 16px;
                color: #e2e8f0;
                background-image: radial-gradient(ellipse at center, #0f1525 0%, #0a0e1a 100%);
            }

            .phone-container {
                max-width: 420px;
                width: 100%;
                background: linear-gradient(145deg, #1a1f2e 0%, #131725 100%);
                border-radius: 32px;
                padding: 30px 24px;
                border: 1px solid rgba(3, 102, 214, 0.15);
                box-shadow: 0 25px 50px -12px rgba(0,0,0,0.6);
                position: relative;
                overflow: hidden;
                min-height: 480px;
                display: flex;
                flex-direction: column;
                justify-content: center;
            }

            .phone-container::before {
                content: '';
                position: absolute;
                top: -50%;
                right: -50%;
                width: 100%;
                height: 100%;
                background: radial-gradient(circle, rgba(3, 102, 214, 0.05) 0%, transparent 70%);
                pointer-events: none;
            }

            @keyframes slideUp {
                from { opacity: 0; transform: translateY(30px); }
                to { opacity: 1; transform: translateY(0); }
            }

            @keyframes pulse {
                0%, 100% { transform: scale(1); }
                50% { transform: scale(1.05); }
            }

            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }

            @keyframes float {
                0%, 100% { transform: translateY(0px); }
                50% { transform: translateY(-8px); }
            }

            @keyframes shimmer {
                0% { background-position: -200% 0; }
                100% { background-position: 200% 0; }
            }

            .logo {
                text-align: center;
                margin-bottom: 16px;
                position: relative;
                z-index: 1;
            }
            .app-logo-img {
                width: 38px;
                height: 38px;
                object-fit: contain;
                border-radius: 9px;
                filter: drop-shadow(0 2px 8px rgba(3, 102, 214, 0.4));
                transition: transform 0.3s ease;
            }
            .logo:hover .app-logo-img {
                transform: scale(1.08) rotate(3deg);
            }

            .logo h1 {
                font-size: 2em;
                margin: 0;
                letter-spacing: -0.5px;
            }
            .logo h1 span:first-child { color: #0366d6; }
            .logo h1 span:last-child { color: #f68b1e; }
            .logo p {
                color: #8b92a8;
                font-size: 13px;
                margin-top: 2px;
                letter-spacing: 0.3px;
            }

            .status-icon {
                text-align: center;
                font-size: 72px;
                margin: 10px 0 8px;
                position: relative;
                z-index: 1;
                transition: all 0.5s ease;
            }

            .status-icon.pulse {
                animation: float 3s ease-in-out infinite;
            }

            .status-text {
                text-align: center;
                font-size: 20px;
                font-weight: 600;
                margin-bottom: 4px;
                position: relative;
                z-index: 1;
            }

            .status-sub {
                text-align: center;
                color: #8b92a8;
                font-size: 14px;
                margin-bottom: 16px;
                position: relative;
                z-index: 1;
            }

            .status-sub strong {
                color: #f68b1e;
                font-weight: 600;
            }

            .file-list {
                background: rgba(0, 0, 0, 0.3);
                border-radius: 16px;
                padding: 12px;
                margin-bottom: 16px;
                max-height: 220px;
                overflow-y: auto;
                position: relative;
                z-index: 1;
                border: 1px solid rgba(255,255,255,0.05);
            }

            .file-list::-webkit-scrollbar {
                width: 4px;
            }
            .file-list::-webkit-scrollbar-track {
                background: transparent;
            }
            .file-list::-webkit-scrollbar-thumb {
                background: #0366d6;
                border-radius: 10px;
            }

            .file-item {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 10px 12px;
                background: rgba(255,255,255,0.03);
                border-radius: 10px;
                margin-bottom: 6px;
                animation: slideUp 0.3s ease;
                transition: all 0.2s;
                border: 1px solid transparent;
            }

            .file-item:hover {
                background: rgba(255,255,255,0.06);
                border-color: rgba(3, 102, 214, 0.2);
            }

            .file-item:last-child { margin-bottom: 0; }
            .file-item .file-icon { 
                width: 40px; 
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
            }
            .file-item .file-icon .svg-icon {
                filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));
                transition: transform 0.2s ease;
            }
            .file-item:hover .file-icon .svg-icon {
                transform: scale(1.1);
            }
            .file-item .file-info { flex: 1; min-width: 0; }
            .file-item .file-name { 
                font-size: 14px; 
                font-weight: 500;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .file-item .file-size { font-size: 12px; color: #8b92a8; }

            .btn {
                display: block;
                width: 100%;
                padding: 15px;
                border: none;
                border-radius: 40px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                text-align: center;
                position: relative;
                z-index: 1;
                letter-spacing: 0.3px;
            }

            .btn:active {
                transform: scale(0.97);
            }

            .btn-primary {
                background: linear-gradient(135deg, #0366d6, #f68b1e);
                color: white;
                box-shadow: 0 4px 15px rgba(3, 102, 214, 0.3);
            }

            .btn-primary:hover {
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(3, 102, 214, 0.4);
            }

            .btn-success {
                background: linear-gradient(135deg, #43a047, #66bb6a);
                color: white;
                box-shadow: 0 4px 15px rgba(76, 175, 80, 0.3);
            }

            .btn-success:hover {
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(76, 175, 80, 0.4);
            }

            .btn-danger {
                background: linear-gradient(135deg, #e53935, #ef5350);
                color: white;
                box-shadow: 0 4px 15px rgba(244, 67, 54, 0.3);
            }

            .btn-danger:hover {
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(244, 67, 54, 0.4);
            }

            .btn-outline {
                background: rgba(255,255,255,0.05);
                color: #8b92a8;
                border: 1px solid rgba(255,255,255,0.08);
            }

            .btn-outline:hover {
                background: rgba(255,255,255,0.1);
                color: #e2e8f0;
            }

            .btn:disabled {
                opacity: 0.5;
                cursor: not-allowed;
                transform: none !important;
                box-shadow: none !important;
            }

            .hidden { display: none !important; }

            .session-id {
                text-align: center;
                font-size: 11px;
                color: #5a6278;
                margin-top: 12px;
                font-family: monospace;
                word-break: break-all;
                padding: 8px;
                background: rgba(0,0,0,0.2);
                border-radius: 8px;
                position: relative;
                z-index: 1;
                letter-spacing: 0.5px;
            }

            .session-id .label {
                color: #5a6278;
                font-size: 10px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }

            .progress-container {
                margin: 12px 0 16px;
                background: rgba(0,0,0,0.3);
                border-radius: 16px;
                padding: 16px 18px;
                position: relative;
                z-index: 1;
                border: 1px solid rgba(255,255,255,0.05);
            }

            .progress-bar-bg {
                background: #0a0e1a;
                border-radius: 12px;
                height: 8px;
                overflow: hidden;
                position: relative;
            }

            .progress-bar-fill {
                height: 100%;
                background: linear-gradient(90deg, #0366d6, #f68b1e);
                transition: width 0.5s cubic-bezier(0.4, 0, 0.2, 1);
                border-radius: 12px;
                width: 0%;
                position: relative;
            }

            .progress-bar-fill::after {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
                background-size: 200% 100%;
                animation: shimmer 2s infinite;
            }

            .progress-text {
                display: flex;
                justify-content: space-between;
                font-size: 12px;
                color: #8b92a8;
                margin-top: 10px;
            }

            .progress-text .filename { 
                font-weight: 500;
                color: #e2e8f0;
                max-width: 60%;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .btn-group {
                display: flex;
                gap: 10px;
                margin-top: 6px;
                position: relative;
                z-index: 1;
            }

            .btn-group .btn {
                flex: 1;
                padding: 13px;
                font-size: 14px;
            }

            .count-badge {
                display: inline-block;
                background: rgba(246, 139, 30, 0.15);
                color: #f68b1e;
                padding: 2px 12px;
                border-radius: 20px;
                font-size: 13px;
                font-weight: 500;
            }

            .checking-animation {
                display: inline-block;
                width: 20px;
                height: 20px;
                border: 3px solid rgba(3, 102, 214, 0.2);
                border-top: 3px solid #0366d6;
                border-radius: 50%;
                animation: spin 0.8s linear infinite;
                margin-right: 8px;
                vertical-align: middle;
            }

            @media (max-width: 400px) {
                .phone-container { padding: 20px 16px; min-height: 400px; }
                .status-icon { font-size: 56px; }
                .status-text { font-size: 18px; }
                .btn { padding: 13px; font-size: 15px; }
                .file-item { padding: 8px 10px; }
                .file-item .file-icon { font-size: 24px; width: 34px; }
            }
        </style>
    </head>
    <body>
        <div class="phone-container" id="app">
            <div class="logo">
                <div style="display:inline-flex;align-items:center;justify-content:center;gap:12px;margin-bottom:4px;">
                    <img src="/static/pydrop1.png" alt="PyDrop" class="app-logo-img">
                    <h1 style="margin:0;"><span>Py</span><span>Drop</span></h1>
                </div>
                <p><img src="/static/icons/smartphone.svg" class="svg-icon" style="width:16px;height:16px;vertical-align:-2px;margin-right:4px;" alt=""> Réception depuis le PC</p>
            </div>

            <!-- ÉTAT: ATTENTE -->
            <div id="stateWaiting">
                <div class="status-icon pulse"><img src="/static/icons/clock.svg" class="svg-icon-xl" alt=""></div>
                <div class="status-text">En attente de fichiers</div>
                <div class="status-sub">Le PC va envoyer des fichiers vers votre téléphone</div>
                <div style="text-align:center;margin:10px 0 16px;">
                    <span class="checking-animation"></span>
                    <span style="color:#5a6278;font-size:13px;">Vérification automatique...</span>
                </div>
                <button class="btn btn-primary" onclick="checkSession()">
                    <img src="/static/icons/refresh-cw.svg" class="svg-icon" style="width:16px;height:16px;vertical-align:-3px;margin-right:6px;" alt=""> Vérifier maintenant
                </button>
            </div>

            <!-- ÉTAT: FICHIERS REÇUS -->
            <div id="stateReceived" class="hidden">
                <div class="status-icon pulse" style="animation-duration: 1.5s;"><img src="/static/icons/download.svg" class="svg-icon-xl" alt=""></div>
                <div class="status-text">Fichiers reçus !</div>
                <div class="status-sub">
                    <span class="count-badge" id="filesCount">0</span> fichier(s) prêt(s) à être téléchargé(s)
                </div>
                <div class="file-list" id="fileList"></div>
                <div class="btn-group">
                    <button class="btn btn-success" id="acceptBtn" onclick="acceptFiles()">
                        <img src="/static/icons/download.svg" class="svg-icon" style="width:18px;height:18px;vertical-align:-3px;margin-right:6px;" alt=""> Télécharger
                    </button>
                    <button class="btn btn-outline" id="rejectBtn" onclick="rejectFiles()">
                        <img src="/static/icons/x.svg" class="svg-icon" style="width:18px;height:18px;vertical-align:-3px;margin-right:6px;" alt=""> Refuser
                    </button>
                </div>
            </div>

            <!-- ÉTAT: TÉLÉCHARGEMENT -->
            <div id="stateDownloading" class="hidden">
                <div class="status-icon" style="animation: none;"><img src="/static/icons/download.svg" class="svg-icon-xl" alt=""></div>
                <div class="status-text">Téléchargement en cours...</div>
                <div class="status-sub">Veuillez patienter</div>
                <div class="progress-container">
                    <div class="progress-bar-bg">
                        <div class="progress-bar-fill" id="downloadProgressBar"></div>
                    </div>
                    <div class="progress-text">
                        <span class="filename" id="progressFileName">-</span>
                        <span id="progressPercent">0%</span>
                    </div>
                </div>
                <div style="text-align:center; color:#5a6278; font-size:12px;">
                    <span id="progressFiles">0</span> / <span id="totalFiles">0</span> fichiers
                </div>
            </div>

            <!-- ÉTAT: TERMINÉ -->
            <div id="stateCompleted" class="hidden">
                <div class="status-icon" style="animation: none;"><img src="/static/icons/check-circle.svg" class="svg-icon-xl" style="color:#22c55e;" alt=""></div>
                <div class="status-text">Transfert terminé !</div>
                <div class="status-sub" id="completedMsg">Tous les fichiers ont été téléchargés avec succès</div>
                <button class="btn btn-primary" onclick="resetState()">
                    <img src="/static/icons/refresh-cw.svg" class="svg-icon" style="width:16px;height:16px;vertical-align:-3px;margin-right:6px;" alt=""> Prêt pour un autre transfert
                </button>
            </div>

            <!-- ÉTAT: REFUSÉ -->
            <div id="stateRejected" class="hidden">
                <div class="status-icon" style="animation: none;"><img src="/static/icons/x-circle.svg" class="svg-icon-xl" style="color:#ef4444;" alt=""></div>
                <div class="status-text">Transfert refusé</div>
                <div class="status-sub">Vous avez refusé la réception des fichiers</div>
                <button class="btn btn-primary" onclick="resetState()">
                    <img src="/static/icons/refresh-cw.svg" class="svg-icon" style="width:16px;height:16px;vertical-align:-3px;margin-right:6px;" alt=""> Prêt pour un autre transfert
                </button>
            </div>

            <!-- ÉTAT: EXPIRÉ -->
            <div id="stateExpired" class="hidden">
                <div class="status-icon" style="animation: none;"><img src="/static/icons/clock.svg" class="svg-icon-xl" style="color:#f59e0b;" alt=""></div>
                <div class="status-text">Session expirée</div>
                <div class="status-sub">Le délai pour accepter les fichiers est dépassé</div>
                <button class="btn btn-primary" onclick="resetState()">
                    <img src="/static/icons/refresh-cw.svg" class="svg-icon" style="width:16px;height:16px;vertical-align:-3px;margin-right:6px;" alt=""> Prêt pour un autre transfert
                </button>
            </div>

            <!-- ÉTAT: ERREUR -->
            <div id="stateError" class="hidden">
                <div class="status-icon" style="animation: none;"><img src="/static/icons/alert-triangle.svg" class="svg-icon-xl" style="color:#ef4444;" alt=""></div>
                <div class="status-text">Une erreur est survenue</div>
                <div class="status-sub" id="errorMsg">-</div>
                <button class="btn btn-primary" onclick="resetState()">
                    <img src="/static/icons/refresh-cw.svg" class="svg-icon" style="width:16px;height:16px;vertical-align:-3px;margin-right:6px;" alt=""> Réessayer
                </button>
            </div>

            <div class="session-id">
                <div class="label">ID de session</div>
                <div id="sessionDisplay">-</div>
            </div>
        </div>

        <script>
            let currentSessionId = null;
            let currentFiles = [];
            let isProcessing = false;
            let isDownloading = false;

            function getSessionIdFromUrl() {
                const params = new URLSearchParams(window.location.search);
                return params.get('session');
            }

            function setState(state) {
                const states = ['Waiting', 'Received', 'Downloading', 'Completed', 'Rejected', 'Expired', 'Error'];
                states.forEach(s => {
                    const el = document.getElementById('state' + s);
                    if (el) {
                        if (s === state) {
                            el.classList.remove('hidden');
                        } else {
                            el.classList.add('hidden');
                        }
                    }
                });
            }

            async function checkSession() {
                if (isProcessing) return;
                isProcessing = true;

                const sessionId = getSessionIdFromUrl();
                if (!sessionId) {
                    setState('Waiting');
                    document.getElementById('sessionDisplay').textContent = 'En attente...';
                    isProcessing = false;
                    return;
                }

                currentSessionId = sessionId;
                document.getElementById('sessionDisplay').textContent = sessionId;

                try {
                    const response = await fetch('/api/session/status/' + sessionId);
                    const data = await response.json();

                    if (response.status === 404) {
                        setState('Expired');
                        isProcessing = false;
                        return;
                    }

                    if (data.status === 'pending') {
                        if (data.files_count > 0) {
                            setState('Received');
                            currentFiles = data.files;
                            renderFileList(data.files);
                            document.getElementById('filesCount').textContent = data.files_count;
                        } else {
                            setState('Waiting');
                        }
                    } else if (data.status === 'accepted') {
                        setState('Downloading');
                        await downloadFiles();
                    } else if (data.status === 'completed') {
                        setState('Completed');
                        document.getElementById('completedMsg').textContent = 
                            'Tous les fichiers ont été téléchargés avec succès !';
                    } else {
                        setState('Waiting');
                    }
                } catch (error) {
                    console.error('Error checking session:', error);
                    setState('Error');
                    document.getElementById('errorMsg').textContent = 'Impossible de contacter le serveur';
                }

                isProcessing = false;
            }

            function renderFileList(files) {
                const container = document.getElementById('fileList');
                if (!files || files.length === 0) {
                    container.innerHTML = '<div style="text-align:center;color:#5a6278;padding:20px;">Aucun fichier</div>';
                    return;
                }
                container.innerHTML = files.map((f, i) => `
                    <div class="file-item" style="animation-delay: ${i * 0.05}s">
                        <span class="file-icon">${getFileIcon(f.name)}</span>
                        <div class="file-info">
                            <div class="file-name">${escapeHtml(f.name)}</div>
                            <div class="file-size">${f.size || '?'}</div>
                        </div>
                    </div>
                `).join('');
            }

            function getFileIcon(filename, type = 'item') {
                if (!filename) {
                    const sz = type === 'card' ? '40px' : '22px';
                    return `<img src="/static/icons/file.svg" class="svg-icon" style="width:${sz};height:${sz};" alt="file">`;
                }
                const ext = filename.split('.').pop().toLowerCase();
                const map = {
                    'jpg': 'image', 'jpeg': 'image', 'png': 'image', 'gif': 'image', 'webp': 'image', 'svg': 'image', 'bmp': 'image', 'ico': 'image', 'tiff': 'image', 'psd': 'image', 'ai': 'image',
                    'mp4': 'video', 'mkv': 'video', 'avi': 'video', 'mov': 'video', 'wmv': 'video', 'webm': 'video', 'm4v': 'video', 'flv': 'video', '3gp': 'video', 'ts': 'video',
                    'mp3': 'music', 'wav': 'music', 'flac': 'music', 'aac': 'music', 'ogg': 'music', 'm4a': 'music', 'wma': 'music', 'opus': 'music', 'mid': 'music', 'midi': 'music',
                    'pdf': 'file-pdf',
                    'doc': 'file-doc', 'docx': 'file-doc', 'odt': 'file-doc', 'rtf': 'file-doc', 'dot': 'file-doc', 'dotx': 'file-doc',
                    'xls': 'file-spreadsheet', 'xlsx': 'file-spreadsheet', 'csv': 'file-spreadsheet', 'ods': 'file-spreadsheet', 'tsv': 'file-spreadsheet', 'xlsm': 'file-spreadsheet',
                    'ppt': 'file-presentation', 'pptx': 'file-presentation', 'odp': 'file-presentation', 'pps': 'file-presentation', 'ppsx': 'file-presentation',
                    'py': 'file-python', 'pyw': 'file-python', 'ipynb': 'file-python',
                    'php': 'file-php',
                    'cs': 'file-cs',
                    'c': 'file-cpp', 'cpp': 'file-cpp', 'cc': 'file-cpp', 'cxx': 'file-cpp', 'h': 'file-cpp', 'hpp': 'file-cpp',
                    'java': 'file-java', 'class': 'file-java', 'jar': 'file-java',
                    'js': 'file-js', 'mjs': 'file-js', 'cjs': 'file-js', 'jsx': 'file-js',
                    'ts': 'file-ts', 'tsx': 'file-ts',
                    'html': 'file-html', 'htm': 'file-html', 'xhtml': 'file-html', 'vue': 'file-html',
                    'css': 'file-css', 'scss': 'file-css', 'sass': 'file-css', 'less': 'file-css',
                    'json': 'file-json', 'xml': 'file-json', 'yaml': 'file-json', 'yml': 'file-json', 'toml': 'file-json', 'ini': 'file-json', 'env': 'file-json', 'config': 'file-json', 'lock': 'file-json',
                    'sql': 'file-sql',
                    'sh': 'file-sh', 'bash': 'file-sh', 'zsh': 'file-sh', 'bat': 'file-sh', 'ps1': 'file-sh', 'cmd': 'file-sh',
                    'rs': 'file-rs', 'go': 'file-go', 'rb': 'file-rb',
                    'swift': 'file-swift', 'kt': 'file-swift', 'kts': 'file-swift',
                    'zip': 'file-archive', 'rar': 'file-archive', '7z': 'file-archive', 'tar': 'file-archive', 'gz': 'file-archive', 'xz': 'file-archive', 'bz2': 'file-archive', 'tgz': 'file-archive',
                    'txt': 'file-text', 'md': 'file-text', 'log': 'file-text',
                    'iso': 'disc', 'dmg': 'disc', 'img': 'disc', 'vhd': 'disc',
                    'exe': 'settings', 'msi': 'settings', 'deb': 'settings', 'rpm': 'settings',
                    'apk': 'smartphone', 'aab': 'smartphone', 'ipa': 'smartphone'
                };
                const icon = map[ext] || 'file';
                const sz = type === 'card' ? '40px' : '22px';
                return `<img src="/static/icons/${icon}.svg" class="svg-icon" style="width:${sz};height:${sz};" alt="${ext}">`;
            }

            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }

            async function acceptFiles() {
                if (!currentSessionId) return;

                try {
                    const response = await fetch('/api/session/accept/' + currentSessionId, {
                        method: 'POST'
                    });
                    const data = await response.json();

                    if (data.status === 'accepted') {
                        setState('Downloading');
                        await downloadFiles();
                    } else {
                        setState('Error');
                        document.getElementById('errorMsg').textContent = 'Erreur lors de l'acceptation';
                    }
                } catch (error) {
                    console.error('Error accepting files:', error);
                    setState('Error');
                    document.getElementById('errorMsg').textContent = 'Erreur réseau';
                }
            }

            async function rejectFiles() {
                if (!currentSessionId) return;

                try {
                    await fetch('/api/session/reject/' + currentSessionId, {
                        method: 'POST'
                    });
                    setState('Rejected');
                } catch (error) {
                    console.error('Error rejecting files:', error);
                }
            }

            async function downloadFiles() {
                if (isDownloading) return;
                if (!currentSessionId || currentFiles.length === 0) {
                    setState('Error');
                    document.getElementById('errorMsg').textContent = 'Aucun fichier à télécharger';
                    return;
                }

                isDownloading = true;
                const progressBar = document.getElementById('downloadProgressBar');
                const progressPercent = document.getElementById('progressPercent');
                const progressFileName = document.getElementById('progressFileName');
                const progressFiles = document.getElementById('progressFiles');
                const totalFiles = document.getElementById('totalFiles');

                totalFiles.textContent = currentFiles.length;
                let downloaded = 0;

                for (let i = 0; i < currentFiles.length; i++) {
                    const file = currentFiles[i];
                    progressFileName.innerHTML = '<img src="/static/icons/download.svg" class="svg-icon" style="width:14px;height:14px;vertical-align:-2px;margin-right:4px;"> ' + escapeHtml(file.name);
                    progressFiles.textContent = i + 1;

                    try {
                        const response = await fetch('/api/download_from_pc/' + currentSessionId + '/' + 
                            encodeURIComponent(file.name));

                        if (!response.ok) {
                            const errorData = await response.json().catch(() => ({}));
                            throw new Error(errorData.error || 'Erreur HTTP ' + response.status);
                        }

                        const blob = await response.blob();
                        const url = window.URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = file.name;
                        document.body.appendChild(a);
                        a.click();
                        a.remove();
                        window.URL.revokeObjectURL(url);

                        downloaded++;
                        const pct = Math.round((downloaded / currentFiles.length) * 100);
                        progressBar.style.width = pct + '%';
                        progressPercent.textContent = pct + '%';

                        await new Promise(resolve => setTimeout(resolve, 300));

                    } catch (error) {
                        console.error('Error downloading file:', error);
                        setState('Error');
                        document.getElementById('errorMsg').textContent = 'Erreur: ' + error.message;
                        isDownloading = false;
                        return;
                    }
                }

                progressFileName.innerHTML = '<img src="/static/icons/check-circle.svg" class="svg-icon" style="width:14px;height:14px;vertical-align:-2px;margin-right:4px;color:#22c55e;"> Terminé !';
                progressFiles.textContent = currentFiles.length;
                setState('Completed');
                document.getElementById('completedMsg').textContent = 
                    downloaded + ' fichier' + (downloaded > 1 ? 's' : '') + ' téléchargé' + (downloaded > 1 ? 's' : '') + ' avec succès !';

                try {
                    await fetch('/api/session/cleanup/' + currentSessionId, { method: 'POST' });
                } catch (e) {}

                isDownloading = false;
            }

            function resetState() {
                currentSessionId = null;
                currentFiles = [];
                isDownloading = false;
                setState('Waiting');
                document.getElementById('sessionDisplay').textContent = 'En attente...';
                
                const url = new URL(window.location);
                url.searchParams.delete('session');
                window.history.replaceState({}, '', url);
            }

            // Auto-refresh toutes les 3 secondes
            let autoRefreshInterval = null;

            function startAutoRefresh() {
                if (autoRefreshInterval) clearInterval(autoRefreshInterval);
                autoRefreshInterval = setInterval(() => {
                    const stateEl = document.querySelector('#app > div:not(.hidden)');
                    if (stateEl && (stateEl.id === 'stateWaiting' || stateEl.id === 'stateReceived')) {
                        checkSession();
                    }
                }, 3000);
            }

            // Pull to refresh
            let startY = 0;
            document.addEventListener('touchstart', (e) => {
                startY = e.touches[0].clientY;
            }, { passive: true });

            document.addEventListener('touchend', (e) => {
                const endY = e.changedTouches[0].clientY;
                const stateEl = document.querySelector('#app > div:not(.hidden)');
                if (endY - startY > 120 && stateEl && stateEl.id === 'stateWaiting') {
                    checkSession();
                }
            }, { passive: true });

            // Initialisation
            document.addEventListener('DOMContentLoaded', function() {
                const sessionId = getSessionIdFromUrl();
                if (sessionId) {
                    currentSessionId = sessionId;
                    document.getElementById('sessionDisplay').textContent = sessionId;
                    checkSession();
                } else {
                    setState('Waiting');
                }
                startAutoRefresh();
            });
        </script>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/send_to_phone')
def send_to_phone():
    """Interface pour envoyer des fichiers du PC vers le téléphone"""
    html = """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
        <title>PyDrop - Envoyer au téléphone</title>
        <link rel="icon" type="image/png" href="{{ url_for('static', filename='pydrop1.png') }}">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }

            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                background: #0a0e1a;
                min-height: 100vh;
                padding: 20px;
                color: #e2e8f0;
            }

            .container {
                max-width: 900px;
                margin: 0 auto;
            }

            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(20px); }
                to { opacity: 1; transform: translateY(0); }
            }

            @keyframes pulse {
                0%, 100% { transform: scale(1); }
                50% { transform: scale(1.03); }
            }

            @keyframes float {
                0%, 100% { transform: translateY(0px); }
                50% { transform: translateY(-8px); }
            }

            @keyframes shimmer {
                0% { background-position: -200% 0; }
                100% { background-position: 200% 0; }
            }

            .header {
                background: linear-gradient(145deg, #1a1f2e 0%, #131725 100%);
                border-radius: 24px;
                padding: 20px 28px;
                margin-bottom: 24px;
                border: 1px solid rgba(3, 102, 214, 0.15);
                display: flex;
                align-items: center;
                justify-content: space-between;
                flex-wrap: wrap;
                gap: 12px;
                animation: fadeIn 0.4s ease;
            }

            .logo-area {
                display: flex;
                align-items: center;
                gap: 12px;
            }
            .app-logo-img {
                width: 38px;
                height: 38px;
                object-fit: contain;
                border-radius: 9px;
                filter: drop-shadow(0 2px 8px rgba(3, 102, 214, 0.4));
                transition: transform 0.3s ease;
            }
            .logo-area:hover .app-logo-img {
                transform: scale(1.08) rotate(3deg);
            }

            .logo-area h1 {
                font-size: 1.8em;
                margin: 0;
                letter-spacing: -0.5px;
            }
            .logo-area h1 span:first-child { color: #0366d6; }
            .logo-area h1 span:last-child { color: #f68b1e; }

            .header-actions {
                display: flex;
                align-items: center;
                gap: 12px;
                flex-wrap: wrap;
            }

            .btn-back {
                color: #8b92a8;
                text-decoration: none;
                padding: 8px 18px;
                border-radius: 40px;
                border: 1px solid rgba(255,255,255,0.08);
                transition: all 0.3s;
                font-size: 14px;
                display: inline-flex;
                align-items: center;
                gap: 6px;
            }

            .btn-back:hover {
                border-color: #0366d6;
                color: #0366d6;
                background: rgba(3, 102, 214, 0.05);
            }

            .status-badge {
                display: inline-block;
                padding: 6px 16px;
                border-radius: 30px;
                font-size: 13px;
                font-weight: 500;
            }

            .status-badge.waiting {
                background: rgba(255, 152, 0, 0.15);
                color: #ff9800;
                border: 1px solid rgba(255, 152, 0, 0.2);
            }

            .status-badge.accepted {
                background: rgba(76, 175, 80, 0.15);
                color: #4caf50;
                border: 1px solid rgba(76, 175, 80, 0.2);
            }

            .status-badge.completed {
                background: rgba(3, 102, 214, 0.15);
                color: #0366d6;
                border: 1px solid rgba(3, 102, 214, 0.2);
            }

            .status-badge.rejected {
                background: rgba(244, 67, 54, 0.15);
                color: #f44336;
                border: 1px solid rgba(244, 67, 54, 0.2);
            }

            .status-badge.sending {
                background: rgba(3, 102, 214, 0.2);
                color: #0366d6;
                border: 1px solid rgba(3, 102, 214, 0.3);
                animation: pulse 1.5s ease-in-out infinite;
            }

            /* DROP ZONE */
            .drop-zone {
                background: linear-gradient(145deg, #1a1f2e 0%, #131725 100%);
                border-radius: 24px;
                padding: 50px 30px;
                border: 3px dashed rgba(3, 102, 214, 0.25);
                text-align: center;
                transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
                cursor: pointer;
                margin-bottom: 20px;
                animation: fadeIn 0.5s ease;
                position: relative;
                overflow: hidden;
            }

            .drop-zone::before {
                content: '';
                position: absolute;
                top: -50%;
                left: -50%;
                width: 200%;
                height: 200%;
                background: radial-gradient(circle at center, rgba(3, 102, 214, 0.03) 0%, transparent 70%);
                transition: all 0.6s;
                opacity: 0;
            }

            .drop-zone:hover::before {
                opacity: 1;
            }

            .drop-zone:hover {
                border-color: rgba(3, 102, 214, 0.5);
                transform: translateY(-2px);
                box-shadow: 0 8px 30px rgba(3, 102, 214, 0.08);
            }

            .drop-zone.drag-over {
                border-color: #f68b1e;
                background: rgba(246, 139, 30, 0.05);
                transform: scale(1.01);
                box-shadow: 0 8px 40px rgba(246, 139, 30, 0.1);
            }

            .drop-zone.drag-over .drop-zone-icon {
                animation: float 1s ease-in-out infinite;
            }

            .drop-zone-icon {
                font-size: 64px;
                margin-bottom: 16px;
                display: block;
                transition: all 0.3s;
            }

            .drop-zone-title {
                font-size: 22px;
                font-weight: 600;
                margin-bottom: 8px;
                background: linear-gradient(135deg, #e2e8f0, #8b92a8);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }

            .drop-zone-sub {
                color: #8b92a8;
                font-size: 14px;
            }

            .drop-zone input[type="file"] {
                display: none;
            }

            .drop-zone-hint {
                margin-top: 12px;
                display: flex;
                justify-content: center;
                gap: 20px;
                flex-wrap: wrap;
                font-size: 12px;
                color: #5a6278;
            }

            .drop-zone-hint span {
                display: inline-flex;
                align-items: center;
                gap: 4px;
            }

            /* FILE PREVIEW */
            .file-preview-wrapper {
                background: linear-gradient(145deg, #1a1f2e 0%, #131725 100%);
                border-radius: 20px;
                padding: 20px;
                margin-bottom: 20px;
                border: 1px solid rgba(3, 102, 214, 0.1);
                animation: fadeIn 0.4s ease;
            }

            .file-preview-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 14px;
                flex-wrap: wrap;
                gap: 10px;
            }

            .file-preview-header .count {
                font-size: 14px;
                color: #8b92a8;
            }

            .file-preview-header .count strong {
                color: #e2e8f0;
            }

            .file-preview {
                max-height: 260px;
                overflow-y: auto;
                padding-right: 4px;
            }

            .file-preview::-webkit-scrollbar {
                width: 4px;
            }
            .file-preview::-webkit-scrollbar-track {
                background: transparent;
            }
            .file-preview::-webkit-scrollbar-thumb {
                background: #0366d6;
                border-radius: 10px;
            }

            .file-preview-item {
                display: flex;
                align-items: center;
                gap: 12px;
                padding: 10px 12px;
                background: rgba(255,255,255,0.03);
                border-radius: 10px;
                margin-bottom: 6px;
                animation: fadeIn 0.3s ease;
                transition: all 0.2s;
                border: 1px solid transparent;
            }

            .file-preview-item:hover {
                background: rgba(255,255,255,0.06);
                border-color: rgba(3, 102, 214, 0.15);
            }

            .file-preview-item .icon { 
                width: 40px; 
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
            }
            .file-preview-item .icon .svg-icon {
                filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));
                transition: transform 0.2s ease;
            }
            .file-preview-item:hover .icon .svg-icon {
                transform: scale(1.1);
            }
            .file-preview-item .info { flex: 1; min-width: 0; }
            .file-preview-item .name {
                font-size: 14px;
                font-weight: 500;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .file-preview-item .size { font-size: 12px; color: #8b92a8; }
            .file-preview-item .remove {
                background: rgba(244, 67, 54, 0.15);
                border: none;
                color: #f44336;
                width: 30px;
                height: 30px;
                border-radius: 50%;
                cursor: pointer;
                font-size: 14px;
                transition: all 0.2s;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .file-preview-item .remove:hover {
                background: #f44336;
                color: white;
                transform: scale(1.05);
            }

            .actions {
                display: flex;
                gap: 12px;
                flex-wrap: wrap;
                justify-content: center;
                margin-top: 4px;
            }

            .btn {
                padding: 14px 32px;
                border: none;
                border-radius: 40px;
                font-size: 15px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                display: inline-flex;
                align-items: center;
                gap: 10px;
                letter-spacing: 0.2px;
            }

            .btn:active {
                transform: scale(0.97);
            }

            .btn-primary {
                background: linear-gradient(135deg, #0366d6, #f68b1e);
                color: white;
                box-shadow: 0 4px 20px rgba(3, 102, 214, 0.25);
            }

            .btn-primary:hover {
                transform: translateY(-2px);
                box-shadow: 0 8px 30px rgba(3, 102, 214, 0.35);
            }

            .btn-primary:disabled {
                opacity: 0.5;
                cursor: not-allowed;
                transform: none !important;
                box-shadow: none !important;
            }

            .btn-secondary {
                background: rgba(255,255,255,0.06);
                color: #e2e8f0;
                border: 1px solid rgba(255,255,255,0.08);
            }

            .btn-secondary:hover {
                background: rgba(255,255,255,0.12);
                transform: translateY(-2px);
            }

            .btn-danger {
                background: rgba(244, 67, 54, 0.15);
                color: #f44336;
                border: 1px solid rgba(244, 67, 54, 0.2);
            }

            .btn-danger:hover {
                background: #f44336;
                color: white;
                transform: translateY(-2px);
            }

            .btn-small {
                padding: 8px 16px;
                font-size: 13px;
            }

            .hidden { display: none !important; }

            /* SESSION INFO */
            .session-info {
                background: linear-gradient(145deg, #1a1f2e 0%, #131725 100%);
                border-radius: 20px;
                padding: 18px 24px;
                margin-top: 20px;
                border: 1px solid rgba(3, 102, 214, 0.1);
                animation: fadeIn 0.5s ease;
                display: flex;
                align-items: center;
                justify-content: space-between;
                flex-wrap: wrap;
                gap: 12px;
            }

            .session-info .label {
                color: #8b92a8;
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }

            .session-info .value {
                font-family: monospace;
                color: #f68b1e;
                font-size: 15px;
                font-weight: 500;
            }

            .session-info .status-text {
                color: #8b92a8;
                font-size: 13px;
            }

            .copy-btn {
                background: rgba(3, 102, 214, 0.15);
                border: none;
                color: #0366d6;
                padding: 6px 16px;
                border-radius: 30px;
                cursor: pointer;
                font-size: 13px;
                font-weight: 500;
                transition: all 0.2s;
                display: inline-flex;
                align-items: center;
                gap: 6px;
            }

            .copy-btn:hover {
                background: #0366d6;
                color: white;
            }

            /* QR SECTION */
            .qr-section {
                background: linear-gradient(145deg, #1a1f2e 0%, #131725 100%);
                border-radius: 24px;
                padding: 28px 30px;
                margin-top: 24px;
                border: 1px solid rgba(3, 102, 214, 0.1);
                text-align: center;
                animation: fadeIn 0.6s ease;
            }

            .qr-section h3 {
                font-size: 18px;
                margin-bottom: 16px;
                color: #e2e8f0;
            }

            .qr-section .sub {
                color: #8b92a8;
                font-size: 13px;
                margin-bottom: 16px;
            }

            .qr-code-container {
                display: inline-block;
                background: white;
                padding: 16px;
                border-radius: 20px;
                margin-bottom: 16px;
                box-shadow: 0 8px 30px rgba(0,0,0,0.3);
                transition: all 0.3s;
            }

            .qr-code-container:hover {
                transform: scale(1.02);
            }

            .qr-code-container img {
                width: 200px;
                height: 200px;
                display: block;
            }

            .qr-url {
                font-family: monospace;
                font-size: 14px;
                color: #f68b1e;
                word-break: break-all;
                background: rgba(0,0,0,0.3);
                padding: 10px 16px;
                border-radius: 12px;
                display: inline-block;
                max-width: 100%;
                margin-bottom: 12px;
            }

            .qr-actions {
                display: flex;
                gap: 10px;
                justify-content: center;
                flex-wrap: wrap;
            }

            .qr-actions .btn {
                padding: 10px 20px;
                font-size: 13px;
            }

            /* NOTIFICATION */
            .notification {
                position: fixed;
                bottom: 24px;
                left: 50%;
                transform: translateX(-50%);
                padding: 14px 28px;
                border-radius: 16px;
                background: linear-gradient(145deg, #1a1f2e 0%, #131725 100%);
                border: 1px solid rgba(3, 102, 214, 0.25);
                color: #e2e8f0;
                font-size: 14px;
                box-shadow: 0 12px 40px rgba(0,0,0,0.6);
                display: none;
                z-index: 999;
                max-width: 90%;
                text-align: center;
                animation: fadeIn 0.3s ease;
                backdrop-filter: blur(10px);
            }

            .notification.success { border-color: rgba(76, 175, 80, 0.3); }
            .notification.error { border-color: rgba(244, 67, 54, 0.3); }
            .notification.warning { border-color: rgba(255, 152, 0, 0.3); }

            /* SUCCESS MODAL & PROGRESS BAR */
            .success-modal-overlay {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(4, 7, 16, 0.85);
                backdrop-filter: blur(12px);
                -webkit-backdrop-filter: blur(12px);
                align-items: center;
                justify-content: center;
                z-index: 2500;
                opacity: 0;
                transition: opacity 0.3s ease;
            }
            .success-modal-overlay.active {
                display: flex;
                opacity: 1;
            }
            .success-modal-card {
                background: linear-gradient(145deg, #192032 0%, #101524 100%);
                border-radius: 28px;
                max-width: 440px;
                width: 92%;
                padding: 32px 28px;
                text-align: center;
                position: relative;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(34, 197, 94, 0.3);
                transform: scale(0.85) translateY(20px);
                transition: transform 0.35s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            }
            .success-modal-overlay.active .success-modal-card {
                transform: scale(1) translateY(0);
            }
            .success-modal-close-btn {
                position: absolute;
                top: 16px;
                right: 16px;
                width: 32px;
                height: 32px;
                border-radius: 50%;
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.1);
                color: #8b92a8;
                font-size: 14px;
                display: flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                transition: all 0.2s;
            }
            .success-modal-close-btn:hover {
                background: rgba(255, 255, 255, 0.18);
                color: white;
                transform: scale(1.08);
            }
            .success-icon-wrap {
                width: 80px;
                height: 80px;
                margin: 0 auto 20px;
                position: relative;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .success-icon-glow {
                position: absolute;
                width: 80px;
                height: 80px;
                border-radius: 50%;
                background: radial-gradient(circle, rgba(34, 197, 94, 0.4) 0%, rgba(34, 197, 94, 0) 70%);
                animation: successPulse 2s infinite ease-in-out;
            }
            @keyframes successPulse {
                0%, 100% { transform: scale(0.9); opacity: 0.6; }
                50% { transform: scale(1.3); opacity: 0.2; }
            }
            .success-checkmark-svg {
                width: 72px;
                height: 72px;
                border-radius: 50%;
                display: block;
                stroke-width: 3.5;
                stroke: #22c55e;
                stroke-miterlimit: 10;
                box-shadow: inset 0px 0px 0px #22c55e;
            }
            .success-checkmark-circle {
                stroke-dasharray: 166;
                stroke-dashoffset: 166;
                stroke-width: 3.5;
                stroke-miterlimit: 10;
                stroke: #22c55e;
                fill: none;
                animation: strokeCircle 0.6s cubic-bezier(0.65, 0, 0.45, 1) forwards;
            }
            .success-checkmark-check {
                transform-origin: 50% 50%;
                stroke-dasharray: 48;
                stroke-dashoffset: 48;
                stroke-width: 3.5;
                stroke: #22c55e;
                fill: none;
                stroke-linecap: round;
                stroke-linejoin: round;
                animation: strokeCheck 0.4s cubic-bezier(0.65, 0, 0.45, 1) 0.5s forwards;
            }
            @keyframes strokeCircle {
                100% { stroke-dashoffset: 0; }
            }
            @keyframes strokeCheck {
                100% { stroke-dashoffset: 0; }
            }
            .success-modal-title {
                font-size: 22px;
                font-weight: 700;
                color: #ffffff;
                margin-bottom: 8px;
            }
            .success-modal-message {
                font-size: 15px;
                color: #94a3b8;
                line-height: 1.5;
                margin-bottom: 20px;
            }
            .success-modal-message strong {
                color: #38bdf8;
                font-weight: 600;
            }
            .success-file-card {
                background: rgba(10, 14, 26, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 16px;
                padding: 12px 16px;
                display: flex;
                align-items: center;
                gap: 12px;
                margin-bottom: 24px;
                text-align: left;
            }
            .success-file-icon {
                font-size: 28px;
                display: flex;
                align-items: center;
                justify-content: center;
                width: 44px;
                height: 44px;
                border-radius: 12px;
                background: rgba(3, 102, 214, 0.15);
                border: 1px solid rgba(3, 102, 214, 0.3);
                flex-shrink: 0;
            }
            .success-file-info {
                flex: 1;
                min-width: 0;
            }
            .success-file-name {
                font-size: 14px;
                font-weight: 600;
                color: #f1f5f9;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                display: block;
            }
            .success-file-meta {
                font-size: 12px;
                color: #64748b;
                display: flex;
                gap: 8px;
                margin-top: 2px;
            }
            .success-file-status {
                color: #22c55e;
                font-weight: 500;
            }
            .success-modal-btn {
                width: 100%;
                padding: 14px;
                border-radius: 40px;
                background: linear-gradient(135deg, #0366d6 0%, #22c55e 100%);
                color: white;
                font-size: 15px;
                font-weight: 600;
                border: none;
                cursor: pointer;
                transition: all 0.2s;
                box-shadow: 0 4px 15px rgba(34, 197, 94, 0.3);
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
            }
            .success-modal-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(34, 197, 94, 0.45);
            }

            .send-progress-card {
                background: linear-gradient(135deg, #182030 0%, #0e1320 100%);
                border: 1px solid rgba(3, 102, 214, 0.3);
                border-radius: 18px;
                padding: 16px 20px;
                margin-top: 16px;
                display: none;
            }
            .send-progress-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 8px;
                font-size: 13px;
            }
            .send-progress-name {
                font-weight: 600;
                color: #f1f5f9;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                max-width: 70%;
            }
            .send-progress-percent {
                font-weight: 700;
                color: #38bdf8;
            }
            .send-progress-bar {
                background: rgba(10, 14, 26, 0.8);
                border-radius: 10px;
                height: 8px;
                overflow: hidden;
                margin-bottom: 8px;
            }
            .send-progress-fill {
                height: 100%;
                background: linear-gradient(90deg, #0366d6, #38bdf8, #22c55e);
                border-radius: 10px;
                transition: width 0.2s ease;
                width: 0%;
            }
            .send-progress-meta {
                font-size: 12px;
                color: #8b92a8;
                text-align: right;
            }

            /* RESPONSIVE */
            @media (max-width: 600px) {
                body { padding: 12px; }
                .header { padding: 16px 20px; flex-direction: column; align-items: stretch; }
                .logo-area h1 { font-size: 1.5em; }
                .header-actions { justify-content: space-between; }
                .drop-zone { padding: 30px 20px; }
                .drop-zone-icon { font-size: 48px; }
                .drop-zone-title { font-size: 18px; }
                .qr-code-container img { width: 150px; height: 150px; }
                .btn { padding: 12px 20px; font-size: 14px; }
                .session-info { flex-direction: column; align-items: stretch; text-align: center; }
                .qr-section { padding: 20px; }
                .actions .btn { flex: 1; justify-content: center; min-width: 120px; }
            }

            @media (max-width: 400px) {
                .drop-zone { padding: 24px 16px; }
                .drop-zone-icon { font-size: 40px; }
                .qr-code-container img { width: 120px; height: 120px; }
                .file-preview-item { padding: 8px 10px; }
                .file-preview-item .icon { font-size: 22px; width: 32px; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <!-- HEADER -->
            <div class="header">
                <div class="logo-area">
                    <img src="/static/pydrop1.png" alt="PyDrop" class="app-logo-img">
                    <h1><span>Py</span><span>Drop</span></h1>
                    <span class="status-badge waiting" id="statusBadge"><img src="/static/icons/upload.svg" class="svg-icon" style="width:14px;height:14px;vertical-align:-2px;margin-right:4px;" alt=""> Envoyer</span>
                </div>
                <div class="header-actions">
                    <a href="/" class="btn-back">← Explorer</a>
                </div>
            </div>

            <!-- DROP ZONE -->
            <div class="drop-zone" id="dropZone">
                <span class="drop-zone-icon"><img src="/static/icons/upload.svg" class="svg-icon" style="width:52px;height:52px;" alt=""></span>
                <div class="drop-zone-title">Glissez-déposez vos fichiers</div>
                <div class="drop-zone-sub">ou cliquez pour sélectionner</div>
                <div class="drop-zone-hint">
                    <span><img src="/static/icons/folder.svg" class="svg-icon" style="width:14px;height:14px;vertical-align:-2px;margin-right:4px;" alt=""> Tous types de fichiers</span>
                    <span><img src="/static/icons/package.svg" class="svg-icon" style="width:14px;height:14px;vertical-align:-2px;margin-right:4px;" alt=""> Jusqu'à 2 Go</span>
                </div>
                <input type="file" id="fileInput" multiple>
            </div>

            <!-- FILE PREVIEW -->
            <div id="filePreviewWrapper" class="file-preview-wrapper hidden">
                <div class="file-preview-header">
                    <span class="count"><strong id="fileCount">0</strong> fichier(s) sélectionné(s)</span>
                    <button class="btn-small btn-danger" onclick="clearFiles()"><img src="/static/icons/trash-2.svg" class="svg-icon" style="width:14px;height:14px;vertical-align:-2px;margin-right:4px;" alt=""> Tout effacer</button>
                </div>
                <div class="file-preview" id="filePreview"></div>

                <!-- PROGRESSION D'ENVOI EN TEMPS RÉEL -->
                <div id="sendProgressCard" class="send-progress-card">
                    <div class="send-progress-header">
                        <span class="send-progress-name" id="sendProgressName">Envoi des fichiers...</span>
                        <span class="send-progress-percent" id="sendProgressPercent">0%</span>
                    </div>
                    <div class="send-progress-bar">
                        <div class="send-progress-fill" id="sendProgressFill"></div>
                    </div>
                    <div class="send-progress-meta" id="sendProgressMeta">0 B / 0 B</div>
                </div>

                <div class="actions" style="margin-top: 16px;">
                    <button class="btn btn-primary" id="sendBtn" onclick="sendFiles()">
                        <img src="/static/icons/upload.svg" class="svg-icon" style="width:18px;height:18px;vertical-align:-3px;margin-right:6px;" alt=""> Envoyer vers le téléphone
                    </button>
                </div>
            </div>

            <!-- MODALE DE SUCCÈS AVEC ANIMATION CHECKMARK -->
            <div id="sendSuccessModal" class="success-modal-overlay">
                <div class="success-modal-card">
                    <button class="success-modal-close-btn" onclick="closeSendSuccessModal()" title="Fermer"><img src="/static/icons/x.svg" class="svg-icon" style="width:16px;height:16px;" alt=""></button>
                    
                    <div class="success-icon-wrap">
                        <div class="success-icon-glow"></div>
                        <svg class="success-checkmark-svg" viewBox="0 0 52 52">
                            <circle class="success-checkmark-circle" cx="26" cy="26" r="23"/>
                            <path class="success-checkmark-check" d="M14.1 27.2l7.1 7.2 16.7-16.8"/>
                        </svg>
                    </div>
                    
                    <h3 class="success-modal-title" id="sendSuccessModalTitle">Transfert prêt !</h3>
                    <p class="success-modal-message" id="sendSuccessModalMsg">Fichier téléversé avec succès</p>
                    
                    <div class="success-file-card">
                        <div class="success-file-icon" id="sendSuccessModalFileIcon"><img src="/static/icons/file.svg" class="svg-icon" style="width:24px;height:24px;" alt=""></div>
                        <div class="success-file-info">
                            <span class="success-file-name" id="sendSuccessModalFileName">-</span>
                            <div class="success-file-meta">
                                <span id="sendSuccessModalFileSize">-</span>
                                <span>•</span>
                                <span class="success-file-status">Téléversé avec succès</span>
                            </div>
                        </div>
                    </div>
                    
                    <button class="success-modal-btn" onclick="closeSendSuccessModal()">
                        <span>Continuer</span>
                        <span>✓</span>
                    </button>
                </div>
            </div>

            <!-- SESSION INFO -->
            <div id="sessionContainer" class="hidden">
                <div class="session-info">
                    <div>
                        <div class="label"><img src="/static/icons/hash.svg" class="svg-icon" style="width:12px;height:12px;vertical-align:-1px;margin-right:3px;" alt=""> Session</div>
                        <div class="value" id="sessionIdDisplay">-</div>
                    </div>
                    <div>
                        <div class="label">Statut</div>
                        <div class="status-text" id="sessionStatus">En attente...</div>
                    </div>
                    <button class="copy-btn" onclick="copySessionUrl()"><img src="/static/icons/copy.svg" class="svg-icon" style="width:13px;height:13px;vertical-align:-2px;margin-right:4px;" alt=""> Copier le lien</button>
                </div>
            </div>

            <!-- QR SECTION -->
            <div class="qr-section">
                <h3><img src="/static/icons/smartphone.svg" class="svg-icon" style="width:20px;height:20px;vertical-align:-3px;margin-right:6px;" alt=""> Scannez pour recevoir sur votre téléphone</h3>
                <div class="sub">Ou ouvrez le lien directement sur votre téléphone</div>
                <div class="qr-code-container">
                    <img id="qrCodeImg" src="" alt="QR Code">
                </div>
                <div class="qr-url" id="qrUrlDisplay">Chargement...</div>
                <div class="qr-actions">
                    <button class="btn btn-secondary btn-small" onclick="copyQrUrl()"><img src="/static/icons/copy.svg" class="svg-icon" style="width:13px;height:13px;vertical-align:-2px;margin-right:4px;" alt=""> Copier l'URL</button>
                </div>
            </div>
        </div>

        <!-- NOTIFICATION -->
        <div class="notification" id="notification"></div>

        <script>
            let selectedFiles = [];
            let currentSessionId = null;
            let sessionStatusInterval = null;

            // === DROP ZONE ===
            const dropZone = document.getElementById('dropZone');
            const fileInput = document.getElementById('fileInput');

            dropZone.addEventListener('dragover', (e) => {
                e.preventDefault();
                dropZone.classList.add('drag-over');
            });

            dropZone.addEventListener('dragleave', () => {
                dropZone.classList.remove('drag-over');
            });

            dropZone.addEventListener('drop', (e) => {
                e.preventDefault();
                dropZone.classList.remove('drag-over');
                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    addFiles(files);
                }
            });

            dropZone.addEventListener('click', () => {
                fileInput.click();
            });

            fileInput.addEventListener('change', () => {
                if (fileInput.files.length > 0) {
                    addFiles(fileInput.files);
                    fileInput.value = '';
                }
            });

            // === GESTION DES FICHIERS ===
            function addFiles(files) {
                for (const file of files) {
                    const exists = selectedFiles.some(f => f.name === file.name && f.size === file.size);
                    if (!exists && file.size > 0) {
                        selectedFiles.push({
                            name: file.name,
                            size: file.size,
                            type: file.type,
                            file: file
                        });
                    }
                }
                renderFilePreview();
            }

            function getFileIcon(filename, type = 'item') {
                if (!filename) {
                    const sz = type === 'card' ? '40px' : (type === 'preview' ? '28px' : '22px');
                    return `<img src="/static/icons/file.svg" class="svg-icon" style="width:${sz};height:${sz};" alt="file">`;
                }
                const ext = filename.split('.').pop().toLowerCase();
                const map = {
                    'jpg': 'image', 'jpeg': 'image', 'png': 'image', 'gif': 'image', 'webp': 'image', 'svg': 'image', 'bmp': 'image', 'ico': 'image', 'tiff': 'image', 'psd': 'image', 'ai': 'image',
                    'mp4': 'video', 'mkv': 'video', 'avi': 'video', 'mov': 'video', 'wmv': 'video', 'webm': 'video', 'm4v': 'video', 'flv': 'video', '3gp': 'video', 'ts': 'video',
                    'mp3': 'music', 'wav': 'music', 'flac': 'music', 'aac': 'music', 'ogg': 'music', 'm4a': 'music', 'wma': 'music', 'opus': 'music', 'mid': 'music', 'midi': 'music',
                    'pdf': 'file-pdf',
                    'doc': 'file-doc', 'docx': 'file-doc', 'odt': 'file-doc', 'rtf': 'file-doc', 'dot': 'file-doc', 'dotx': 'file-doc',
                    'xls': 'file-spreadsheet', 'xlsx': 'file-spreadsheet', 'csv': 'file-spreadsheet', 'ods': 'file-spreadsheet', 'tsv': 'file-spreadsheet', 'xlsm': 'file-spreadsheet',
                    'ppt': 'file-presentation', 'pptx': 'file-presentation', 'odp': 'file-presentation', 'pps': 'file-presentation', 'ppsx': 'file-presentation',
                    'py': 'file-python', 'pyw': 'file-python', 'ipynb': 'file-python',
                    'php': 'file-php',
                    'cs': 'file-cs',
                    'c': 'file-cpp', 'cpp': 'file-cpp', 'cc': 'file-cpp', 'cxx': 'file-cpp', 'h': 'file-cpp', 'hpp': 'file-cpp',
                    'java': 'file-java', 'class': 'file-java', 'jar': 'file-java',
                    'js': 'file-js', 'mjs': 'file-js', 'cjs': 'file-js', 'jsx': 'file-js',
                    'ts': 'file-ts', 'tsx': 'file-ts',
                    'html': 'file-html', 'htm': 'file-html', 'xhtml': 'file-html', 'vue': 'file-html',
                    'css': 'file-css', 'scss': 'file-css', 'sass': 'file-css', 'less': 'file-css',
                    'json': 'file-json', 'xml': 'file-json', 'yaml': 'file-json', 'yml': 'file-json', 'toml': 'file-json', 'ini': 'file-json', 'env': 'file-json', 'config': 'file-json', 'lock': 'file-json',
                    'sql': 'file-sql',
                    'sh': 'file-sh', 'bash': 'file-sh', 'zsh': 'file-sh', 'bat': 'file-sh', 'ps1': 'file-sh', 'cmd': 'file-sh',
                    'rs': 'file-rs', 'go': 'file-go', 'rb': 'file-rb',
                    'swift': 'file-swift', 'kt': 'file-swift', 'kts': 'file-swift',
                    'zip': 'file-archive', 'rar': 'file-archive', '7z': 'file-archive', 'tar': 'file-archive', 'gz': 'file-archive', 'xz': 'file-archive', 'bz2': 'file-archive', 'tgz': 'file-archive',
                    'txt': 'file-text', 'md': 'file-text', 'log': 'file-text',
                    'iso': 'disc', 'dmg': 'disc', 'img': 'disc', 'vhd': 'disc',
                    'exe': 'settings', 'msi': 'settings', 'deb': 'settings', 'rpm': 'settings',
                    'apk': 'smartphone', 'aab': 'smartphone', 'ipa': 'smartphone'
                };
                const icon = map[ext] || 'file';
                const sz = type === 'card' ? '40px' : (type === 'preview' ? '28px' : '22px');
                return `<img src="/static/icons/${icon}.svg" class="svg-icon" style="width:${sz};height:${sz};" alt="${ext}">`;
            }

            function formatSize(bytes) {
                if (bytes < 1024) return bytes + ' B';
                if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
                if (bytes < 1024 * 1024 * 1024) return (bytes / 1024 / 1024).toFixed(1) + ' MB';
                return (bytes / 1024 / 1024 / 1024).toFixed(2) + ' GB';
            }

            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }

            function renderFilePreview() {
                const wrapper = document.getElementById('filePreviewWrapper');
                const container = document.getElementById('filePreview');
                const count = document.getElementById('fileCount');

                if (selectedFiles.length === 0) {
                    wrapper.classList.add('hidden');
                    return;
                }

                wrapper.classList.remove('hidden');
                count.textContent = selectedFiles.length;

                container.innerHTML = selectedFiles.map((f, i) => `
                    <div class="file-preview-item">
                        <span class="icon">${getFileIcon(f.name)}</span>
                        <div class="info">
                            <div class="name">${escapeHtml(f.name)}</div>
                            <div class="size">${formatSize(f.size)}</div>
                        </div>
                        <button class="remove" onclick="removeFile(${i})" title="Supprimer"><img src="/static/icons/x.svg" class="svg-icon" style="width:14px;height:14px;" alt=""></button>
                    </div>
                `).join('');
            }

            function removeFile(index) {
                selectedFiles.splice(index, 1);
                renderFilePreview();
                if (selectedFiles.length === 0) {
                    hideSession();
                }
            }

            function clearFiles() {
                selectedFiles = [];
                renderFilePreview();
                hideSession();
            }

            function hideSession() {
                document.getElementById('sessionContainer').classList.add('hidden');
                if (sessionStatusInterval) {
                    clearInterval(sessionStatusInterval);
                    sessionStatusInterval = null;
                }
                updateStatusBadge('waiting', '<img src="/static/icons/upload.svg" class="svg-icon" style="width:14px;height:14px;vertical-align:-2px;margin-right:4px;"> Envoyer');
            }

            // === NOTIFICATIONS ===
            function showNotification(message, type = 'info') {
                const notif = document.getElementById('notification');
                notif.textContent = message;
                notif.className = 'notification ' + type;
                notif.style.display = 'block';
                clearTimeout(notif._timeout);
                notif._timeout = setTimeout(() => {
                    notif.style.display = 'none';
                }, 4000);
            }

            // === MODALE DE SUCCÈS ===
            function showSendSuccessModal(fileName, fileSize, isMultiple) {
                const modal = document.getElementById('sendSuccessModal');
                const titleEl = document.getElementById('sendSuccessModalTitle');
                const msgEl = document.getElementById('sendSuccessModalMsg');
                const fileIconEl = document.getElementById('sendSuccessModalFileIcon');
                const fileNameEl = document.getElementById('sendSuccessModalFileName');
                const fileSizeEl = document.getElementById('sendSuccessModalFileSize');
                
                titleEl.textContent = 'Téléversement réussi !';
                if (isMultiple) {
                    msgEl.innerHTML = `<strong>${escapeHtml(fileName)}</strong> et autres fichiers téléversés avec succès`;
                } else {
                    msgEl.innerHTML = `Fichier <strong>${escapeHtml(fileName)}</strong> téléversé avec succès`;
                }
                
                fileIconEl.innerHTML = getFileIcon(fileName, 'preview');
                fileNameEl.textContent = fileName;
                fileSizeEl.textContent = fileSize;
                
                modal.classList.add('active');
            }

            function closeSendSuccessModal() {
                const modal = document.getElementById('sendSuccessModal');
                modal.classList.remove('active');
            }

            // === STATUS BADGE ===
            function updateStatusBadge(type, text) {
                const badge = document.getElementById('statusBadge');
                badge.className = 'status-badge ' + type;
                badge.textContent = text;
            }

            // === ENVOI DES FICHIERS AVEC PROGRESSION XHR ===
            function sendFiles() {
                if (selectedFiles.length === 0) {
                    showNotification('Veuillez sélectionner des fichiers', 'warning');
                    return;
                }

                const sendBtn = document.getElementById('sendBtn');
                const progressCard = document.getElementById('sendProgressCard');
                const progressFill = document.getElementById('sendProgressFill');
                const progressPercent = document.getElementById('sendProgressPercent');
                const progressMeta = document.getElementById('sendProgressMeta');
                const progressName = document.getElementById('sendProgressName');

                sendBtn.disabled = true;
                sendBtn.innerHTML = '⏳ Envoi en cours...';
                updateStatusBadge('sending', '⏳ Envoi en cours...');

                progressCard.style.display = 'block';
                progressFill.style.width = '0%';
                progressPercent.textContent = '0%';

                const totalBytes = selectedFiles.reduce((acc, f) => acc + f.size, 0);
                const firstFileName = selectedFiles[0].name;
                const isMulti = selectedFiles.length > 1;
                progressName.textContent = isMulti ? `${firstFileName} (+${selectedFiles.length - 1} autre(s))` : firstFileName;
                progressMeta.textContent = `0 B / ${formatSize(totalBytes)}`;

                const formData = new FormData();
                for (const f of selectedFiles) {
                    formData.append('file', f.file);
                }

                const xhr = new XMLHttpRequest();
                xhr.open('POST', '/api/upload_to_phone', true);

                xhr.upload.onprogress = function(e) {
                    if (e.lengthComputable) {
                        const percent = Math.round((e.loaded / e.total) * 100);
                        progressFill.style.width = percent + '%';
                        progressPercent.textContent = percent + '%';
                        progressMeta.textContent = `${formatSize(e.loaded)} / ${formatSize(e.total)}`;
                    }
                };

                xhr.onload = function() {
                    sendBtn.disabled = false;
                    sendBtn.innerHTML = '<img src="/static/icons/upload.svg" class="svg-icon" style="width:18px;height:18px;vertical-align:-3px;margin-right:6px;" alt=""> Envoyer vers le téléphone';

                    if (xhr.status >= 200 && xhr.status < 300) {
                        try {
                            const data = JSON.parse(xhr.responseText);
                            currentSessionId = data.session_id;
                            document.getElementById('sessionIdDisplay').textContent = currentSessionId;
                            document.getElementById('sessionContainer').classList.remove('hidden');
                            updateSessionStatus('En attente de confirmation...', 'waiting');

                            const url = window.location.origin + '/phone?session=' + currentSessionId;
                            document.getElementById('qrUrlDisplay').textContent = url;
                            generateQRCode(url);

                            progressFill.style.width = '100%';
                            progressPercent.textContent = '100%';
                            setTimeout(() => {
                                progressCard.style.display = 'none';
                            }, 1000);

                            // Affichage de la modale de succès animée
                            showSendSuccessModal(firstFileName, formatSize(totalBytes), isMulti);
                            updateStatusBadge('waiting', '⏳ En attente...');

                            startSessionMonitoring();
                        } catch (e) {
                            showNotification('Erreur de traitement du serveur', 'error');
                            updateStatusBadge('rejected', '<img src="/static/icons/x-circle.svg" class="svg-icon" style="width:12px;height:12px;vertical-align:-1px;margin-right:3px;"> Erreur');
                        }
                    } else {
                        let errorMsg = 'Erreur lors du téléversement';
                        try {
                            const errData = JSON.parse(xhr.responseText);
                            if (errData.error) errorMsg = errData.error;
                        } catch(e) {}
                        showNotification(errorMsg, 'error');
                        updateStatusBadge('rejected', '<img src="/static/icons/x-circle.svg" class="svg-icon" style="width:12px;height:12px;vertical-align:-1px;margin-right:3px;"> Erreur');
                        progressCard.style.display = 'none';
                    }
                };

                xhr.onerror = function() {
                    sendBtn.disabled = false;
                    sendBtn.innerHTML = '<img src="/static/icons/upload.svg" class="svg-icon" style="width:18px;height:18px;vertical-align:-3px;margin-right:6px;" alt=""> Envoyer vers le téléphone';
                    showNotification('Erreur de connexion au serveur', 'error');
                    updateStatusBadge('rejected', '<img src="/static/icons/x-circle.svg" class="svg-icon" style="width:12px;height:12px;vertical-align:-1px;margin-right:3px;"> Erreur');
                    progressCard.style.display = 'none';
                };

                xhr.send(formData);
            }

            // === SURVEILLANCE DE SESSION ===
            function startSessionMonitoring() {
                if (sessionStatusInterval) clearInterval(sessionStatusInterval);

                sessionStatusInterval = setInterval(async () => {
                    if (!currentSessionId) return;

                    try {
                        const response = await fetch('/api/session/status/' + currentSessionId);
                        const data = await response.json();

                        if (response.status === 404) {
                            updateSessionStatus('Session expirée', 'rejected');
                            updateStatusBadge('rejected', '<img src="/static/icons/clock.svg" class="svg-icon" style="width:12px;height:12px;vertical-align:-1px;margin-right:3px;"> Expirée');
                            clearInterval(sessionStatusInterval);
                            return;
                        }

                        if (data.status === 'accepted') {
                            updateSessionStatus('Accepté - Téléchargement en cours...', 'accepted');
                            updateStatusBadge('accepted', '<img src="/static/icons/check-circle.svg" class="svg-icon" style="width:12px;height:12px;vertical-align:-1px;margin-right:3px;"> Accepté');
                            showNotification('Le téléphone a accepté les fichiers !', 'success');
                            setTimeout(() => checkCompletion(), 2000);
                            
                        } else if (data.status === 'completed') {
                            updateSessionStatus('Transfert terminé !', 'completed');
                            updateStatusBadge('completed', '<img src="/static/icons/check-circle.svg" class="svg-icon" style="width:12px;height:12px;vertical-align:-1px;margin-right:3px;"> Terminé');
                            showNotification('Transfert terminé avec succès !', 'success');
                            clearInterval(sessionStatusInterval);
                            document.getElementById('sendBtn').innerHTML = '<img src="/static/icons/check-circle.svg" class="svg-icon" style="width:18px;height:18px;vertical-align:-3px;margin-right:6px;"> Transfert terminé';
                            document.getElementById('sendBtn').disabled = true;
                            
                        } else if (data.status === 'pending') {
                            updateSessionStatus('En attente de confirmation...', 'waiting');
                            updateStatusBadge('waiting', '⏳ En attente...');
                        }
                    } catch (error) {
                        console.error('Error checking session status:', error);
                    }
                }, 3000);
            }

            async function checkCompletion() {
                if (!currentSessionId) return;

                try {
                    const response = await fetch('/api/session/status/' + currentSessionId);
                    const data = await response.json();

                    if (data.status === 'completed') {
                        updateSessionStatus('Transfert terminé !', 'completed');
                        updateStatusBadge('completed', '<img src="/static/icons/check-circle.svg" class="svg-icon" style="width:12px;height:12px;vertical-align:-1px;margin-right:3px;"> Terminé');
                        showNotification('Transfert terminé avec succès !', 'success');
                        clearInterval(sessionStatusInterval);
                        document.getElementById('sendBtn').innerHTML = '<img src="/static/icons/check-circle.svg" class="svg-icon" style="width:18px;height:18px;vertical-align:-3px;margin-right:6px;"> Transfert terminé';
                        document.getElementById('sendBtn').disabled = true;
                    } else if (data.status === 'accepted') {
                        setTimeout(() => checkCompletion(), 2000);
                    }
                } catch (error) {
                    console.error('Error checking completion:', error);
                }
            }

            function updateSessionStatus(text, type) {
                const el = document.getElementById('sessionStatus');
                el.textContent = text;
                el.className = 'status-text';
                if (type === 'accepted') el.style.color = '#4caf50';
                else if (type === 'completed') el.style.color = '#0366d6';
                else if (type === 'rejected') el.style.color = '#f44336';
                else el.style.color = '#8b92a8';
            }

            // === QR CODE ===
            function generateQRCode(url) {
                const img = document.getElementById('qrCodeImg');
                img.src = 'https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=' + encodeURIComponent(url) + '&bgcolor=ffffff&color=0366d6';
            }

            // === COPY ===
            function copySessionUrl() {
                const url = window.location.origin + '/phone?session=' + currentSessionId;
                navigator.clipboard.writeText(url).then(() => {
                    showNotification('Lien copié !', 'success');
                }).catch(() => {
                    const input = document.createElement('input');
                    input.value = url;
                    document.body.appendChild(input);
                    input.select();
                    document.execCommand('copy');
                    document.body.removeChild(input);
                    showNotification('Lien copié !', 'success');
                });
            }

            function copyQrUrl() {
                const url = document.getElementById('qrUrlDisplay').textContent;
                navigator.clipboard.writeText(url).then(() => {
                    showNotification('URL copiée !', 'success');
                }).catch(() => {
                    const input = document.createElement('input');
                    input.value = url;
                    document.body.appendChild(input);
                    input.select();
                    document.execCommand('copy');
                    document.body.removeChild(input);
                    showNotification('URL copiée !', 'success');
                });
            }

            // === INIT ===
            document.addEventListener('DOMContentLoaded', () => {
                const baseUrl = window.location.origin + '/phone';
                document.getElementById('qrUrlDisplay').textContent = baseUrl;
                generateQRCode(baseUrl);
            });

            // Prevent default drag on page
            document.addEventListener('dragover', (e) => e.preventDefault());
            document.addEventListener('drop', (e) => e.preventDefault());
        </script>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/')
@app.route('/browse/')
@app.route('/browse/<path:path>')
def file_browser(path=''):
    """Explorateur de fichiers et dossiers"""
    year = datetime.datetime.now().year
    shortcuts = get_system_shortcuts()
    
    if (path == '' or path == '/'):
        is_drive_list = True
        current_path = ''
        files_to_render = []
        if sys.platform == 'win32':
            for letter in string.ascii_uppercase:
                drive = f"{letter}:\\"
                if os.path.exists(drive):
                    stats = get_drive_stats(drive)
                    files_to_render.append({
                        'name': drive,
                        'url_path': letter + ':',
                        'stats': stats,
                        'display_name': f"Lecteur ({letter}:)"
                    })
        else:
            stats = get_drive_stats('/')
            files_to_render.append({
                'name': '/',
                'url_path': 'root',
                'stats': stats,
                'display_name': 'Système de fichiers (/)'
            })
            for mount_parent in ['/mnt', '/media']:
                if os.path.exists(mount_parent) and os.path.isdir(mount_parent):
                    try:
                        for item in os.listdir(mount_parent):
                            mp = os.path.join(mount_parent, item)
                            if os.path.isdir(mp):
                                files_to_render.append({
                                    'name': mp,
                                    'url_path': mp[1:] if mp.startswith('/') else mp,
                                    'stats': get_drive_stats(mp),
                                    'display_name': f"Stockage ({item})"
                                })
                    except:
                        pass
        directories = []
        file_list = []
        display_names = {}
        safe_downloads = {}
    else:
        is_drive_list = False
        if sys.platform == 'win32':
            if len(path) == 2 and path[1] == ':':
                current_path = path + '\\'
            else:
                current_path = os.path.abspath(path)
        else:
            current_path = '/' + path if not path.startswith('/') else path
            if current_path == '':
                current_path = '/'
            current_path = os.path.abspath(current_path)

        if not os.path.exists(current_path):
            return "Chemin introuvable", 404

        directories = []
        file_list = []
        display_names = {}
        safe_downloads = {}

        try:
            entries = os.listdir(current_path)
            for entry in entries:
                full_item_path = os.path.join(current_path, entry)
                clean_name = sanitize_for_template(entry)
                display_names[entry] = clean_name
                
                if os.path.isdir(full_item_path):
                    directories.append(entry)
                else:
                    file_list.append(entry)
                    # Utiliser l'API POST pour le téléchargement avec chemin encodé
                    encoded_path = quote(full_item_path.replace('\\', '/'), safe='')
                    safe_downloads[entry] = f'/download_file?filepath={encoded_path}'
        except PermissionError:
            return "Permission refusée pour ce dossier", 403
        except Exception as e:
            return f"Erreur: {e}", 500

        files_to_render = []

    bs = '\\'
    slash = '/'
    
    html_template = """<!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=yes">
        <link rel="icon" type="image/png" href="{{ url_for('static', filename='pydrop1.png') }}">
        <title>PyDrop</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            .svg-icon {
                display: inline-block;
                vertical-align: middle;
                filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));
                transition: transform 0.2s ease, filter 0.2s ease;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                background: #0a0e1a;
                min-height: 100vh;
                padding: 20px;
                padding-bottom: 80px;
                color: #e2e8f0;
            }
            .container { max-width: 1200px; margin: 0 auto; margin-bottom: 60px; }
            .header {
                background: linear-gradient(135deg, #1a1f2e 0%, #0f131f 100%);
                border-radius: 24px;
                padding: 20px 30px;
                margin-bottom: 25px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.3);
                display: flex;
                align-items: center;
                gap: 15px;
                flex-wrap: wrap;
                border: 1px solid rgba(3, 102, 214, 0.2);
            }
            .logo-area {
                display: flex;
                align-items: center;
                gap: 12px;
            }
            .app-logo-img {
                width: 38px;
                height: 38px;
                object-fit: contain;
                border-radius: 10px;
                filter: drop-shadow(0 2px 8px rgba(3, 102, 214, 0.4));
                transition: transform 0.3s ease;
            }
            .logo-area:hover .app-logo-img {
                transform: scale(1.08) rotate(3deg);
            }
            .logo-area h1 { font-size: 2em; margin: 0; }
            .logo-area h1 span:first-child { color: #0366d6; }
            .logo-area h1 span:last-child { color: #f68b1e; }
            .search-container { flex: 1; max-width: 400px; margin-left: auto; margin-right: 15px; }
            .search-box {
                display: flex;
                align-items: center;
                background: rgba(10, 14, 26, 0.8);
                border-radius: 40px;
                padding: 8px 16px;
                border: 1px solid rgba(3, 102, 214, 0.3);
                transition: all 0.3s ease;
            }
            .search-box:focus-within {
                border-color: #0366d6;
                box-shadow: 0 0 0 2px rgba(3, 102, 214, 0.2);
                background: #0a0e1a;
            }
            .search-icon { color: #5a6278; font-size: 18px; margin-right: 10px; }
            .search-input {
                background: transparent;
                border: none;
                color: #e2e8f0;
                font-size: 14px;
                width: 100%;
                outline: none;
            }
            .search-input::placeholder { color: #5a6278; }
            .search-clear {
                background: none;
                border: none;
                color: #5a6278;
                cursor: pointer;
                font-size: 18px;
                padding: 0 5px;
                display: none;
            }
            .search-clear:hover { color: #f68b1e; }
            .search-info { font-size: 12px; color: #5a6278; margin-top: 5px; padding-left: 16px; }
            
            .header-btn {
                background: linear-gradient(135deg, #0366d6, #f68b1e);
                color: white;
                padding: 8px 18px;
                border-radius: 40px;
                text-decoration: none;
                font-size: 13px;
                font-weight: 500;
                display: inline-flex;
                align-items: center;
                gap: 6px;
                transition: all 0.3s ease;
                border: none;
                cursor: pointer;
            }
            .header-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 8px 20px rgba(3, 102, 214, 0.3);
            }
            
            .clear-history-btn {
                background: rgba(244, 67, 54, 0.2);
                border: 1px solid rgba(244, 67, 54, 0.3);
                color: #f44336;
                padding: 8px 16px;
                border-radius: 40px;
                font-size: 13px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.2s ease;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            .clear-history-btn:hover {
                background: #f44336;
                color: white;
                transform: scale(1.02);
            }
            
            .connection-status {
                display: flex;
                align-items: center;
                gap: 10px;
                padding: 8px 16px;
                border-radius: 40px;
                font-size: 13px;
                font-weight: 600;
                transition: all 0.3s ease;
                background: rgba(0,0,0,0.3);
                backdrop-filter: blur(10px);
            }
            .connection-status .status-dot {
                width: 10px;
                height: 10px;
                border-radius: 50%;
                animation: pulse 1.5s ease-in-out infinite;
            }
            @keyframes pulse {
                0%, 100% { opacity: 1; transform: scale(1); }
                50% { opacity: 0.5; transform: scale(1.2); }
            }
            .connection-status.online {
                background: rgba(76, 175, 80, 0.2);
                color: #4caf50;
                border: 1px solid rgba(76, 175, 80, 0.3);
            }
            .connection-status.online .status-dot { background: #4caf50; box-shadow: 0 0 8px rgba(76, 175, 80, 0.5); }
            .connection-status.offline {
                background: rgba(244, 67, 54, 0.2);
                color: #f44336;
                border: 1px solid rgba(244, 67, 54, 0.3);
            }
            .connection-status.offline .status-dot { background: #f44336; box-shadow: 0 0 8px rgba(244, 67, 54, 0.5); }
            .connection-status.checking {
                background: rgba(255, 152, 0, 0.2);
                color: #ff9800;
                border: 1px solid rgba(255, 152, 0, 0.3);
            }
            .connection-status.checking .status-dot { background: #ff9800; animation: none; }
            
            .path {
                background: rgba(26, 31, 46, 0.95);
                backdrop-filter: blur(10px);
                padding: 15px 20px;
                border-radius: 16px;
                margin-bottom: 25px;
                font-family: 'Courier New', monospace;
                font-size: 14px;
                word-break: break-all;
                border: 1px solid rgba(3, 102, 214, 0.2);
                box-shadow: 0 4px 16px rgba(0,0,0,0.2);
                display: flex;
                justify-content: space-between;
                align-items: center;
                flex-wrap: wrap;
                gap: 10px;
            }
            .path-code { flex: 1; overflow-x: auto; }
            
            .section-title {
                font-size: 13px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.8px;
                color: #94a3b8;
                margin: 20px 0 12px 2px;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            .section-title .svg-icon {
                opacity: 0.9;
            }
            .shortcuts-grid {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 12px;
                margin-bottom: 24px;
            }
            @media (min-width: 640px) {
                .shortcuts-grid {
                    grid-template-columns: repeat(3, 1fr);
                    gap: 14px;
                }
            }
            @media (min-width: 1024px) {
                .shortcuts-grid {
                    grid-template-columns: repeat(5, 1fr);
                    gap: 16px;
                }
            }
            .shortcut-card {
                background: linear-gradient(135deg, #182032 0%, #111625 100%);
                border-radius: 16px;
                padding: 14px 12px;
                text-decoration: none;
                color: inherit;
                transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
                border: 1px solid rgba(255, 255, 255, 0.08);
                display: flex;
                flex-direction: column;
                align-items: flex-start;
                gap: 10px;
                position: relative;
                overflow: hidden;
                box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
            }
            .shortcut-card::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 3px;
                background: var(--card-accent, #0366d6);
                opacity: 0.9;
                transition: height 0.2s ease;
            }
            .shortcut-card:hover {
                transform: translateY(-3px);
                border-color: rgba(3, 102, 214, 0.5);
                box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
            }
            .shortcut-card:hover::before {
                height: 4px;
            }
            .shortcut-icon-wrapper {
                width: 38px;
                height: 38px;
                border-radius: 10px;
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                display: flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
                transition: transform 0.2s ease;
            }
            .shortcut-card:hover .shortcut-icon-wrapper {
                transform: scale(1.1);
            }
            .shortcut-details {
                width: 100%;
                min-width: 0;
            }
            .shortcut-title {
                font-size: 14px;
                font-weight: 700;
                color: #f1f5f9;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                margin-bottom: 2px;
            }
            .shortcut-subtitle {
                font-size: 11px;
                color: #8b92a8;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .shortcut-badge {
                font-size: 10px;
                color: #64748b;
                margin-top: 4px;
                background: rgba(255, 255, 255, 0.04);
                display: inline-block;
                padding: 2px 6px;
                border-radius: 6px;
            }
            .quick-nav-bar {
                display: flex;
                align-items: center;
                gap: 8px;
                overflow-x: auto;
                padding: 4px 0 16px 0;
                margin-bottom: 12px;
                scrollbar-width: thin;
            }
            .quick-nav-pill {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                background: rgba(26, 31, 46, 0.85);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 20px;
                padding: 6px 14px;
                font-size: 12px;
                color: #cbd5e1;
                text-decoration: none;
                white-space: nowrap;
                transition: all 0.2s ease;
            }
            .quick-nav-pill:hover {
                background: rgba(3, 102, 214, 0.25);
                border-color: rgba(3, 102, 214, 0.5);
                color: #ffffff;
                transform: translateY(-2px);
            }
            .quick-nav-pill.active {
                background: linear-gradient(135deg, rgba(3, 102, 214, 0.4), rgba(246, 139, 30, 0.4));
                border-color: #0366d6;
                color: #ffffff;
                font-weight: 600;
            }

            /* DRIVE LIST (LIST VIEW FOR DISKS) */
            .drive-list {
                display: flex;
                flex-direction: column;
                gap: 14px;
                margin-bottom: 30px;
            }
            .drive-list-item {
                background: linear-gradient(135deg, #182032 0%, #111625 100%);
                border-radius: 18px;
                padding: 16px 20px;
                text-decoration: none;
                color: inherit;
                transition: all 0.25s ease;
                border: 1px solid rgba(255, 255, 255, 0.08);
                display: flex;
                align-items: center;
                gap: 18px;
                box-shadow: 0 4px 18px rgba(0,0,0,0.25);
            }
            .drive-list-item:hover {
                transform: translateY(-2px);
                border-color: rgba(3, 102, 214, 0.5);
                box-shadow: 0 8px 26px rgba(3, 102, 214, 0.25);
                background: linear-gradient(135deg, #1d263b 0%, #141b2c 100%);
            }
            .drive-list-icon {
                width: 52px;
                height: 52px;
                flex-shrink: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                background: rgba(3, 102, 214, 0.08);
                border-radius: 14px;
                border: 1px solid rgba(3, 102, 214, 0.2);
                padding: 6px;
                transition: transform 0.2s ease;
            }
            .drive-list-item:hover .drive-list-icon {
                transform: scale(1.06);
            }
            .drive-list-icon img {
                width: 100%;
                height: 100%;
                object-fit: contain;
            }
            .drive-list-body {
                flex: 1;
                min-width: 0;
            }
            .drive-list-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 10px;
                margin-bottom: 8px;
            }
            .drive-list-name {
                font-size: 16px;
                font-weight: 700;
                color: #f1f5f9;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .drive-list-percent {
                font-size: 13px;
                font-weight: 700;
                color: #38bdf8;
                background: rgba(56, 189, 248, 0.12);
                padding: 2px 8px;
                border-radius: 8px;
            }
            .drive-list-percent.warning {
                color: #f68b1e;
                background: rgba(246, 139, 30, 0.15);
            }
            .drive-list-percent.danger {
                color: #ef4444;
                background: rgba(239, 68, 68, 0.15);
            }
            .drive-list-stats {
                display: flex;
                flex-wrap: wrap;
                gap: 12px;
                font-size: 12px;
                color: #8b92a8;
                margin-top: 8px;
            }
            .drive-list-stats span {
                display: inline-flex;
                align-items: center;
            }
            .drive-list-action {
                color: #64748b;
                display: flex;
                align-items: center;
                padding-left: 8px;
            }
            .drive-list-item:hover .drive-list-action {
                color: #38bdf8;
            }
            .progress-bar-container {
                background: #0a0e1a;
                border-radius: 10px;
                height: 8px;
                overflow: hidden;
            }
            .progress-bar-fill {
                height: 100%;
                background: linear-gradient(90deg, #0366d6, #f68b1e);
                transition: width 0.3s ease;
                border-radius: 10px;
            }
            .progress-bar-fill.warning { background: linear-gradient(90deg, #ff9800, #ffc107); }
            .progress-bar-fill.danger { background: linear-gradient(90deg, #f44336, #e91e63); }

            .file-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
                gap: 16px;
                margin-bottom: 30px;
            }
            .file-card {
                background: linear-gradient(135deg, #1a1f2e 0%, #131725 100%);
                border-radius: 16px;
                padding: 20px 12px;
                text-align: center;
                transition: all 0.3s ease;
                border: 1px solid rgba(3, 102, 214, 0.15);
                position: relative;
            }
            .file-card:hover {
                transform: translateY(-5px);
                border-color: rgba(3, 102, 214, 0.4);
                box-shadow: 0 8px 20px rgba(3, 102, 214, 0.2);
                background: linear-gradient(135deg, #1e2538 0%, #161c2e 100%);
            }
            .file-card.folder:hover { border-color: #0366d6; }
            .file-card.file:hover { border-color: #f68b1e; }
            .file-card-icon {
                width: 54px;
                height: 54px;
                margin: 0 auto 12px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: 14px;
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
            }
            .file-card:hover .file-card-icon { transform: scale(1.08); }
            .file-card.folder .file-card-icon {
                background: rgba(246, 139, 30, 0.1);
                border-color: rgba(246, 139, 30, 0.25);
                box-shadow: 0 4px 12px rgba(246, 139, 30, 0.1);
            }
            .file-card.file .file-card-icon {
                background: rgba(3, 102, 214, 0.08);
                border-color: rgba(3, 102, 214, 0.2);
                box-shadow: 0 4px 12px rgba(3, 102, 214, 0.1);
            }
            .up-card .file-card-icon {
                background: rgba(246, 139, 30, 0.1);
                border-color: rgba(246, 139, 30, 0.25);
            }
            .file-card-icon .svg-icon {
                width: 28px !important;
                height: 28px !important;
                display: block;
            }
            .arrow-up { font-size: 24px; font-weight: bold; }
            .file-card-name {
                font-size: 13px;
                font-weight: 500;
                color: #e2e8f0;
                word-break: break-word;
                overflow: hidden;
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
                margin-bottom: 12px;
                min-height: 36px;
            }
            .file-card-name.folder { color: #0366d6; }
            .file-card-name.file { color: #f68b1e; }
            .file-card-action {
                display: inline-block;
                background: rgba(3, 102, 214, 0.2);
                padding: 6px 14px;
                border-radius: 20px;
                text-decoration: none;
                color: #0366d6;
                font-size: 12px;
                font-weight: 500;
                transition: all 0.2s;
                border: 1px solid rgba(3, 102, 214, 0.3);
                margin-top: 8px;
            }
            .file-card-action:hover {
                background: #0366d6;
                color: white;
                transform: scale(1.05);
            }
            .file-card.file .file-card-action {
                background: rgba(246, 139, 30, 0.2);
                color: #f68b1e;
                border-color: rgba(246, 139, 30, 0.3);
            }
            .file-card.file .file-card-action:hover {
                background: #f68b1e;
                color: white;
            }
            .up-card {
                background: linear-gradient(135deg, rgba(246, 139, 30, 0.15), rgba(246, 139, 30, 0.05));
                border-color: rgba(246, 139, 30, 0.3);
            }
            .up-card:hover {
                border-color: #f68b1e;
                background: linear-gradient(135deg, rgba(246, 139, 30, 0.25), rgba(246, 139, 30, 0.1));
            }
            .up-card .file-card-icon { color: #f68b1e; }
            .up-card .file-card-name { color: #f68b1e; }

            .file-list {
                display: none;
                background: linear-gradient(135deg, #1a1f2e 0%, #131725 100%);
                border-radius: 20px;
                overflow: hidden;
                box-shadow: 0 8px 24px rgba(0,0,0,0.2);
                margin-bottom: 30px;
                border: 1px solid rgba(3, 102, 214, 0.15);
            }
            .file-item {
                padding: 12px 20px;
                border-bottom: 1px solid rgba(255,255,255,0.05);
                display: flex;
                align-items: center;
                gap: 12px;
                transition: background 0.2s;
            }
            .file-item:hover { background: rgba(3, 102, 214, 0.1); }
            .file-item:last-child { border-bottom: none; }
            .file-item .file-icon {
                width: 36px;
                height: 36px;
                border-radius: 10px;
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                display: flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
                transition: transform 0.2s ease;
            }
            .file-item:hover .file-icon { transform: scale(1.08); }
            .file-item .file-icon .svg-icon {
                width: 20px !important;
                height: 20px !important;
            }
            .file-item .arrow-up { font-size: 20px; font-weight: bold; }
            .file-item .file-name { flex-grow: 1; font-size: 14px; color: #e2e8f0; word-break: break-word; }
            .file-item .file-name.folder { font-weight: 600; color: #0366d6; }
            .file-item .file-action {
                background: rgba(3, 102, 214, 0.2);
                padding: 6px 14px;
                border-radius: 10px;
                text-decoration: none;
                color: #0366d6;
                font-size: 13px;
                font-weight: 500;
                transition: all 0.2s;
                border: 1px solid rgba(3, 102, 214, 0.3);
            }
            .file-item .file-action:hover {
                background: #0366d6;
                color: white;
                transform: scale(1.05);
                border-color: #0366d6;
            }
            .up-link { background: rgba(246, 139, 30, 0.1); }
            .up-link .file-name { color: #f68b1e; }

            .view-toggle {
                display: flex;
                justify-content: flex-end;
                margin-bottom: 16px;
                gap: 8px;
            }
            .view-btn {
                background: rgba(10, 14, 26, 0.8);
                border: 1px solid rgba(3, 102, 214, 0.3);
                border-radius: 8px;
                padding: 8px 12px;
                cursor: pointer;
                transition: all 0.2s;
                color: #5a6278;
                font-size: 13px;
            }
            .view-btn.active { background: #0366d6; color: white; border-color: #0366d6; }
            .view-btn:hover { border-color: #0366d6; color: #0366d6; }

            .upload-section {
                background: linear-gradient(135deg, #1a1f2e 0%, #131725 100%);
                border-radius: 24px;
                padding: 28px;
                margin-bottom: 30px;
                border: 1px solid rgba(3, 102, 214, 0.2);
            }
            .upload-header {
                display: flex;
                align-items: center;
                gap: 16px;
                margin-bottom: 24px;
            }
            .upload-header-icon {
                width: 52px;
                height: 52px;
                background: linear-gradient(135deg, rgba(3, 102, 214, 0.15), rgba(246, 139, 30, 0.15));
                border-radius: 18px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: #0366d6;
                font-size: 24px;
            }
            .upload-header h2 { font-size: 20px; font-weight: 600; color: #e2e8f0; margin-bottom: 6px; }
            .upload-subtitle { font-size: 13px; color: #8b92a8; }
            .upload-info {
                background: rgba(0, 0, 0, 0.25);
                border-radius: 16px;
                padding: 14px 18px;
                margin-bottom: 24px;
                border: 1px solid rgba(3, 102, 214, 0.15);
            }
            .upload-info-item {
                display: flex;
                align-items: center;
                gap: 12px;
                flex-wrap: wrap;
            }
            .upload-info-label {
                font-size: 12px;
                font-weight: 500;
                color: #8b92a8;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            .upload-info-value {
                background: rgba(0, 0, 0, 0.4);
                padding: 6px 12px;
                border-radius: 10px;
                font-family: monospace;
                font-size: 12px;
                color: #f68b1e;
                word-break: break-all;
            }

            .upload-area {
                background: rgba(10, 14, 26, 0.6);
                border: 2px dashed rgba(3, 102, 214, 0.3);
                border-radius: 20px;
                transition: all 0.3s ease;
                cursor: pointer;
                position: relative;
            }
            .upload-area:hover {
                border-color: #0366d6;
                background: rgba(3, 102, 214, 0.05);
                transform: translateY(-2px);
            }
            .upload-area.drag-over {
                border-color: #f68b1e;
                background: rgba(246, 139, 30, 0.05);
                transform: scale(1.01);
            }
            .upload-area-content { padding: 40px 24px; text-align: center; }
            .upload-area-icon {
                margin-bottom: 16px;
                color: #5a6278;
                transition: all 0.3s ease;
                font-size: 48px;
            }
            .upload-area:hover .upload-area-icon {
                color: #0366d6;
                transform: translateY(-3px);
            }
            .upload-area-text {
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
                flex-wrap: wrap;
                margin-bottom: 12px;
            }
            .upload-area-title { font-size: 15px; color: #a0a8c0; }
            .upload-area-button {
                background: linear-gradient(135deg, #0366d6, #0260c4);
                color: white;
                padding: 8px 20px;
                border-radius: 30px;
                font-size: 14px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.3s ease;
                display: inline-block;
            }
            .upload-area-button:hover {
                transform: scale(1.02);
                box-shadow: 0 4px 12px rgba(3, 102, 214, 0.3);
            }
            .upload-area-hint { font-size: 12px; color: #5a6278; }

            .selected-files {
                margin-top: 20px;
                padding-top: 16px;
                border-top: 1px solid rgba(255, 255, 255, 0.08);
                text-align: left;
                max-height: 150px;
                overflow-y: auto;
            }
            .selected-files .file-item {
                display: flex;
                align-items: center;
                gap: 10px;
                padding: 8px 12px;
                background: rgba(0, 0, 0, 0.3);
                border-radius: 10px;
                margin-bottom: 8px;
                font-size: 13px;
                transition: all 0.2s;
            }
            .selected-files .file-item:hover { background: rgba(3, 102, 214, 0.15); }
            .selected-files .file-item .file-name {
                flex: 1;
                color: #e2e8f0;
                font-family: monospace;
                font-size: 12px;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .selected-files .file-item .file-size { color: #8b92a8; font-size: 11px; }
            .selected-files .file-item .remove-file {
                background: rgba(244, 67, 54, 0.2);
                border: none;
                color: #f44336;
                width: 24px;
                height: 24px;
                border-radius: 50%;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.2s;
            }
            .selected-files .file-item .remove-file:hover {
                background: #f44336;
                color: white;
            }

            .upload-action { margin-top: 24px; text-align: center; }
            #uploadBtn {
                background: linear-gradient(135deg, #0366d6, #f68b1e);
                color: white;
                border: none;
                padding: 14px 32px;
                border-radius: 50px;
                font-size: 15px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.3s ease;
                display: inline-flex;
                align-items: center;
                gap: 10px;
                box-shadow: 0 4px 15px rgba(3, 102, 214, 0.3);
            }
            #uploadBtn:hover {
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(3, 102, 214, 0.4);
            }

            .upload-progress {
                margin-top: 24px;
                display: none;
            }
            .upload-progress-card {
                background: rgba(0, 0, 0, 0.3);
                border-radius: 16px;
                padding: 18px;
                border: 1px solid rgba(3, 102, 214, 0.2);
                animation: fadeInUp 0.3s ease;
            }
            @keyframes fadeInUp {
                from { opacity: 0; transform: translateY(10px); }
                to { opacity: 1; transform: translateY(0); }
            }
            .upload-progress-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 12px;
            }
            .upload-progress-title {
                display: flex;
                align-items: center;
                gap: 8px;
                font-size: 13px;
                font-weight: 500;
                color: #a0a8c0;
            }
            .upload-progress-percent { font-size: 14px; font-weight: 700; color: #f68b1e; }
            .upload-progress-bar {
                background: #0a0e1a;
                border-radius: 10px;
                height: 6px;
                overflow: hidden;
                margin-bottom: 12px;
            }
            .upload-progress-fill {
                height: 100%;
                background: linear-gradient(90deg, #0366d6, #f68b1e);
                transition: width 0.3s ease;
                border-radius: 10px;
            }
            .upload-progress-info {
                display: flex;
                justify-content: space-between;
                align-items: center;
                font-size: 12px;
            }
            .upload-progress-filename { color: #8b92a8; font-family: monospace; }
            .upload-progress-meta { color: #0366d6; font-weight: 500; }

            #uploadFileInput { display: none; }

            /* MODALE DE SUCCÈS & ANIMATION CHECKMARK */
            .success-modal-overlay {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(4, 7, 16, 0.85);
                backdrop-filter: blur(12px);
                -webkit-backdrop-filter: blur(12px);
                align-items: center;
                justify-content: center;
                z-index: 2500;
                opacity: 0;
                transition: opacity 0.3s ease;
            }
            .success-modal-overlay.active {
                display: flex;
                opacity: 1;
            }
            .success-modal-card {
                background: linear-gradient(145deg, #192032 0%, #101524 100%);
                border-radius: 28px;
                max-width: 440px;
                width: 92%;
                padding: 32px 28px;
                text-align: center;
                position: relative;
                box-shadow: 0 20px 60px rgba(0, 0, 0, 0.6), 0 0 0 1px rgba(34, 197, 94, 0.3);
                transform: scale(0.85) translateY(20px);
                transition: transform 0.35s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            }
            .success-modal-overlay.active .success-modal-card {
                transform: scale(1) translateY(0);
            }
            .success-modal-close-btn {
                position: absolute;
                top: 16px;
                right: 16px;
                width: 32px;
                height: 32px;
                border-radius: 50%;
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.1);
                color: #8b92a8;
                font-size: 14px;
                display: flex;
                align-items: center;
                justify-content: center;
                cursor: pointer;
                transition: all 0.2s;
            }
            .success-modal-close-btn:hover {
                background: rgba(255, 255, 255, 0.18);
                color: white;
                transform: scale(1.08);
            }
            .success-icon-wrap {
                width: 80px;
                height: 80px;
                margin: 0 auto 20px;
                position: relative;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            .success-icon-glow {
                position: absolute;
                width: 80px;
                height: 80px;
                border-radius: 50%;
                background: radial-gradient(circle, rgba(34, 197, 94, 0.4) 0%, rgba(34, 197, 94, 0) 70%);
                animation: successPulse 2s infinite ease-in-out;
            }
            @keyframes successPulse {
                0%, 100% { transform: scale(0.9); opacity: 0.6; }
                50% { transform: scale(1.3); opacity: 0.2; }
            }
            .success-checkmark-svg {
                width: 72px;
                height: 72px;
                border-radius: 50%;
                display: block;
                stroke-width: 3.5;
                stroke: #22c55e;
                stroke-miterlimit: 10;
                box-shadow: inset 0px 0px 0px #22c55e;
            }
            .success-checkmark-circle {
                stroke-dasharray: 166;
                stroke-dashoffset: 166;
                stroke-width: 3.5;
                stroke-miterlimit: 10;
                stroke: #22c55e;
                fill: none;
                animation: strokeCircle 0.6s cubic-bezier(0.65, 0, 0.45, 1) forwards;
            }
            .success-checkmark-check {
                transform-origin: 50% 50%;
                stroke-dasharray: 48;
                stroke-dashoffset: 48;
                stroke-width: 3.5;
                stroke: #22c55e;
                fill: none;
                stroke-linecap: round;
                stroke-linejoin: round;
                animation: strokeCheck 0.4s cubic-bezier(0.65, 0, 0.45, 1) 0.5s forwards;
            }
            @keyframes strokeCircle {
                100% { stroke-dashoffset: 0; }
            }
            @keyframes strokeCheck {
                100% { stroke-dashoffset: 0; }
            }
            .success-modal-title {
                font-size: 22px;
                font-weight: 700;
                color: #ffffff;
                margin-bottom: 8px;
            }
            .success-modal-message {
                font-size: 15px;
                color: #94a3b8;
                line-height: 1.5;
                margin-bottom: 20px;
            }
            .success-modal-message strong {
                color: #38bdf8;
                font-weight: 600;
            }
            .success-file-card {
                background: rgba(10, 14, 26, 0.7);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 16px;
                padding: 12px 16px;
                display: flex;
                align-items: center;
                gap: 12px;
                margin-bottom: 24px;
                text-align: left;
            }
            .success-file-icon {
                font-size: 28px;
                display: flex;
                align-items: center;
                justify-content: center;
                width: 44px;
                height: 44px;
                border-radius: 12px;
                background: rgba(3, 102, 214, 0.15);
                border: 1px solid rgba(3, 102, 214, 0.3);
                flex-shrink: 0;
            }
            .success-file-info {
                flex: 1;
                min-width: 0;
            }
            .success-file-name {
                font-size: 14px;
                font-weight: 600;
                color: #f1f5f9;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                display: block;
            }
            .success-file-meta {
                font-size: 12px;
                color: #64748b;
                display: flex;
                gap: 8px;
                margin-top: 2px;
            }
            .success-file-status {
                color: #22c55e;
                font-weight: 500;
            }
            .success-modal-btn {
                width: 100%;
                padding: 14px;
                border-radius: 40px;
                background: linear-gradient(135deg, #0366d6 0%, #22c55e 100%);
                color: white;
                font-size: 15px;
                font-weight: 600;
                border: none;
                cursor: pointer;
                transition: all 0.2s;
                box-shadow: 0 4px 15px rgba(34, 197, 94, 0.3);
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
            }
            .success-modal-btn:hover {
                transform: translateY(-2px);
                box-shadow: 0 8px 25px rgba(34, 197, 94, 0.45);
            }

            /* MODALES STANDARDS */
            .modal {
                display: none;
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0,0,0,0.8);
                backdrop-filter: blur(10px);
                align-items: center;
                justify-content: center;
                z-index: 1000;
            }
            .modal-content {
                background: linear-gradient(135deg, #1a1f2e 0%, #131725 100%);
                border-radius: 24px;
                max-width: 400px;
                width: 90%;
                overflow: hidden;
                animation: modalSlideIn 0.3s ease;
                border: 1px solid rgba(3, 102, 214, 0.3);
            }
            @keyframes modalSlideIn {
                from { opacity: 0; transform: translateY(-30px); }
                to { opacity: 1; transform: translateY(0); }
            }
            .modal-header {
                padding: 20px 24px;
                background: linear-gradient(135deg, #0366d6, #f68b1e);
                color: white;
            }
            .modal-header h3 { font-size: 20px; margin-bottom: 5px; }
            .modal-body { padding: 24px; }
            .modal-info {
                background: rgba(0,0,0,0.3);
                border-radius: 16px;
                padding: 15px;
                margin-bottom: 20px;
                border: 1px solid rgba(3, 102, 214, 0.2);
            }
            .modal-info-item {
                display: flex;
                justify-content: space-between;
                padding: 8px 0;
                border-bottom: 1px solid rgba(255,255,255,0.05);
            }
            .modal-info-item:last-child { border-bottom: none; }
            .modal-info-label { font-weight: 600; color: #8b92a8; }
            .modal-info-value { color: #e2e8f0; font-family: monospace; }
            .modal-buttons {
                display: flex;
                gap: 12px;
                margin-top: 20px;
            }
            .modal-btn {
                flex: 1;
                padding: 12px;
                border: none;
                border-radius: 40px;
                font-size: 14px;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.2s;
            }
            .modal-btn.confirm {
                background: linear-gradient(135deg, #0366d6, #f68b1e);
                color: white;
            }
            .modal-btn.confirm:hover {
                transform: translateY(-2px);
                box-shadow: 0 4px 12px rgba(3, 102, 214, 0.4);
            }
            .modal-btn.cancel {
                background: rgba(255,255,255,0.1);
                color: #e2e8f0;
                border: 1px solid rgba(255,255,255,0.1);
            }
            .modal-btn.cancel:hover { background: rgba(255,255,255,0.2); }

            /* BARRE DE PROGRESSION FLOTTANTE POUR TÉLÉCHARGEMENT */
            #downloadProgress {
                position: fixed;
                bottom: 25px;
                left: 50%;
                transform: translateX(-50%);
                width: 92%;
                max-width: 480px;
                background: linear-gradient(135deg, #182030 0%, #0e1320 100%);
                border-radius: 20px;
                padding: 16px 20px;
                box-shadow: 0 12px 45px rgba(0,0,0,0.6);
                z-index: 2000;
                animation: slideUp 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
                border: 1px solid rgba(3, 102, 214, 0.35);
                display: none;
            }
            @keyframes slideUp {
                from { opacity: 0; transform: translateX(-50%) translateY(20px); }
                to { opacity: 1; transform: translateX(-50%) translateY(0); }
            }
            .download-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 10px;
                font-size: 13px;
            }
            .download-filename {
                font-weight: 600;
                color: #f1f5f9;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                max-width: 65%;
                display: flex;
                align-items: center;
                gap: 6px;
            }
            .download-percent {
                font-weight: 700;
                color: #38bdf8;
                font-size: 14px;
            }
            .progress-track {
                background: rgba(10, 14, 26, 0.8);
                border-radius: 12px;
                height: 8px;
                overflow: hidden;
                position: relative;
                margin-bottom: 10px;
            }
            .progress-fill {
                height: 100%;
                background: linear-gradient(90deg, #0366d6, #38bdf8, #22c55e);
                background-size: 200% 100%;
                border-radius: 12px;
                transition: width 0.25s ease;
                animation: progressGlow 2s linear infinite;
            }
            @keyframes progressGlow {
                0% { background-position: 0% 50%; }
                100% { background-position: 200% 50%; }
            }
            .download-footer {
                display: flex;
                justify-content: space-between;
                align-items: center;
                font-size: 12px;
                color: #8b92a8;
            }
            .download-cancel-btn {
                background: rgba(244, 67, 54, 0.15);
                border: 1px solid rgba(244, 67, 54, 0.35);
                color: #f87171;
                padding: 4px 12px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.2s ease;
            }
            .download-cancel-btn:hover {
                background: #ef4444;
                color: white;
            }

            .footer {
                position: fixed;
                bottom: 0;
                left: 0;
                right: 0;
                text-align: center;
                padding: 12px;
                color: #5a6278;
                font-size: 12px;
                background: linear-gradient(135deg, #1a1f2e 0%, #0f131f 100%);
                border-top: 1px solid rgba(3, 102, 214, 0.2);
                z-index: 100;
                backdrop-filter: blur(10px);
            }

            .no-results {
                text-align: center;
                padding: 40px;
                color: #5a6278;
                font-size: 14px;
            }

            @media (max-width: 768px) {
                .header { flex-direction: column; align-items: stretch; }
                .search-container { margin-left: 0; max-width: none; }
                .connection-status { align-self: flex-end; }
                .clear-history-btn { align-self: flex-start; }
                .upload-header { flex-direction: column; text-align: center; }
                .file-grid { grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 12px; }
                .file-card { padding: 15px 8px; }
                .file-card-icon { font-size: 32px; }
                .file-card-name { font-size: 11px; }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="logo-area">
                    <img src="/static/pydrop1.png" alt="PyDrop" class="app-logo-img">
                    <h1><span>Py</span><span>Drop</span></h1>
                </div>
                
                <div class="search-container">
                    <div class="search-box">
                        <span class="search-icon"><img src="/static/icons/search.svg" class="svg-icon" style="width:16px;height:16px;" alt=""></span>
                        <input type="text" id="searchInput" class="search-input" placeholder="Rechercher un fichier ou dossier..." autocomplete="off">
                        <button id="searchClear" class="search-clear"><img src="/static/icons/x.svg" class="svg-icon" style="width:14px;height:14px;" alt=""></button>
                    </div>
                    <div id="searchInfo" class="search-info"></div>
                </div>
                
                <a href="{{ url_for('send_to_phone') }}" class="header-btn"><img src="/static/icons/upload.svg" class="svg-icon" style="width:16px;height:16px;vertical-align:-2px;margin-right:4px;" alt=""> Envoyer</a>
                
                <button id="clearHistoryBtn" class="clear-history-btn" title="Nettoyer l'historique des téléchargements interrompus"><img src="/static/icons/trash-2.svg" class="svg-icon" style="width:15px;height:15px;vertical-align:-2px;margin-right:4px;" alt=""> Nettoyer</button>
                
                <div id="connectionStatus" class="connection-status checking">
                    <div class="status-dot"></div>
                    <span>Vérification...</span>
                </div>
            </div>

            <div class="path">
                <span class="path-code"><img src="/static/icons/folder-open.svg" class="svg-icon" style="width:18px;height:18px;vertical-align:-3px;margin-right:6px;" alt=""> Vous êtes ici : <code>{{ path }}</code></span>
            </div>

            {% if not is_drive_list %}
            <!-- BARRE DE RACCOURCIS RAPIDES (ACCÈS DIRECT EN SOUS-DOSSIER) -->
            <div class="quick-nav-bar">
                <a href="{{ url_for('file_browser') }}" class="quick-nav-pill">
                    <img src="/static/icons/hard-drive.svg" class="svg-icon" style="width:14px;height:14px;" alt="">
                    <span>Accueil / Disques</span>
                </a>
                {% for sc in shortcuts %}
                <a href="{{ url_for('file_browser', path=sc['url_path']) }}" class="quick-nav-pill {% if current_path == sc['url_path'] %}active{% endif %}" title="{{ sc['path'] }}">
                    <img src="/static/icons/{{ sc['icon'] }}.svg" class="svg-icon" style="width:14px;height:14px;" alt="">
                    <span>{{ sc['name'] }}</span>
                </a>
                {% endfor %}
            </div>
            {% endif %}

            <div id="fileListContainer">
            {% if is_drive_list %}
                <div id="itemsContainer">
                    <!-- SECTION RACCOURCIS SYSTÈME (GRILLE 2/3 COLONNES) -->
                    {% if shortcuts %}
                    <div class="section-title">
                        <img src="/static/icons/folder-open.svg" class="svg-icon" style="width:18px;height:18px;" alt="">
                        <span>Accès Rapide & Dossiers Personnels</span>
                    </div>
                    <div class="shortcuts-grid">
                    {% for sc in shortcuts %}
                        <a href="{{ url_for('file_browser', path=sc['url_path']) }}" class="shortcut-card" data-name="{{ sc['name'].lower() }} {{ sc['sub'].lower() }}" style="--card-accent: {{ sc['color'] }};">
                            <div class="shortcut-icon-wrapper">
                                <img src="/static/icons/{{ sc['icon'] }}.svg" class="svg-icon" style="width:22px;height:22px;" alt="{{ sc['name'] }}">
                            </div>
                            <div class="shortcut-details">
                                <div class="shortcut-title">{{ sc['name'] }}</div>
                                <div class="shortcut-subtitle">{{ sc['sub'] }}</div>
                                {% if sc['item_count'] is not none %}
                                <div class="shortcut-badge">{{ sc['item_count'] }} élément(s)</div>
                                {% endif %}
                            </div>
                        </a>
                    {% endfor %}
                    </div>
                    {% endif %}

                    <!-- SECTION DISQUES & LECTEURS (AFFICHAGE EN LISTE) -->
                    <div class="section-title" style="margin-top: 26px;">
                        <img src="/static/icons/hard-drive.svg" class="svg-icon" style="width:18px;height:18px;" alt="">
                        <span>Lecteurs & Disques</span>
                    </div>
                    <div class="drive-list">
                    {% for drive in files_to_render %}
                        {% set percent = drive['stats']['percent_used'] %}
                        {% set status_class = 'danger' if percent > 90 else ('warning' if percent > 70 else '') %}
                        <a href="{{ url_for('file_browser', path=drive['url_path']) }}" class="drive-list-item" data-name="{{ drive.get('display_name', drive['name']).lower() }}">
                            <div class="drive-list-icon">
                                <img src="/static/icons/hard-drive.svg" alt="Lecteur">
                            </div>
                            <div class="drive-list-body">
                                <div class="drive-list-header">
                                    <div class="drive-list-name">{{ drive.get('display_name', drive['name']) }}</div>
                                    <div class="drive-list-percent {{ status_class }}">{{ percent }}% plein</div>
                                </div>
                                <div class="progress-bar-container">
                                    <div class="progress-bar-fill {{ status_class }}" style="width: {{ percent }}%;"></div>
                                </div>
                                <div class="drive-list-stats">
                                    <span><img src="/static/icons/pie-chart.svg" class="svg-icon" style="width:13px;height:13px;vertical-align:-2px;margin-right:4px;" alt=""> Utilisé : {{ drive['stats']['used'] }} / {{ drive['stats']['total'] }}</span>
                                    <span><img src="/static/icons/disc.svg" class="svg-icon" style="width:13px;height:13px;vertical-align:-2px;margin-right:4px;" alt=""> Disponible : {{ drive['stats']['free'] }}</span>
                                </div>
                            </div>
                            <div class="drive-list-action">
                                <img src="/static/icons/folder-open.svg" class="svg-icon" style="width:20px;height:20px;" alt="Ouvrir">
                            </div>
                        </a>
                    {% endfor %}
                    </div>
                </div>
            {% else %}
                <div class="view-toggle">
                    <button class="view-btn active" data-view="grid">Mosaïque</button>
                    <button class="view-btn" data-view="list">Liste</button>
                </div>
                
                <div class="file-grid" id="fileGrid">
                    {% set parent_path = os.path.abspath(os.path.join(current_path, '..')) %}
                    {% if sys.platform == 'win32' and current_path|length <= 4 %}
                        <div class="file-card up-card" data-name="remonter aux disques">
                            <div class="file-card-icon arrow-up"><img src="/static/icons/arrow-up.svg" class="svg-icon" style="width:28px;height:28px;" alt=""></div>
                            <div class="file-card-name">Remonter aux Disques</div>
                            <a href="{{ url_for('file_browser') }}" class="file-card-action">Aller</a>
                        </div>
                    {% elif current_path != '/' %}
                        {% set parent_url_path = parent_path[1:] if parent_path.startswith('/') else parent_path %}
                        <div class="file-card up-card" data-name="remonter parent">
                            <div class="file-card-icon arrow-up"><img src="/static/icons/arrow-up.svg" class="svg-icon" style="width:28px;height:28px;" alt=""></div>
                            <div class="file-card-name">Remonter</div>
                            <a href="{{ url_for('file_browser', path=parent_url_path | replace(bs, slash) ) }}" class="file-card-action">Aller</a>
                        </div>
                    {% endif %}

                    {% for f_name in directories %}
                        {% set full_folder_path = os.path.join(current_path, f_name) %}
                        {% set path_for_url = full_folder_path[1:] if full_folder_path.startswith('/') else full_folder_path %}
                        <div class="file-card folder" data-name="{{ display_names.get(f_name, f_name).lower() }}" data-type="folder" data-filename="{{ display_names.get(f_name, f_name) }}">
                            <div class="file-card-icon folder-icon"><img src="/static/icons/folder.svg" class="svg-icon" style="width:40px;height:40px;" alt=""></div>
                            <div class="file-card-name folder">{{ display_names.get(f_name, f_name) }}</div>
                            <a href="{{ url_for('file_browser', path=path_for_url | replace(bs, slash) ) }}" class="file-card-action">Ouvrir</a>
                        </div>
                    {% endfor %}

                    {% for f_name in file_list %}
                        {% set download_url = safe_downloads.get(f_name, '#') %}
                        <div class="file-card file" data-name="{{ display_names.get(f_name, f_name).lower() }}" data-type="file" data-filename="{{ display_names.get(f_name, f_name) }}">
                            <div class="file-card-icon file-icon" data-filename="{{ display_names.get(f_name, f_name) }}"><img src="/static/icons/{{ get_file_icon_name(f_name) }}.svg" class="svg-icon" style="width:40px;height:40px;" alt=""></div>
                            <div class="file-card-name file">{{ display_names.get(f_name, f_name) }}</div>
                            <a href="{{ download_url }}" class="download-link file-card-action" data-file="{{ display_names.get(f_name, f_name) }}">Télécharger</a>
                        </div>
                    {% endfor %}
                </div>
                
                <div class="file-list" id="fileList" style="display: none;">
                    {% set parent_path = os.path.abspath(os.path.join(current_path, '..')) %}
                    {% if sys.platform == 'win32' and current_path|length <= 4 %}
                        <div class="file-item up-link" data-name="remonter aux disques">
                            <div class="file-icon arrow-up"><img src="/static/icons/arrow-up.svg" class="svg-icon" style="width:20px;height:20px;" alt=""></div>
                            <div class="file-name">Remonter aux Disques</div>
                            <a href="{{ url_for('file_browser') }}" class="file-action">Aller</a>
                        </div>
                    {% elif current_path != '/' %}
                        {% set parent_url_path = parent_path[1:] if parent_path.startswith('/') else parent_path %}
                        <div class="file-item up-link" data-name="remonter parent">
                            <div class="file-icon arrow-up"><img src="/static/icons/arrow-up.svg" class="svg-icon" style="width:20px;height:20px;" alt=""></div>
                            <div class="file-name">Remonter</div>
                            <a href="{{ url_for('file_browser', path=parent_url_path | replace(bs, slash) ) }}" class="file-action">Aller</a>
                        </div>
                    {% endif %}

                    {% for f_name in directories %}
                        {% set full_folder_path = os.path.join(current_path, f_name) %}
                        {% set path_for_url = full_folder_path[1:] if full_folder_path.startswith('/') else full_folder_path %}
                        <div class="file-item" data-name="{{ display_names.get(f_name, f_name).lower() }}" data-type="folder" data-filename="{{ display_names.get(f_name, f_name) }}">
                            <div class="file-icon folder-icon"><img src="/static/icons/folder.svg" class="svg-icon" style="width:24px;height:24px;" alt=""></div>
                            <div class="file-name folder">{{ display_names.get(f_name, f_name) }}</div>
                            <a href="{{ url_for('file_browser', path=path_for_url | replace(bs, slash) ) }}" class="file-action">Ouvrir</a>
                        </div>
                    {% endfor %}

                    {% for f_name in file_list %}
                        {% set download_url = safe_downloads.get(f_name, '#') %}
                        <div class="file-item" data-name="{{ display_names.get(f_name, f_name).lower() }}" data-type="file" data-filename="{{ display_names.get(f_name, f_name) }}">
                            <div class="file-icon file-icon-item" data-filename="{{ display_names.get(f_name, f_name) }}"><img src="/static/icons/{{ get_file_icon_name(f_name) }}.svg" class="svg-icon" style="width:24px;height:24px;" alt=""></div>
                            <div class="file-name">{{ display_names.get(f_name, f_name) }}</div>
                            <a href="{{ download_url }}" class="download-link file-action" data-file="{{ display_names.get(f_name, f_name) }}">Télécharger</a>
                        </div>
                    {% endfor %}
                </div>
            {% endif %}
            </div>

            <div class="upload-section">
                <div class="upload-header">
                    <div class="upload-header-icon"><img src="/static/icons/upload.svg" class="svg-icon" style="width:32px;height:32px;" alt=""></div>
                    <div>
                        <h2>Transfert de fichiers</h2>
                        <p class="upload-subtitle">Envoyez des fichiers depuis votre appareil vers l'ordinateur</p>
                    </div>
                </div>
                
                <div class="upload-info">
                    <div class="upload-info-item">
                        <span class="upload-info-label">Dossier de destination</span>
                        <code class="upload-info-value">{{ upload_folder }}</code>
                    </div>
                </div>
                
                <form id="uploadForm" action="{{ url_for('upload_file') }}" method="post" enctype="multipart/form-data">
                    <div class="upload-area" id="uploadArea">
                        <div class="upload-area-content">
                            <div class="upload-area-icon"><img src="/static/icons/paperclip.svg" class="svg-icon" style="width:36px;height:36px;" alt=""></div>
                            <div class="upload-area-text">
                                <span class="upload-area-title">Glissez vos fichiers ici ou</span>
                                <label for="uploadFileInput" class="upload-area-button">
                                    Parcourir
                                </label>
                            </div>
                            <div class="upload-area-hint">Tous types de fichiers acceptés</div>
                            <input id="uploadFileInput" type="file" name="file" multiple style="display: none;" onchange="handleFileInputChange(this)">
                            <div id="selected-files" class="selected-files"></div>
                        </div>
                    </div>
                    
                    <div class="upload-action">
                        <button id="uploadBtn" type="submit">
                            Envoyer les fichiers
                        </button>
                    </div>
                </form>

                <div id="uploadProgress" class="upload-progress">
                    <div class="upload-progress-card">
                        <div class="upload-progress-header">
                            <div class="upload-progress-title">
                                <span><img src="/static/icons/clock.svg" class="svg-icon" style="width:16px;height:16px;vertical-align:-2px;margin-right:4px;" alt=""></span>
                                <span>Téléversement en cours</span>
                            </div>
                            <span class="upload-progress-percent" id="uploadProgressPercent">0%</span>
                        </div>
                        <div class="upload-progress-bar">
                            <div class="upload-progress-fill" id="uploadProgressBar" style="width:0%;"></div>
                        </div>
                        <div class="upload-progress-info">
                            <span class="upload-progress-filename" id="uploadFileName">-</span>
                            <span class="upload-progress-meta" id="uploadMeta">0 MB</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <div class="footer">
            © {{ year }} — PyDrop by Seraphin
        </div>

        <!-- Modales -->
        <!-- Modale de Succès avec Animation SVG -->
        <div id="transferSuccessModal" class="success-modal-overlay">
            <div class="success-modal-card">
                <button class="success-modal-close-btn" onclick="closeSuccessModal()" title="Fermer"><img src="/static/icons/x.svg" class="svg-icon" style="width:16px;height:16px;" alt=""></button>
                
                <div class="success-icon-wrap">
                    <div class="success-icon-glow"></div>
                    <svg class="success-checkmark-svg" viewBox="0 0 52 52">
                        <circle class="success-checkmark-circle" cx="26" cy="26" r="23"/>
                        <path class="success-checkmark-check" d="M14.1 27.2l7.1 7.2 16.7-16.8"/>
                    </svg>
                </div>
                
                <h3 class="success-modal-title" id="successModalTitle">Transfert réussi !</h3>
                <p class="success-modal-message" id="successModalMsg">Fichier traité avec succès</p>
                
                <div class="success-file-card">
                    <div class="success-file-icon" id="successModalFileIcon"><img src="/static/icons/file.svg" class="svg-icon" style="width:24px;height:24px;" alt=""></div>
                    <div class="success-file-info">
                        <span class="success-file-name" id="successModalFileName">-</span>
                        <div class="success-file-meta">
                            <span id="successModalFileSize">-</span>
                            <span>•</span>
                            <span class="success-file-status" id="successModalStatus">Terminé</span>
                        </div>
                    </div>
                </div>
                
                <button class="success-modal-btn" onclick="closeSuccessModal()">
                    <span>Fermer</span>
                    <span>✓</span>
                </button>
            </div>
        </div>

        <!-- Modales de confirmation & reprise -->
        <div id="cancelModal" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <h3>Annuler le téléchargement</h3>
                </div>
                <div class="modal-body">
                    <div class="modal-info">
                        <div class="modal-info-item">
                            <span class="modal-info-label">Fichier</span>
                            <span class="modal-info-value" id="cancelModalFileName">-</span>
                        </div>
                        <div class="modal-info-item">
                            <span class="modal-info-label">Progression</span>
                            <span class="modal-info-value" id="cancelModalProgress">-</span>
                        </div>
                    </div>
                    <p style="text-align: center; margin: 20px 0;">Êtes-vous sûr de vouloir annuler ce téléchargement ?</p>
                    <div class="modal-buttons">
                        <button class="modal-btn cancel" id="cancelModalNoBtn">Non, continuer</button>
                        <button class="modal-btn confirm" id="cancelModalYesBtn">Oui, annuler</button>
                    </div>
                </div>
            </div>
        </div>

        <div id="resumeModal" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <h3><img src="/static/icons/download.svg" class="svg-icon" style="width:20px;height:20px;vertical-align:-3px;margin-right:6px;" alt=""> Reprise du téléchargement</h3>
                </div>
                <div class="modal-body">
                    <div class="modal-info">
                        <div class="modal-info-item">
                            <span class="modal-info-label">Fichier</span>
                            <span class="modal-info-value" id="modalFileName">-</span>
                        </div>
                        <div class="modal-info-item">
                            <span class="modal-info-label">Progression</span>
                            <span class="modal-info-value" id="modalProgress">-</span>
                        </div>
                        <div class="modal-info-item">
                            <span class="modal-info-label">Téléchargé</span>
                            <span class="modal-info-value" id="modalDownloaded">-</span>
                        </div>
                        <div class="modal-info-item">
                            <span class="modal-info-label">Total</span>
                            <span class="modal-info-value" id="modalTotal">-</span>
                        </div>
                    </div>
                    <div class="progress-bar-small">
                        <div id="modalProgressBar" class="progress-bar-fill" style="width:0%;"></div>
                    </div>
                    <div class="modal-buttons">
                        <button class="modal-btn cancel" id="modalCancelBtn">Annuler</button>
                        <button class="modal-btn confirm" id="modalConfirmBtn">Reprendre</button>
                    </div>
                </div>
            </div>
        </div>

        <div id="reconnectModal" class="modal">
            <div class="modal-content">
                <div class="modal-header">
                    <h3><img src="/static/icons/refresh-cw.svg" class="svg-icon" style="width:20px;height:20px;vertical-align:-3px;margin-right:6px;" alt=""> Connexion rétablie</h3>
                </div>
                <div class="modal-body">
                    <div class="modal-info">
                        <div class="modal-info-item">
                            <span class="modal-info-label">Fichier</span>
                            <span class="modal-info-value" id="reconnectFileName">-</span>
                        </div>
                        <div class="modal-info-item">
                            <span class="modal-info-label">Progression</span>
                            <span class="modal-info-value" id="reconnectProgress">-</span>
                        </div>
                    </div>
                    <div class="modal-buttons">
                        <button class="modal-btn cancel" id="reconnectCancelBtn">Annuler</button>
                        <button class="modal-btn confirm" id="reconnectConfirmBtn">Reprendre</button>
                    </div>
                </div>
            </div>
        </div>

        <!-- Barre de progression de téléchargement flottante -->
        <div id="downloadProgress">
            <div class="download-header">
                <div class="download-filename">
                    <span><img src="/static/icons/download.svg" class="svg-icon" style="width:16px;height:16px;vertical-align:-2px;margin-right:4px;" alt=""></span>
                    <span id="downloadFileName">-</span>
                </div>
                <span class="download-percent" id="downloadProgressPercent">0%</span>
            </div>
            <div class="progress-track">
                <div id="downloadProgressBar" class="progress-fill" style="width:0%;"></div>
            </div>
            <div class="download-footer">
                <span id="downloadProgressText">0 MB / 0 MB</span>
                <button id="downloadCancelBtn" class="download-cancel-btn">Annuler</button>
            </div>
        </div>

        <div id="notification"></div>
        <script>
            let currentDownload = null;
            let downloadProgressInterval = null;
            let wasOffline = false;
            let pingInterval = null;
            let activeDownloadXhr = null;
            let successModalCloseCallback = null;

            function escapeHtml(text) {
                if (!text) return '';
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }

            function formatBytes(bytes, decimals = 1) {
                if (!bytes || bytes === 0) return '0 B';
                const k = 1024;
                const dm = decimals < 0 ? 0 : decimals;
                const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
                const i = Math.floor(Math.log(bytes) / Math.log(k));
                return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
            }

            function getFileIcon(filename, type = 'item') {
                if (!filename) {
                    const sz = type === 'card' ? '40px' : (type === 'preview' ? '28px' : '22px');
                    return `<img src="/static/icons/file.svg" class="svg-icon" style="width:${sz};height:${sz};" alt="file">`;
                }
                const ext = filename.split('.').pop().toLowerCase();
                const map = {
                    'jpg': 'image', 'jpeg': 'image', 'png': 'image', 'gif': 'image', 'webp': 'image', 'svg': 'image', 'bmp': 'image', 'ico': 'image', 'tiff': 'image', 'psd': 'image', 'ai': 'image',
                    'mp4': 'video', 'mkv': 'video', 'avi': 'video', 'mov': 'video', 'wmv': 'video', 'webm': 'video', 'm4v': 'video', 'flv': 'video', '3gp': 'video', 'ts': 'video',
                    'mp3': 'music', 'wav': 'music', 'flac': 'music', 'aac': 'music', 'ogg': 'music', 'm4a': 'music', 'wma': 'music', 'opus': 'music', 'mid': 'music', 'midi': 'music',
                    'pdf': 'file-pdf',
                    'doc': 'file-doc', 'docx': 'file-doc', 'odt': 'file-doc', 'rtf': 'file-doc', 'dot': 'file-doc', 'dotx': 'file-doc',
                    'xls': 'file-spreadsheet', 'xlsx': 'file-spreadsheet', 'csv': 'file-spreadsheet', 'ods': 'file-spreadsheet', 'tsv': 'file-spreadsheet', 'xlsm': 'file-spreadsheet',
                    'ppt': 'file-presentation', 'pptx': 'file-presentation', 'odp': 'file-presentation', 'pps': 'file-presentation', 'ppsx': 'file-presentation',
                    'py': 'file-python', 'pyw': 'file-python', 'ipynb': 'file-python',
                    'php': 'file-php',
                    'cs': 'file-cs',
                    'c': 'file-cpp', 'cpp': 'file-cpp', 'cc': 'file-cpp', 'cxx': 'file-cpp', 'h': 'file-cpp', 'hpp': 'file-cpp',
                    'java': 'file-java', 'class': 'file-java', 'jar': 'file-java',
                    'js': 'file-js', 'mjs': 'file-js', 'cjs': 'file-js', 'jsx': 'file-js',
                    'ts': 'file-ts', 'tsx': 'file-ts',
                    'html': 'file-html', 'htm': 'file-html', 'xhtml': 'file-html', 'vue': 'file-html',
                    'css': 'file-css', 'scss': 'file-css', 'sass': 'file-css', 'less': 'file-css',
                    'json': 'file-json', 'xml': 'file-json', 'yaml': 'file-json', 'yml': 'file-json', 'toml': 'file-json', 'ini': 'file-json', 'env': 'file-json', 'config': 'file-json', 'lock': 'file-json',
                    'sql': 'file-sql',
                    'sh': 'file-sh', 'bash': 'file-sh', 'zsh': 'file-sh', 'bat': 'file-sh', 'ps1': 'file-sh', 'cmd': 'file-sh',
                    'rs': 'file-rs', 'go': 'file-go', 'rb': 'file-rb',
                    'swift': 'file-swift', 'kt': 'file-swift', 'kts': 'file-swift',
                    'zip': 'file-archive', 'rar': 'file-archive', '7z': 'file-archive', 'tar': 'file-archive', 'gz': 'file-archive', 'xz': 'file-archive', 'bz2': 'file-archive', 'tgz': 'file-archive',
                    'txt': 'file-text', 'md': 'file-text', 'log': 'file-text',
                    'iso': 'disc', 'dmg': 'disc', 'img': 'disc', 'vhd': 'disc',
                    'exe': 'settings', 'msi': 'settings', 'deb': 'settings', 'rpm': 'settings',
                    'apk': 'smartphone', 'aab': 'smartphone', 'ipa': 'smartphone'
                };
                const icon = map[ext] || 'file';
                const sz = type === 'card' ? '40px' : (type === 'preview' ? '28px' : '22px');
                return `<img src="/static/icons/${icon}.svg" class="svg-icon" style="width:${sz};height:${sz};" alt="${ext}">`;
            }

            function showSuccessModal({ type, title, filename, size, message, onClose }) {
                const modal = document.getElementById('transferSuccessModal');
                if (!modal) return;
                
                successModalCloseCallback = onClose || null;
                
                document.getElementById('successModalTitle').textContent = title || (type === 'upload' ? 'Téléversement réussi !' : 'Téléchargement réussi !');
                document.getElementById('successModalMsg').innerHTML = message || (type === 'upload' ? `Fichier <strong>${escapeHtml(filename)}</strong>, fichier téléversé avec succès !` : `Fichier <strong>${escapeHtml(filename)}</strong>, fichier reçu avec succès !`);
                
                const iconEl = document.getElementById('successModalFileIcon');
                if (iconEl) iconEl.innerHTML = getFileIcon(filename, 'item');
                
                const nameEl = document.getElementById('successModalFileName');
                if (nameEl) nameEl.textContent = filename || '-';
                
                const sizeEl = document.getElementById('successModalFileSize');
                if (sizeEl) sizeEl.textContent = size || '';
                
                const statusEl = document.getElementById('successModalStatus');
                if (statusEl) statusEl.textContent = type === 'upload' ? 'Envoyé avec succès' : 'Reçu avec succès';

                // Re-trigger animation
                const svg = modal.querySelector('.success-checkmark-svg');
                if (svg) {
                    const newSvg = svg.cloneNode(true);
                    svg.parentNode.replaceChild(newSvg, svg);
                }

                modal.classList.add('active');
            }

            function closeSuccessModal() {
                const modal = document.getElementById('transferSuccessModal');
                if (modal) modal.classList.remove('active');
                if (typeof successModalCloseCallback === 'function') {
                    const cb = successModalCloseCallback;
                    successModalCloseCallback = null;
                    cb();
                }
            }

            function showNotification(message, isError = false) {
                const notif = document.getElementById('notification');
                if (!notif) return;
                notif.textContent = message;
                notif.style.position = 'fixed';
                notif.style.bottom = '80px';
                notif.style.left = '50%';
                notif.style.transform = 'translateX(-50%)';
                notif.style.padding = '12px 24px';
                notif.style.borderRadius = '30px';
                notif.style.background = isError ? 'rgba(244, 67, 54, 0.9)' : 'rgba(3, 102, 214, 0.9)';
                notif.style.color = 'white';
                notif.style.boxShadow = '0 4px 20px rgba(0,0,0,0.3)';
                notif.style.zIndex = '2100';
                notif.style.display = 'block';
                notif.style.backdropFilter = 'blur(10px)';
                notif.style.fontWeight = '500';
                notif.style.fontSize = '14px';
                setTimeout(() => { notif.style.display = 'none'; }, 4000);
            }

            function clearDownloadHistory() {
                try {
                    const keys = Object.keys(localStorage);
                    let count = 0;
                    keys.forEach(key => {
                        if (key.startsWith('download_') || key.startsWith('transfer_')) {
                            localStorage.removeItem(key);
                            count++;
                        }
                    });
                    showNotification(`Historique nettoyé (${count} éléments supprimés)`);
                } catch (e) {
                    showNotification('Erreur lors du nettoyage', true);
                }
            }

            async function checkConnection() {
                const statusDiv = document.getElementById('connectionStatus');
                if (!statusDiv) return;
                try {
                    const controller = new AbortController();
                    const timeoutId = setTimeout(() => controller.abort(), 2000);
                    const response = await fetch('/api/ping', { method: 'HEAD', signal: controller.signal, cache: 'no-store' });
                    clearTimeout(timeoutId);
                    if (response.ok) {
                        statusDiv.className = 'connection-status online';
                        statusDiv.querySelector('span').textContent = 'Connecté';
                        if (wasOffline) {
                            wasOffline = false;
                            showNotification('Connexion rétablie !');
                        }
                    } else { throw new Error('Response not ok'); }
                } catch (e) {
                    statusDiv.className = 'connection-status offline';
                    statusDiv.querySelector('span').textContent = 'Déconnecté';
                    if (!wasOffline) {
                        wasOffline = true;
                        showNotification('Connexion perdue avec le serveur', true);
                    }
                }
            }

            function startPing() {
                checkConnection();
                if (pingInterval) clearInterval(pingInterval);
                pingInterval = setInterval(checkConnection, 3000);
            }

            function initSearch() {
                const searchInput = document.getElementById('searchInput');
                const searchClear = document.getElementById('searchClear');
                const searchInfo = document.getElementById('searchInfo');
                if (!searchInput) return;

                function getElements() {
                    const itemsContainer = document.getElementById('itemsContainer');
                    if (itemsContainer) {
                        return { items: itemsContainer.querySelectorAll('.shortcut-card, .drive-list-item'), isGrid: true };
                    }
                    const grid = document.getElementById('fileGrid');
                    const isGrid = grid && (grid.style.display !== 'none' && getComputedStyle(grid).display !== 'none');
                    if (isGrid) {
                        return { items: document.querySelectorAll('#fileGrid .file-card:not(.up-card)'), isGrid: true };
                    } else {
                        return { items: document.querySelectorAll('#fileList .file-item:not(.up-link)'), isGrid: false };
                    }
                }

                function performSearch() {
                    const term = searchInput.value.toLowerCase().trim();
                    searchClear.style.display = term ? 'block' : 'none';
                    const { items } = getElements();
                    let visibleCount = 0;
                    let totalCount = items.length;

                    items.forEach(item => {
                        const name = item.getAttribute('data-name') || '';
                        if (name.includes(term)) {
                            item.style.display = '';
                            visibleCount++;
                        } else {
                            item.style.display = 'none';
                        }
                    });

                    if (term && searchInfo) {
                        searchInfo.textContent = `${visibleCount} sur ${totalCount} élément(s)`;
                    } else if (searchInfo) {
                        searchInfo.textContent = '';
                    }

                    const upElements = document.querySelectorAll('.up-card, .up-link');
                    upElements.forEach(el => { el.style.display = term ? 'none' : ''; });
                }

                searchInput.addEventListener('input', performSearch);
                if (searchClear) {
                    searchClear.addEventListener('click', () => {
                        searchInput.value = '';
                        performSearch();
                        searchInput.focus();
                    });
                }
                searchInput.addEventListener('keydown', (e) => {
                    if (e.key === 'Escape') {
                        searchInput.value = '';
                        performSearch();
                    }
                });
            }

            function initViewToggle() {
                const viewBtns = document.querySelectorAll('.view-btn');
                const fileGrid = document.getElementById('fileGrid');
                const fileList = document.getElementById('fileList');
                if (!viewBtns.length) return;

                const savedView = localStorage.getItem('preferredView') || 'grid';
                setView(savedView);

                viewBtns.forEach(btn => {
                    btn.addEventListener('click', () => {
                        const view = btn.getAttribute('data-view');
                        setView(view);
                        localStorage.setItem('preferredView', view);
                    });
                });

                function setView(view) {
                    viewBtns.forEach(btn => {
                        btn.classList.toggle('active', btn.getAttribute('data-view') === view);
                    });
                    if (view === 'grid') {
                        if (fileGrid) fileGrid.style.display = 'grid';
                        if (fileList) fileList.style.display = 'none';
                    } else {
                        if (fileGrid) fileGrid.style.display = 'none';
                        if (fileList) fileList.style.display = 'block';
                    }
                }
            }

            function setFileIcons() {
                document.querySelectorAll('.file-icon, .file-icon-item, .file-card-icon.file-icon').forEach(el => {
                    const filename = el.getAttribute('data-filename');
                    if (filename) {
                        const isCard = el.classList.contains('file-card-icon');
                        el.innerHTML = getFileIcon(filename, isCard ? 'card' : 'item');
                    }
                });
            }

            // Gestion des téléchargements avec barre de progression temps réel et modale de succès
            function handleDownloadClick(e) {
                const target = e.target.closest('.download-link');
                if (!target) return;
                e.preventDefault();
                const url = target.getAttribute('href');
                const filename = target.getAttribute('data-file') || url.split('/').pop() || 'fichier';
                downloadFileWithProgress(url, filename);
            }

            function downloadFileWithProgress(url, filename) {
                if (activeDownloadXhr) {
                    activeDownloadXhr.abort();
                }

                const progressEl = document.getElementById('downloadProgress');
                const progressBar = document.getElementById('downloadProgressBar');
                const progressPercent = document.getElementById('downloadProgressPercent');
                const progressFileName = document.getElementById('downloadFileName');
                const progressText = document.getElementById('downloadProgressText');
                const cancelBtn = document.getElementById('downloadCancelBtn');

                if (!progressEl) {
                    window.location.href = url;
                    return;
                }

                progressEl.style.display = 'block';
                progressBar.style.width = '0%';
                progressPercent.textContent = '0%';
                progressFileName.textContent = filename;
                progressText.textContent = 'Initialisation...';

                const xhr = new XMLHttpRequest();
                activeDownloadXhr = xhr;
                xhr.open('GET', url, true);
                xhr.responseType = 'blob';

                const startTime = Date.now();

                xhr.onprogress = function(event) {
                    if (event.lengthComputable && event.total > 0) {
                        const pct = Math.min(100, Math.round((event.loaded / event.total) * 100));
                        progressBar.style.width = pct + '%';
                        progressPercent.textContent = pct + '%';
                        
                        const elapsed = (Date.now() - startTime) / 1000;
                        const speed = elapsed > 0 ? (event.loaded / elapsed) : 0;
                        progressText.textContent = `${formatBytes(event.loaded)} / ${formatBytes(event.total)} • ${formatBytes(speed)}/s`;
                    } else {
                        progressBar.style.width = '100%';
                        progressPercent.textContent = '...';
                        progressText.textContent = `${formatBytes(event.loaded)} reçus`;
                    }
                };

                xhr.onload = function() {
                    if (xhr.status === 200) {
                        progressBar.style.width = '100%';
                        progressPercent.textContent = '100%';
                        
                        const blob = xhr.response;
                        const blobUrl = window.URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.style.display = 'none';
                        a.href = blobUrl;
                        a.download = filename;
                        document.body.appendChild(a);
                        a.click();
                        
                        setTimeout(() => {
                            window.URL.revokeObjectURL(blobUrl);
                            if (a.parentNode) document.body.removeChild(a);
                        }, 1000);

                        setTimeout(() => {
                            progressEl.style.display = 'none';
                        }, 400);

                        showSuccessModal({
                            type: 'download',
                            title: 'Téléchargement réussi !',
                            filename: filename,
                            size: formatBytes(blob.size),
                            message: `Fichier <strong>${escapeHtml(filename)}</strong>, fichier reçu avec succès !`
                        });
                    } else {
                        progressEl.style.display = 'none';
                        showNotification('Erreur de téléchargement (' + xhr.status + ')', true);
                    }
                    activeDownloadXhr = null;
                };

                xhr.onerror = function() {
                    progressEl.style.display = 'none';
                    showNotification('Erreur réseau lors du téléchargement', true);
                    activeDownloadXhr = null;
                };

                xhr.onabort = function() {
                    progressEl.style.display = 'none';
                    showNotification('Téléchargement annulé');
                    activeDownloadXhr = null;
                };

                if (cancelBtn) {
                    cancelBtn.onclick = function() {
                        if (activeDownloadXhr) {
                            activeDownloadXhr.abort();
                        }
                    };
                }

                xhr.send();
            }

            // Gestion de l'upload avec barre de progression temps réel et modale de succès
            function uploadFilesWithProgress(files) {
                if (!files || files.length === 0) {
                    showNotification('Veuillez sélectionner au moins un fichier', true);
                    return;
                }

                const formData = new FormData();
                let totalSize = 0;
                for (let i = 0; i < files.length; i++) {
                    formData.append('file', files[i]);
                    totalSize += files[i].size;
                }

                const progressContainer = document.getElementById('uploadProgress');
                const progressBar = document.getElementById('uploadProgressBar');
                const progressPercent = document.getElementById('uploadProgressPercent');
                const progressFileName = document.getElementById('uploadFileName');
                const progressMeta = document.getElementById('uploadMeta');
                const uploadBtn = document.getElementById('uploadBtn');

                if (progressContainer) progressContainer.style.display = 'block';
                if (progressBar) progressBar.style.width = '0%';
                if (progressPercent) progressPercent.textContent = '0%';
                
                const mainName = files.length === 1 ? files[0].name : `${files.length} fichiers`;
                if (progressFileName) progressFileName.textContent = mainName;
                if (progressMeta) progressMeta.textContent = `0 B / ${formatBytes(totalSize)}`;

                if (uploadBtn) {
                    uploadBtn.disabled = true;
                    uploadBtn.innerHTML = '⏳ Envoi en cours...';
                }

                const xhr = new XMLHttpRequest();
                xhr.open('POST', '/upload', true);
                xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');

                const startTime = Date.now();

                xhr.upload.onprogress = function(event) {
                    if (event.lengthComputable && event.total > 0) {
                        const pct = Math.min(100, Math.round((event.loaded / event.total) * 100));
                        if (progressBar) progressBar.style.width = pct + '%';
                        if (progressPercent) progressPercent.textContent = pct + '%';
                        
                        const elapsed = (Date.now() - startTime) / 1000;
                        const speed = elapsed > 0 ? (event.loaded / elapsed) : 0;
                        if (progressMeta) {
                            progressMeta.textContent = `${formatBytes(event.loaded)} / ${formatBytes(event.total)} (${formatBytes(speed)}/s)`;
                        }
                    }
                };

                xhr.onload = function() {
                    if (uploadBtn) {
                        uploadBtn.disabled = false;
                        uploadBtn.innerHTML = 'Envoyer les fichiers';
                    }

                    if (xhr.status >= 200 && xhr.status < 300) {
                        if (progressBar) progressBar.style.width = '100%';
                        if (progressPercent) progressPercent.textContent = '100%';

                        const fileInput = document.getElementById('uploadFileInput');
                        if (fileInput) fileInput.value = '';
                        const selectedContainer = document.getElementById('selected-files');
                        if (selectedContainer) selectedContainer.innerHTML = '';

                        setTimeout(() => {
                            if (progressContainer) progressContainer.style.display = 'none';
                        }, 500);

                        const msg = files.length === 1
                            ? `Fichier <strong>${escapeHtml(files[0].name)}</strong>, fichier téléversé avec succès !`
                            : `<strong>${files.length} fichiers</strong> téléversés avec succès !`;

                        showSuccessModal({
                            type: 'upload',
                            title: 'Téléversement réussi !',
                            filename: files[0].name + (files.length > 1 ? ` (+${files.length - 1})` : ''),
                            size: formatBytes(totalSize),
                            message: msg,
                            onClose: () => {
                                window.location.reload();
                            }
                        });
                    } else {
                        if (progressContainer) progressContainer.style.display = 'none';
                        showNotification("Erreur lors de l'envoi (" + xhr.status + ")", true);
                    }
                };

                xhr.onerror = function() {
                    if (uploadBtn) {
                        uploadBtn.disabled = false;
                        uploadBtn.innerHTML = 'Envoyer les fichiers';
                    }
                    if (progressContainer) progressContainer.style.display = 'none';
                    showNotification("Erreur réseau pendant l'envoi", true);
                };

                xhr.send(formData);
            }

            function handleFileInputChange(input) {
                const container = document.getElementById('selected-files');
                if (!container) return;
                container.innerHTML = '';
                if (input.files && input.files.length > 0) {
                    Array.from(input.files).forEach((file, index) => {
                        const div = document.createElement('div');
                        div.className = 'file-item';
                        div.innerHTML = `
                            <span class="file-name">${escapeHtml(file.name)}</span>
                            <span class="file-size">${formatBytes(file.size)}</span>
                            <button type="button" class="remove-file" onclick="removeSelectedFile(${index})" title="Supprimer"><img src="/static/icons/x.svg" class="svg-icon" style="width:12px;height:12px;" alt=""></button>
                        `;
                        container.appendChild(div);
                    });
                }
            }

            function removeSelectedFile(index) {
                const input = document.getElementById('uploadFileInput');
                if (!input || !input.files) return;
                const dt = new DataTransfer();
                Array.from(input.files).forEach((file, i) => {
                    if (i !== index) dt.items.add(file);
                });
                input.files = dt.files;
                handleFileInputChange(input);
            }

            // Initialisation
            document.addEventListener('DOMContentLoaded', () => {
                startPing();
                initSearch();
                initViewToggle();
                setFileIcons();
                document.addEventListener('click', handleDownloadClick);
                
                const clearBtn = document.getElementById('clearHistoryBtn');
                if (clearBtn) {
                    clearBtn.addEventListener('click', clearDownloadHistory);
                }

                // Glisser-déposer sur la zone d'upload
                const uploadArea = document.getElementById('uploadArea');
                const fileInput = document.getElementById('uploadFileInput');

                if (uploadArea) {
                    uploadArea.addEventListener('dragover', (e) => {
                        e.preventDefault();
                        uploadArea.classList.add('drag-over');
                    });
                    uploadArea.addEventListener('dragleave', () => {
                        uploadArea.classList.remove('drag-over');
                    });
                    uploadArea.addEventListener('drop', (e) => {
                        e.preventDefault();
                        uploadArea.classList.remove('drag-over');
                        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                            if (fileInput) {
                                fileInput.files = e.dataTransfer.files;
                                handleFileInputChange(fileInput);
                            }
                        }
                    });
                }

                const uploadForm = document.getElementById('uploadForm');
                if (uploadForm) {
                    uploadForm.addEventListener('submit', function(e) {
                        e.preventDefault();
                        const input = document.getElementById('uploadFileInput');
                        if (!input || !input.files || input.files.length === 0) {
                            showNotification('Veuillez sélectionner au moins un fichier', true);
                            return;
                        }
                        uploadFilesWithProgress(input.files);
                    });
                }
            });
        </script>
    </body>
    </html>
    """
    
    return render_template_string(
        html_template,
        path=current_path or "Poste de travail",
        current_path=current_path,
        is_drive_list=is_drive_list,
        shortcuts=shortcuts,
        files_to_render=files_to_render,
        directories=sorted(directories, key=lambda s: s.lower()),
        file_list=sorted(file_list, key=lambda s: s.lower()),
        display_names=display_names,
        safe_downloads=safe_downloads,
        upload_folder=UPLOAD_FOLDER,
        get_file_icon_name=get_file_icon_name,
        year=year,
        os=os,
        sys=sys,
        bs=bs,
        slash=slash
    )

@app.route('/download/<path:filepath>')
def download_file(filepath):
    """Téléchargement d'un fichier avec streaming et suivi de progression en temps réel"""
    if sys.platform != 'win32' and not filepath.startswith('/'):
        filepath = '/' + filepath
    
    abs_path = os.path.abspath(filepath)
    if not os.path.exists(abs_path) or os.path.isdir(abs_path):
        return "Fichier introuvable", 404
        
    filename = os.path.basename(abs_path)
    file_size = os.path.getsize(abs_path)
    transfer_id = str(uuid.uuid4())[:8]
    start_time = time.time()
    
    ACTIVE_TRANSFERS[transfer_id] = {
        'id': transfer_id,
        'filename': filename,
        'type': 'download',
        'direction': 'PC → Téléphone',
        'size': file_size,
        'formatted_size': format_size(file_size),
        'transferred': 0,
        'speed': 0,
        'speed_str': 'En cours...',
        'percent': 0,
        'status': 'running',
        'started_at': start_time,
        'icon': get_file_icon_name(filename)
    }

    def generate_chunks():
        chunk_size = 256 * 1024  # 256 KB
        transferred = 0
        last_time = time.time()
        last_transferred = 0
        try:
            with open(abs_path, 'rb') as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    transferred += len(chunk)
                    now = time.time()
                    elapsed = now - last_time
                    if elapsed >= 0.25:
                        speed = (transferred - last_transferred) / elapsed if elapsed > 0 else 0
                        pct = int((transferred / file_size) * 100) if file_size > 0 else 100
                        if transfer_id in ACTIVE_TRANSFERS:
                            ACTIVE_TRANSFERS[transfer_id]['transferred'] = transferred
                            ACTIVE_TRANSFERS[transfer_id]['percent'] = pct
                            ACTIVE_TRANSFERS[transfer_id]['speed'] = speed
                            ACTIVE_TRANSFERS[transfer_id]['speed_str'] = f"{format_size(speed)}/s"
                        last_time = now
                        last_transferred = transferred
                    yield chunk
            
            if transfer_id in ACTIVE_TRANSFERS:
                ACTIVE_TRANSFERS[transfer_id]['transferred'] = file_size
                ACTIVE_TRANSFERS[transfer_id]['percent'] = 100
                ACTIVE_TRANSFERS[transfer_id]['status'] = 'completed'
            
            TRANSFER_HISTORY['sent'].insert(0, {
                'name': filename,
                'size': file_size,
                'formatted_size': format_size(file_size),
                'timestamp': time.time(),
                'date_str': datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                'icon': get_file_icon_name(filename),
                'status': 'Terminé'
            })
            if len(TRANSFER_HISTORY['sent']) > 50:
                TRANSFER_HISTORY['sent'].pop()
        except Exception as e:
            if transfer_id in ACTIVE_TRANSFERS:
                ACTIVE_TRANSFERS[transfer_id]['status'] = 'error'
            raise e
        finally:
            def clean_active(tid):
                time.sleep(6)
                if tid in ACTIVE_TRANSFERS:
                    del ACTIVE_TRANSFERS[tid]
            threading.Thread(target=clean_active, args=(transfer_id,), daemon=True).start()

    from urllib.parse import quote
    response = Response(
        stream_with_context(generate_chunks()),
        mimetype='application/octet-stream'
    )
    response.headers['Content-Disposition'] = f'attachment; filename="{quote(filename)}"'
    response.headers['Content-Length'] = str(file_size)
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = '*'
    return response

@app.route('/upload', methods=['POST'])
def upload_file():
    """Réception de fichiers uploadés depuis le navigateur avec support AJAX et suivi de progression"""
    is_xhr = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')
    
    if 'file' not in request.files:
        if is_xhr:
            return jsonify({'status': 'error', 'message': 'Aucun fichier fourni'}), 400
        return redirect(request.referrer or url_for('transfers_page'))
    
    files = request.files.getlist('file')
    saved_files = []
    total_size = 0
    
    for file in files:
        if file and file.filename:
            filename = secure_filename(file.filename)
            dest_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
            transfer_id = str(uuid.uuid4())[:8]
            ACTIVE_TRANSFERS[transfer_id] = {
                'id': transfer_id,
                'filename': filename,
                'type': 'upload',
                'direction': 'Téléphone → PC',
                'size': 0,
                'formatted_size': 'Calcul...',
                'transferred': 0,
                'speed': 0,
                'speed_str': 'En cours...',
                'percent': 75,
                'status': 'running',
                'started_at': time.time(),
                'icon': get_file_icon_name(filename)
            }
            
            file.save(dest_path)
            file_size = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
            total_size += file_size
            
            ACTIVE_TRANSFERS[transfer_id]['size'] = file_size
            ACTIVE_TRANSFERS[transfer_id]['transferred'] = file_size
            ACTIVE_TRANSFERS[transfer_id]['percent'] = 100
            ACTIVE_TRANSFERS[transfer_id]['formatted_size'] = format_size(file_size)
            ACTIVE_TRANSFERS[transfer_id]['status'] = 'completed'
            
            saved_item = {
                'name': filename,
                'size': file_size,
                'formatted_size': format_size(file_size),
                'timestamp': time.time(),
                'date_str': datetime.datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                'icon': get_file_icon_name(filename),
                'status': 'Reçu'
            }
            saved_files.append(saved_item)
            TRANSFER_HISTORY['received'].insert(0, saved_item)
            
            def clean_active(tid):
                time.sleep(5)
                if tid in ACTIVE_TRANSFERS:
                    del ACTIVE_TRANSFERS[tid]
            threading.Thread(target=clean_active, args=(transfer_id,), daemon=True).start()
            
    if is_xhr:
        return jsonify({
            'status': 'success',
            'files': saved_files,
            'count': len(saved_files),
            'total_size': total_size,
            'message': f"{len(saved_files)} fichier(s) téléversé(s) avec succès"
        }), 200
        
    return redirect(url_for('transfers_page'))

if __name__ == '__main__':
    configure_console(make_full_green_text=True, clear_screen=False, title="PyDrop - Serveur")
    all_ips = get_all_local_ips()
    primary_ip = get_local_ip()
    port = int(os.environ.get('PORT', 5000))
    
    hotspot_ip = next((ip for ip in all_ips if ip.startswith('192.168.137.') or ip.startswith('192.168.43.')), None)
    server_target_ip = hotspot_ip if hotspot_ip else primary_ip
    server_qr_url = f"http://{server_target_ip}:{port}/qr"
    
    print("\n=======================================================")
    print("   🚀 PyDrop Serveur Démarré avec Succès !")
    print("=======================================================")
    print(f"  🌐 Adresse Serveur Réseau :  http://{server_target_ip}:{port}")
    print(f"  📷 Page QR Code (Ce PC)   :  {server_qr_url}")
    if hotspot_ip:
        print(f"  📡 Point d'accès (PC)     :  http://{hotspot_ip}:{port}")
    print(f"  📱 Accès Application Mobile:  http://{server_target_ip}:{port}/")
    print(f"  📱 Scanner Web Mobile     :  http://{server_target_ip}:{port}/mobile")
    print("=======================================================")
    print("  ⏳ Statut : En attente de connexion d'un autre appareil...")
    print("=======================================================\n")
    print("💡 Astuce : Sur votre téléphone ou votre application mobile,")
    print(f"   entrez l'adresse : http://{server_target_ip}:{port}")
    print("   ou scannez le QR code affiché à l'écran.\n")
    
    # Ouvrir directement la page QR avec l'adresse IP réseau du serveur
    def open_browser():
        time.sleep(1.0)
        print(f"[PyDrop] Lancement du navigateur sur le serveur : {server_qr_url}")
        webbrowser.open(server_qr_url)
        
    threading.Thread(target=open_browser, daemon=True).start()
    
    try:
        app.run(host=HOST, port=port, debug=False)
    except Exception as err:
        print(f"\n[ERREUR SERVEUR] {err}")
        if sys.platform == 'win32':
            input("\nAppuyez sur Entrée pour quitter...")