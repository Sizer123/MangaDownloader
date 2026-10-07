#!/usr/bin/env python3
"""
manga_share.py — Envoie tes CBR/CBZ sur ton téléphone via le réseau local (Wi-Fi), en scannant un QR code.

Fonctionnement :
  1. Lance un petit serveur local et ouvre sur le PC une page affichant un QR code.
  2. Tu scannes le QR code avec ton téléphone (même Wi-Fi que le PC).
  3. Le téléphone ouvre une page avec ta bibliothèque (séries -> chapitres) :
     un appui télécharge le fichier directement sur le téléphone.

Bibliothèque : par défaut, l'archive Manga_Manhwa_Archives des disques branchés
(créée par manga_archiver.py). À défaut, ou avec --root, les dossiers choisis.
Le lien contient un jeton secret aléatoire, valable seulement pour cette session.
Seuls les fichiers .cbr/.cbz trouvés au scan sont servis (jamais de chemin fourni par le client).

Usage :
    python scripts/utils/manga_share.py                       # archive des disques branchés
    python scripts/utils/manga_share.py --root "D:/Manga"     # dossier(s) précis (répétable)
    python scripts/utils/manga_share.py --port 8766 --no-browser
    python scripts/utils/manga_share.py --http                # téléphone sans HTTPS

Le téléphone passe par HTTPS (port + 1) avec un certificat auto-signé créé par openssl :
au premier accès, accepter l'avertissement « connexion non privée ».

Aucune dépendance Python externe (le QR code est dessiné par une petite lib JS chargée
depuis cdnjs ; sans Internet, l'adresse s'affiche quand même en texte et dans le terminal).
"""

import argparse
import json
import re
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
import webbrowser
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from manga_archiver import (ARCHIVE_NAME, PROJECT_ROOT, STATE_DIR, fmt_size, list_drives, log,
                            parse_chapter, series_dir_of, walk_comics)

DEFAULT_PORT = 8766  # page PC (http, local) ; le téléphone utilise DEFAULT_PORT + 1 (https)
TLS_DIR = STATE_DIR / 'share_tls'
CHUNK = 1024 * 256
SCAN_TTL = 30  # secondes avant rescan automatique de la bibliothèque


def local_ip() -> str:
    """IP du PC sur le réseau local (aucun paquet n'est réellement envoyé)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        return s.getsockname()[0]
    except OSError:
        return '127.0.0.1'
    finally:
        s.close()


def ensure_cert(ip: str):
    """Certificat auto-signé pour l'IP du PC (créé avec openssl, réutilisé tant que l'IP ne change pas)."""
    cert, key, ip_file = TLS_DIR / 'cert.pem', TLS_DIR / 'key.pem', TLS_DIR / 'ip.txt'
    if cert.exists() and key.exists() and ip_file.exists() and ip_file.read_text().strip() == ip:
        return cert, key
    exe = shutil.which('openssl')
    if not exe:
        return None
    TLS_DIR.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([exe, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-sha256', '-days', '3650',
                        '-keyout', str(key), '-out', str(cert), '-subj', '/CN=Manga Share',
                        '-addext', f'subjectAltName=IP:{ip}'], capture_output=True)
    if r.returncode != 0:
        log(f'openssl a échoué : {r.stderr.decode(errors="replace").strip()}')
        return None
    ip_file.write_text(ip)
    return cert, key


class TLSServer(ThreadingHTTPServer):
    """Serveur HTTPS : la poignée de main TLS se fait dans le thread de la requête, pas dans accept()."""
    daemon_threads = True

    def __init__(self, addr, handler, ctx):
        super().__init__(addr, handler)
        self.ctx = ctx

    def get_request(self):
        sock, addr = self.socket.accept()
        return self.ctx.wrap_socket(sock, server_side=True, do_handshake_on_connect=False), addr

    def handle_error(self, request, client_address):
        pass  # certificat refusé par le téléphone, connexion coupée…


class Library:
    def __init__(self, roots: list):
        self.roots = roots
        self.lock = threading.Lock()
        self.scanned = 0.0
        self.series = []
        self.files = {}  # id -> Path
        self.groups = {}  # id de série -> (titre, [Path])

    def effective_roots(self) -> list:
        if self.roots:
            return [Path(r) for r in self.roots]
        found = [Path(d['root']) / ARCHIVE_NAME for d in list_drives()
                 if d['has_archive']]
        return found or [PROJECT_ROOT]

    def scan(self) -> None:
        groups, files, n = {}, {}, 0
        for root in self.effective_roots():
            if not root.is_dir():
                continue
            for f in walk_comics(root, set()):
                try:
                    size = f.stat().st_size
                except OSError:
                    continue
                if size == 0:
                    continue
                title = series_dir_of(f, root).name or f.stem
                fid = f'{n:x}'
                n += 1
                files[fid] = f
                num = parse_chapter(f.stem)
                groups.setdefault(title, []).append({
                    'id': fid, 'name': f.name, 'size': size,
                    'sort': float(num) if num else 1e9,
                })
        series, sgroups = [], {}
        for title, items in groups.items():
            items.sort(key=lambda i: (i['sort'], i['name'].lower()))
            sid = f's{len(sgroups):x}'
            sgroups[sid] = (title, [files[i['id']] for i in items])
            series.append({'id': sid, 'title': title, 'count': len(items),
                           'size': sum(i['size'] for i in items),
                           'items': [{k: i[k] for k in ('id', 'name', 'size')} for i in items]})
        series.sort(key=lambda s: s['title'].lower())
        with self.lock:
            self.series, self.files, self.groups, self.scanned = series, files, sgroups, time.time()
        log(f'Bibliothèque : {len(series)} séries, {len(files)} fichiers')

    def get(self) -> list:
        if time.time() - self.scanned > SCAN_TTL:
            self.scan()
        return self.series

    def group(self, sid: str):
        self.get()
        with self.lock:
            return self.groups.get(sid)

    def path(self, fid: str):
        self.get()
        with self.lock:
            return self.files.get(fid)


def make_handler(lib: Library, token: str, phone_url: str):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *args):
            pass

        def _send(self, code, body, ctype='application/json; charset=utf-8'):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def _is_pc(self) -> bool:
            return self.client_address[0] in ('127.0.0.1', '::1')

        def _token_ok(self, q) -> bool:
            return secrets.compare_digest(q.get('t', [''])[0], token)

        def do_GET(self):
            u = urlparse(self.path)
            q = parse_qs(u.query)
            p = u.path
            if p == '/' and self._is_pc():
                page = PC_PAGE.replace('__URL__', json.dumps(phone_url))
                return self._send(200, page.encode(), 'text/html; charset=utf-8')
            if p == '/api/pc-state' and self._is_pc():
                lib.get()
                return self._send(200, {'roots': [str(r) for r in lib.effective_roots()],
                                        'series': len(lib.series), 'files': len(lib.files)})
            if not self._token_ok(q):
                return self._send(403, {'error': 'lien invalide — rescanne le QR code'})
            if p == '/m':
                return self._send(200, PHONE_PAGE.encode(), 'text/html; charset=utf-8')
            if p == '/api/library':
                return self._send(200, lib.get())
            if p.startswith('/file/'):
                return self._file(p[6:])
            if p.startswith('/zip/'):
                return self._zip(p[5:])
            self._send(404, {'error': 'introuvable'})

        def do_POST(self):
            if self.path == '/api/rescan' and self._is_pc():
                lib.scan()
                return self._send(200, {'ok': True})
            self._send(404, {'error': 'introuvable'})

        def _file(self, fid):
            path = lib.path(fid)
            if not path or not path.is_file():
                return self._send(404, {'error': 'fichier introuvable'})
            size = path.stat().st_size
            start, end, code = 0, size - 1, 200
            m = re.match(r'bytes=(\d*)-(\d*)$', self.headers.get('Range') or '')
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else size - 1
                else:
                    start = max(0, size - int(m.group(2)))
                end = min(end, size - 1)
                if start > end:
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{size}')
                    self.send_header('Content-Length', '0')
                    self.end_headers()
                    return
                code = 206
            length = end - start + 1
            self.send_response(code)
            self.send_header('Content-Type', 'application/octet-stream')
            self.send_header('Content-Length', str(length))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Content-Disposition', f"attachment; filename*=UTF-8''{quote(path.name)}")
            if code == 206:
                self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.end_headers()
            if start == 0:
                log(f'Envoi vers {self.client_address[0]} : {path.name} ({fmt_size(size)})')
            try:
                with open(path, 'rb') as f:
                    f.seek(start)
                    left = length
                    while left > 0:
                        chunk = f.read(min(CHUNK, left))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass  # le téléphone a annulé / s'est endormi

        def _zip(self, sid):
            """Toute une série en un seul ZIP (sans compression), envoyé au fil de l'eau."""
            g = lib.group(sid)
            if not g:
                return self._send(404, {'error': 'série introuvable'})
            title, paths = g
            folder = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', title).strip(' .') or 'Manga'
            name = f'{title}.zip'
            self.send_response(200)
            self.send_header('Content-Type', 'application/zip')
            self.send_header('Content-Disposition', f"attachment; filename*=UTF-8''{quote(name)}")
            self.send_header('Connection', 'close')
            self.end_headers()
            self.close_connection = True
            log(f'Envoi ZIP vers {self.client_address[0]} : {name} ({len(paths)} fichiers)')
            try:
                with zipfile.ZipFile(self.wfile, 'w', zipfile.ZIP_STORED) as zf:
                    for f in paths:
                        if f.is_file():
                            zf.write(f, f'{folder}/{f.name}')  # dossier de la série dans le ZIP
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    return Handler


def main():
    ap = argparse.ArgumentParser(description='Envoie tes CBR sur ton téléphone via un QR code (Wi-Fi).')
    ap.add_argument('--port', type=int, default=DEFAULT_PORT)
    ap.add_argument('--root', action='append', default=[],
                    help='dossier à partager (répétable) ; défaut : archive des disques branchés')
    ap.add_argument('--no-browser', action='store_true')
    ap.add_argument('--http', action='store_true', help='téléphone en http simple (sans certificat)')
    args = ap.parse_args()

    ip, phone_port = local_ip(), args.port + 1
    tls = None if args.http else ensure_cert(ip)
    scheme = 'https' if tls else 'http'
    token = secrets.token_urlsafe(12)
    phone_url = f'{scheme}://{ip}:{phone_port}/m?t={token}'
    lib = Library(args.root)
    handler = make_handler(lib, token, phone_url)

    pc_server = ThreadingHTTPServer(('127.0.0.1', args.port), handler)
    pc_server.daemon_threads = True
    if tls:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(*map(str, tls))
        phone_server = TLSServer(('0.0.0.0', phone_port), handler, ctx)
    else:
        phone_server = ThreadingHTTPServer(('0.0.0.0', phone_port), handler)
        phone_server.daemon_threads = True
    threading.Thread(target=phone_server.serve_forever, daemon=True).start()
    threading.Thread(target=lib.scan, daemon=True).start()

    print(f'\nManga Share prêt.\n  PC        : http://127.0.0.1:{args.port}/   (QR code)\n  Téléphone : {phone_url}\n'
          '  (téléphone et PC sur le même Wi-Fi ; autorise Python dans le pare-feu si demandé)', flush=True)
    if tls:
        print('  Certificat auto-signé : au 1er accès, le téléphone affiche « connexion non privée »\n'
              '  → Paramètres avancés → Continuer.\n', flush=True)
    elif not args.http:
        print('  openssl introuvable : téléphone en http simple.\n', flush=True)
    if not args.no_browser:
        threading.Timer(0.5, webbrowser.open, args=(f'http://127.0.0.1:{args.port}/',)).start()
    try:
        pc_server.serve_forever()
    except KeyboardInterrupt:
        print('\nArrêt.')


# --------------------------------------------------------------------------- #
# Pages web
# --------------------------------------------------------------------------- #

PC_PAGE = r"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Manga Share</title>
<style>
:root{--bg:#0d0f14;--card:#181d28;--line:#2a3142;--txt:#e8ebf2;--mut:#8b93a7;--acc:#ff5d8f}
body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.5 system-ui,sans-serif;min-height:100vh;
  display:grid;place-items:center;padding:24px}
.box{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:32px;max-width:440px;text-align:center}
h1{margin:0 0 6px;font-size:22px}.mut{color:var(--mut);font-size:13px}
#qr{background:#fff;padding:14px;border-radius:12px;display:inline-block;margin:22px 0 12px;min-height:200px;min-width:200px}
code{display:block;word-break:break-all;background:var(--bg);border:1px solid var(--line);border-radius:10px;
  padding:10px;font-size:12.5px;margin:10px 0}
button{font:inherit;font-weight:600;color:var(--txt);background:#1f2533;border:1px solid var(--line);
  border-radius:10px;padding:9px 16px;cursor:pointer}
</style></head><body><div class="box">
<h1>📱 Manga Share</h1>
<div class="mut">Scanne avec ton téléphone (même Wi-Fi que ce PC)</div>
<div id="qr"></div>
<code id="url"></code>
<div class="mut" id="info">Analyse de la bibliothèque…</div>
<p class="mut" id="tlsHint" hidden>1er accès : le téléphone affiche « connexion non privée » (certificat créé par ce PC) → <b>Paramètres avancés → Continuer</b>.</p>
<p><button id="re">Rescanner la bibliothèque</button></p>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>
<script>
const URL_ = __URL__;
document.getElementById('url').textContent = URL_;
document.getElementById('tlsHint').hidden = !URL_.startsWith('https');
if (window.QRCode) new QRCode(document.getElementById('qr'), {text: URL_, width: 200, height: 200});
else document.getElementById('qr').textContent = 'QR indisponible hors-ligne : saisis l\'adresse ci-dessous sur le téléphone';
async function info(){
  const s = await (await fetch('/api/pc-state')).json();
  document.getElementById('info').textContent = s.series + ' séries · ' + s.files + ' fichiers — ' + s.roots.join(' | ');
}
document.getElementById('re').onclick = async () => { await fetch('/api/rescan',{method:'POST'}); info(); };
info();
</script></body></html>"""

PHONE_PAGE = r"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Manga Share</title>
<style>
:root{--bg:#0d0f14;--card:#181d28;--line:#2a3142;--txt:#e8ebf2;--mut:#8b93a7;--acc:#ff5d8f}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font:16px/1.4 system-ui,-apple-system,sans-serif;
  padding:0 14px calc(24px + env(safe-area-inset-bottom))}
header{position:sticky;top:0;background:#0d0f14ee;backdrop-filter:blur(8px);padding:14px 0 10px;z-index:5}
h1{margin:0 0 10px;font-size:20px}
input{width:100%;font:inherit;color:var(--txt);background:var(--card);border:1px solid var(--line);
  border-radius:12px;padding:12px 14px;outline:none}
.s{background:var(--card);border:1px solid var(--line);border-radius:14px;margin:10px 0;overflow:hidden}
.sh{display:flex;align-items:center;gap:10px;padding:14px;cursor:pointer}
.sh b{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.mut{color:var(--mut);font-size:13px}
.ch{border-top:1px solid var(--line);padding:6px 14px 10px}
.row{display:flex;align-items:center;gap:10px;padding:11px 0;border-bottom:1px solid #ffffff0d}
.row span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:14px}
a.dl,button{font:inherit;font-weight:600;color:#fff;text-decoration:none;background:linear-gradient(135deg,var(--acc),#e04bb0);
  border:0;border-radius:10px;padding:9px 14px;white-space:nowrap}
a.all{display:block;text-align:center;margin:10px 0 2px}
.empty{color:var(--mut);text-align:center;padding:40px 0}
</style></head><body>
<header><h1>📚 Ma bibliothèque</h1><input id="q" type="search" placeholder="Rechercher une série…"></header>
<div id="list"><div class="empty">Chargement…</div></div>
<script>
const T = new URLSearchParams(location.search).get('t');
const fmt = n => n < 1048576 ? (n/1024).toFixed(0)+' Ko' : n < 1073741824 ? (n/1048576).toFixed(1)+' Mo' : (n/1073741824).toFixed(2)+' Go';
const esc = s => s.replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let lib = [], open_ = new Set();
const url = id => '/file/' + id + '?t=' + encodeURIComponent(T);
function render(){
  const f = document.getElementById('q').value.trim().toLowerCase();
  const rows = lib.filter(s => !f || s.title.toLowerCase().includes(f));
  document.getElementById('list').innerHTML = rows.length ? rows.map(s => {
    const o = open_.has(s.title) || (f && rows.length === 1);
    return `<div class="s"><div class="sh" data-t="${esc(s.title)}"><b>${esc(s.title)}</b>
      <span class="mut">${s.count} ch. · ${fmt(s.size)}</span></div>` + (o ? `<div class="ch">
      <a class="dl all" href="/zip/${s.id}?t=${encodeURIComponent(T)}" download>⬇ Tout télécharger — dossier ZIP (${s.count} fichiers, ${fmt(s.size)})</a>` +
      s.items.map(i => `<div class="row"><span>${esc(i.name)}<br><small class="mut">${fmt(i.size)}</small></span>
        <a class="dl" href="${url(i.id)}" download>⬇</a></div>`).join('') + '</div>' : '') + '</div>';
  }).join('') : '<div class="empty">Aucune série</div>';
}
document.getElementById('list').onclick = e => {
  const h = e.target.closest('.sh');
  if (h) { const t = h.dataset.t; open_.has(t) ? open_.delete(t) : open_.add(t); render(); }
};
document.getElementById('q').oninput = render;
fetch('/api/library?t=' + encodeURIComponent(T)).then(r => r.json()).then(d => { lib = d; render(); })
  .catch(() => document.getElementById('list').innerHTML = '<div class="empty">Erreur — rescanne le QR code</div>');
</script></body></html>"""


if __name__ == '__main__':
    sys.exit(main())
