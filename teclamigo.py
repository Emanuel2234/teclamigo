"""
Teclamigo - app local
------------------------
Abre la app en el navegador y, cuando cargas un audio, separa el piano/teclado
con Demucs (modelo htdemucs_6s de Meta) antes de convertirlo a notas.

Se inicia con:  python teclamigo.py   (Ctrl+C o cerrar la terminal para apagarla).
Todo corre en tu PC; nada se sube a internet.
"""
import hashlib
import http.server
import importlib
import importlib.util
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid
import webbrowser
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = Path(__file__).resolve().parent
PAGINA = "teclamigo.html"
CACHE = BASE / "Piano separado"
MODELO = "htdemucs_6s"
PUERTO_INICIAL = 8765

TRABAJOS = {}                                   # id -> estado de cada separación
INSTALACION = {"estado": "no", "mensaje": ""}   # no / instalando / listo / error
CANDADO = threading.Lock()


# ---------- utilidades ----------
def demucs_instalado() -> bool:
    importlib.invalidate_caches()
    return importlib.util.find_spec("demucs") is not None


def tipo_real(datos: bytes):
    """Tipo de audio según sus primeros bytes (no según la extensión)."""
    cab = datos[:12]
    for firma, ext in [(b"RIFF", ".wav"), (b"ID3", ".mp3"), (b"fLaC", ".flac"), (b"OggS", ".ogg")]:
        if cab.startswith(firma):
            return ext
    if len(cab) > 1 and cab[0] == 0xFF and (cab[1] & 0xE0) == 0xE0:
        return ".mp3"
    if cab[4:8] == b"ftyp":
        return ".m4a"
    return ".mp3"


def nombre_limpio(nombre: str) -> str:
    return re.sub(r'[<>:"/\\|?*]+', "_", nombre).strip()[:80] or "cancion"


def porcentaje_piano(piano: Path, original: Path):
    try:
        import numpy as np
        import sphn
        a, _ = sphn.read(str(piano))
        b, _ = sphn.read(str(original))
        return round(100 * float(np.mean(np.square(a))) / (float(np.mean(np.square(b))) + 1e-12), 1)
    except Exception:
        return None


# ---------- instalación de Demucs (solo la primera vez) ----------
def instalar():
    INSTALACION.update(estado="instalando", mensaje="Iniciando...")
    print("Instalando Demucs (solo la primera vez)...")
    try:
        p = subprocess.Popen([sys.executable, "-m", "pip", "install", "-U", "demucs"],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace")
        for linea in p.stdout:
            linea = linea.strip()
            if linea:
                print("  " + linea)
                INSTALACION["mensaje"] = linea[-120:]
        p.wait()
        if p.returncode == 0 and demucs_instalado():
            INSTALACION.update(estado="listo", mensaje="Instalado")
        else:
            INSTALACION.update(estado="error", mensaje=INSTALACION["mensaje"] or "pip falló")
    except Exception as e:
        INSTALACION.update(estado="error", mensaje=str(e))


# ---------- separación del piano ----------
def separar(tid: str, datos: bytes, nombre: str):
    t = TRABAJOS[tid]
    try:
        CACHE.mkdir(exist_ok=True)
        huella = hashlib.sha1(datos).hexdigest()[:10]
        destino = CACHE / f"{nombre_limpio(nombre)} - piano [{huella}].mp3"
        if destino.exists():
            t.update(estado="listo", progreso=100, mensaje="Ya estaba separada", resultado=str(destino))
            return

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            entrada = tmp / ("cancion" + tipo_real(datos))
            entrada.write_bytes(datos)
            cmd = [sys.executable, "-m", "demucs", "-n", MODELO, "--two-stems", "piano",
                   "--mp3", "--mp3-bitrate", "256", "-o", str(tmp / "salida"), str(entrada)]
            print(f"Separando el piano de: {nombre}")
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, encoding="utf-8", errors="replace")
            ultimas = []
            for linea in p.stdout:          # tqdm usa \r: el modo texto lo separa en líneas
                linea = linea.strip()
                if not linea:
                    continue
                ultimas = (ultimas + [linea])[-8:]
                m = re.search(r"(\d{1,3})%\|", linea)
                if m:
                    t["progreso"] = int(m.group(1))
                    t["mensaje"] = ""
                elif "Downloading" in linea or "download" in linea.lower():
                    t["mensaje"] = "Descargando el modelo (solo la primera vez)..."
            p.wait()
            if p.returncode != 0:
                raise RuntimeError(" / ".join(ultimas[-3:]) or "Demucs falló")

            piano = next((tmp / "salida").rglob("piano.mp3"), None)
            if piano is None:
                raise RuntimeError("No se generó la pista de piano")
            t["nivel"] = porcentaje_piano(piano, entrada)
            shutil.move(str(piano), destino)

        print(f"  Listo: {destino.name}")
        t.update(estado="listo", progreso=100, mensaje="", resultado=str(destino))
    except Exception as e:
        print(f"  Error: {e}")
        t.update(estado="error", mensaje=str(e))


# ---------- servidor web ----------
class Manejador(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(BASE), **kw)

    def log_message(self, *a):
        pass

    def host_valido(self) -> bool:
        """Solo acepta pedidos de esta misma PC."""
        host = (self.headers.get("Host") or "").split(":")[0]
        origen = self.headers.get("Origin")
        if host not in ("127.0.0.1", "localhost"):
            return False
        if origen and urllib.parse.urlparse(origen).hostname not in ("127.0.0.1", "localhost"):
            return False
        return True

    def json(self, datos, codigo=200):
        cuerpo = json.dumps(datos).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        if not self.host_valido():
            return self.send_error(403)
        url = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(url.query)
        if url.path == "/":
            self.send_response(302)
            self.send_header("Location", "/" + PAGINA)
            self.end_headers()
            return
        if url.path == "/api/estado":
            return self.json({"app": "teclamigo", "demucs": demucs_instalado(), "instalacion": INSTALACION})
        if url.path == "/api/trabajo":
            t = TRABAJOS.get(q.get("id", [""])[0])
            if not t:
                return self.json({"estado": "error", "mensaje": "Trabajo no encontrado"}, 404)
            return self.json({k: v for k, v in t.items() if k != "resultado"})
        if url.path == "/api/resultado":
            t = TRABAJOS.get(q.get("id", [""])[0])
            if not t or t.get("estado") != "listo":
                return self.send_error(404)
            datos = Path(t["resultado"]).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "audio/mpeg")
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)
            return
        if url.path.startswith("/api/"):
            return self.send_error(404)
        return super().do_GET()

    def do_POST(self):
        if not self.host_valido():
            return self.send_error(403)
        url = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(url.query)
        if url.path == "/api/instalar":
            with CANDADO:
                if INSTALACION["estado"] != "instalando" and not demucs_instalado():
                    threading.Thread(target=instalar, daemon=True).start()
            return self.json({"ok": True})
        if url.path == "/api/separar":
            largo = int(self.headers.get("Content-Length", "0"))
            if largo <= 0 or largo > 300 * 1024 * 1024:
                return self.json({"error": "Archivo vacío o demasiado grande"}, 400)
            datos = b""
            while len(datos) < largo:
                trozo = self.rfile.read(min(1 << 20, largo - len(datos)))
                if not trozo:
                    break
                datos += trozo
            tid = uuid.uuid4().hex
            TRABAJOS[tid] = {"estado": "separando", "progreso": 0, "mensaje": "Preparando...", "nivel": None}
            nombre = q.get("nombre", ["cancion"])[0]
            threading.Thread(target=separar, args=(tid, datos, nombre), daemon=True).start()
            return self.json({"id": tid})
        return self.send_error(404)


def ya_esta_abierta(puerto: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{puerto}/api/estado", timeout=1) as r:
            return json.load(r).get("app") == "teclamigo"
    except Exception:
        return False


def puerto_libre(puerto: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", puerto)) != 0


def main():
    if not (BASE / PAGINA).exists():
        print(f"No encuentro {PAGINA} en esta carpeta.")
        input("Enter para salir...")
        return

    puerto = PUERTO_INICIAL
    while not puerto_libre(puerto):
        if ya_esta_abierta(puerto):
            print("Teclamigo ya estaba abierta; la abro en el navegador.")
            webbrowser.open(f"http://127.0.0.1:{puerto}/")
            return
        puerto += 1

    servidor = http.server.ThreadingHTTPServer(("127.0.0.1", puerto), Manejador)
    url = f"http://127.0.0.1:{puerto}/"
    print("=" * 50)
    print("  Teclamigo está funcionando")
    print(f"  {url}")
    print("  No cierres esta ventana mientras usas la app.")
    print("=" * 50)
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
