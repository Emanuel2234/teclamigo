"""
Teclamigo - app local
------------------------
Abre la app en el navegador y, cuando cargas un audio:
  1. separa el piano/teclado con Demucs (modelo htdemucs_6s de Meta), y
  2. detecta las notas con un modelo especializado en piano
     (High-resolution Piano Transcription de ByteDance).

Se inicia con:  python teclamigo.py   (Ctrl+C o cerrar la terminal para apagarla).
Todo corre en tu PC; nada se sube a internet.
"""
import hashlib
import http.server
import importlib
import importlib.util
import json
import os
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
PAQUETES = ["demucs", "piano_transcription_inference", "audioread"]
CKPT_URL = "https://zenodo.org/record/4034264/files/CRNN_note_F1%3D0.9677_pedal_F1%3D0.9186.pth?download=1"
CKPT = Path.home() / "piano_transcription_inference_data" / "note_F1=0.9677_pedal_F1=0.9186.pth"
ENV = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
PUERTO_INICIAL = 8765

TRABAJOS = {}                                   # id -> estado de cada separación
INSTALACION = {"estado": "no", "mensaje": ""}   # no / instalando / listo / error
CANDADO = threading.Lock()


# ---------- utilidades ----------
def motor_instalado() -> bool:
    importlib.invalidate_caches()
    return all(importlib.util.find_spec(p) is not None for p in PAQUETES)


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
    print("Instalando el motor de notas (solo la primera vez)...")
    try:
        p = subprocess.Popen([sys.executable, "-m", "pip", "install", "-U", *PAQUETES],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace")
        for linea in p.stdout:
            linea = linea.strip()
            if linea:
                print("  " + linea)
                INSTALACION["mensaje"] = linea[-120:]
        p.wait()
        if p.returncode == 0 and motor_instalado():
            INSTALACION.update(estado="listo", mensaje="Instalado")
        else:
            INSTALACION.update(estado="error", mensaje=INSTALACION["mensaje"] or "pip falló")
    except Exception as e:
        INSTALACION.update(estado="error", mensaje=str(e))


# ---------- detección de notas (se corre en un proceso aparte) ----------
def descargar_modelo():
    """Descarga el modelo de piano (~170 MB) la primera vez."""
    if CKPT.exists() and CKPT.stat().st_size > 1.6e8:
        return
    CKPT.parent.mkdir(parents=True, exist_ok=True)
    tmp = CKPT.with_suffix(".descargando")
    with urllib.request.urlopen(CKPT_URL) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        hecho, ultimo = 0, -1
        while True:
            trozo = r.read(1 << 20)
            if not trozo:
                break
            f.write(trozo)
            hecho += len(trozo)
            if total:
                pct = int(hecho * 100 / total)
                if pct != ultimo:
                    print(f"DESCARGA {pct}", flush=True)
                    ultimo = pct
    tmp.replace(CKPT)


def transcribir_cli(entrada: str, salida: str):
    """python teclamigo.py --transcribir audio salida.json"""
    import julius
    import numpy as np
    import sphn
    import torch
    from piano_transcription_inference import PianoTranscription, sample_rate

    descargar_modelo()
    cargar = torch.load          # el modelo es antiguo: torch nuevo exige weights_only=False
    torch.load = lambda *a, **k: cargar(*a, **{**k, "weights_only": False})

    datos, sr = sphn.read(entrada)
    mono = torch.from_numpy(np.asarray(datos, dtype=np.float32).mean(axis=0))
    audio = julius.resample_frac(mono, int(sr), sample_rate).numpy()

    disp = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    modelo = PianoTranscription(device=disp, checkpoint_path=str(CKPT))
    res = modelo.transcribe(audio, None)
    import math
    notas = []
    for e in res["est_note_events"]:
        ini, fin = float(e["onset_time"]), float(e["offset_time"])
        if not (math.isfinite(ini) and math.isfinite(fin)) or fin <= ini:
            continue                  # a veces el modelo deja una nota con tiempo inválido
        notas.append({"midi": int(e["midi_note"]), "start": round(ini, 4),
                      "dur": round(fin - ini, 4), "vel": int(e["velocity"])})
    Path(salida).write_text(json.dumps(notas, allow_nan=False), encoding="utf-8")


# ---------- trabajo completo: separar + detectar ----------
def correr(cmd, al_leer):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=ENV,
                         text=True, encoding="utf-8", errors="replace")
    ultimas = []
    for linea in p.stdout:          # tqdm usa \r: el modo texto lo separa en líneas
        linea = linea.strip()
        if linea:
            ultimas = (ultimas + [linea])[-8:]
            al_leer(linea)
    p.wait()
    if p.returncode != 0:
        raise RuntimeError(" / ".join(ultimas[-3:]) or "falló el proceso")


def procesar(tid: str, datos: bytes, nombre: str, separar_piano: bool):
    t = TRABAJOS[tid]
    try:
        CACHE.mkdir(exist_ok=True)
        base = f"{nombre_limpio(nombre)} [{hashlib.sha1(datos).hexdigest()[:10]}]"
        cache_json = CACHE / f"{base}{' piano' if separar_piano else ''}.json"
        if cache_json.exists():
            t.update(estado="listo", progreso=100, mensaje="Ya estaba procesada", resultado=str(cache_json))
            return

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            entrada = tmp / ("cancion" + tipo_real(datos))
            entrada.write_bytes(datos)
            audio = entrada
            nivel = None
            inicio_det = 0

            if separar_piano:
                print(f"Separando el piano de: {nombre}")
                t["etapa"] = "Separando el piano"

                def leer_sep(l):
                    m = re.search(r"(\d{1,3})%\|", l)
                    if m:
                        t.update(progreso=int(int(m.group(1)) * 0.5), mensaje="")
                    elif "download" in l.lower():
                        t["mensaje"] = "Descargando el separador (solo la primera vez)..."
                correr([sys.executable, "-m", "demucs", "-n", MODELO, "--two-stems", "piano",
                        "--mp3", "--mp3-bitrate", "256", "-o", str(tmp / "salida"), str(entrada)], leer_sep)
                piano = next((tmp / "salida").rglob("piano.mp3"), None)
                if piano is None:
                    raise RuntimeError("No se generó la pista de piano")
                nivel = porcentaje_piano(piano, entrada)
                audio = CACHE / f"{base} - piano.mp3"
                shutil.move(str(piano), audio)
                inicio_det = 50

            print(f"Detectando notas de: {nombre}")
            t.update(etapa="Detectando las notas", progreso=inicio_det, mensaje="")
            salida = tmp / "notas.json"

            def leer_det(l):
                m = re.match(r"DESCARGA (\d+)", l)
                if m:
                    t["mensaje"] = f"Descargando el modelo de piano {m.group(1)}% (solo la primera vez)"
                    return
                m = re.match(r"Segment (\d+) / (\d+)", l)
                if m:
                    hecho, total = int(m.group(1)), max(1, int(m.group(2)))
                    t.update(progreso=int(inicio_det + (100 - inicio_det) * hecho / total), mensaje="")
            correr([sys.executable, str(Path(__file__).resolve()), "--transcribir", str(audio), str(salida)], leer_det)

            notas = json.loads(salida.read_text(encoding="utf-8"))
            cache_json.write_text(json.dumps({"notas": notas, "nivel": nivel}), encoding="utf-8")

        print(f"  Listo: {len(notas)} notas")
        t.update(estado="listo", progreso=100, mensaje="", resultado=str(cache_json))
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
            return self.json({"app": "teclamigo", "motor": motor_instalado(), "instalacion": INSTALACION})
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
            self.send_header("Content-Type", "application/json")
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
                if INSTALACION["estado"] != "instalando" and not motor_instalado():
                    threading.Thread(target=instalar, daemon=True).start()
            return self.json({"ok": True})
        if url.path == "/api/procesar":
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
            TRABAJOS[tid] = {"estado": "procesando", "etapa": "Preparando", "progreso": 0, "mensaje": ""}
            nombre = q.get("nombre", ["cancion"])[0]
            separar_piano = q.get("separar", ["1"])[0] == "1"
            threading.Thread(target=procesar, args=(tid, datos, nombre, separar_piano), daemon=True).start()
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
    if len(sys.argv) == 4 and sys.argv[1] == "--transcribir":
        return transcribir_cli(sys.argv[2], sys.argv[3])
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
