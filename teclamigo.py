"""
Teclamigo - app local
------------------------
Abre la app en el navegador y, cuando cargas un audio:
  1. separa el piano/teclado con BS-RoFormer SW (el separador de piano con mejor puntaje
     público: 7.83 dB contra 2.23 dB de Demucs 6 pistas, según la tabla de MVSEP);
     si no está disponible, usa Demucs (htdemucs_6s de Meta), y
  2. detecta las notas con Transkun 2, un modelo especializado en piano
     (Yan & Duan, 2024; el modelo viene incluido en el paquete, sin descargas aparte).

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
PAQUETES = ["bs_roformer", "demucs", "transkun"]
PAQUETES_PIP = ["bs-roformer-infer", "demucs", "transkun"]
MOTOR = "rf-tk2s"          # va en el nombre de la caché: si cambia el motor, se vuelve a procesar
SHIFTS = 2               # separación en máxima calidad: Demucs promedia 2 pasadas con pequeños corrimientos
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
        p = subprocess.Popen([sys.executable, "-m", "pip", "install", "-U", *PAQUETES_PIP],
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
def separar_cli(entrada: str, salida: str):
    """python teclamigo.py --separar audio piano.wav   (BS-RoFormer SW, 6 pistas)"""
    import math

    import numpy as np
    import soxr
    import sphn
    import torch
    import yaml
    from bs_roformer.download import ensure_model_assets
    from bs_roformer.inference import SafeLoaderWithTuple
    from bs_roformer.model_registry import DEFAULT_MODEL
    from bs_roformer.utils import demix_track, get_model_from_config
    from ml_collections import ConfigDict

    print("PREPARANDO_SEPARADOR", flush=True)
    ckpt, cfg = ensure_model_assets(DEFAULT_MODEL)     # ~700 MB la primera vez (verificado con SHA-256)
    with open(cfg, encoding="utf-8") as f:
        config = ConfigDict(yaml.load(f, Loader=SafeLoaderWithTuple))
    modelo = get_model_from_config("bs_roformer", config)
    modelo.load_state_dict(torch.load(ckpt, map_location="cpu"))
    disp = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    modelo = modelo.to(disp).eval()
    print("MODELO_LISTO", flush=True)

    datos, sr = sphn.read(entrada)
    x = np.asarray(datos, dtype=np.float32)
    if x.shape[0] == 1:
        x = np.repeat(x, 2, axis=0)
    x = x[:2]
    SR = 44100                                          # el modelo fue entrenado a 44.1 kHz
    if int(sr) != SR:
        x = soxr.resample(x.T, int(sr), SR).T.astype(np.float32)

    # Avance real: un aviso por cada trozo que procesa el modelo
    C, N = config.inference.chunk_size, config.inference.num_overlap
    paso, borde = C // N, C - C // N
    largo = x.shape[1] + (2 * borde if x.shape[1] > 2 * borde else 0)
    total, hechos = math.ceil(largo / paso), [0]

    def aviso(*_):
        hechos[0] += 1
        print(f"Trozo {min(hechos[0], total)} / {total}", flush=True)
    modelo.register_forward_hook(aviso)

    res, _ = demix_track(config, modelo, torch.from_numpy(np.ascontiguousarray(x)), disp)
    sphn.write_wav(salida, np.ascontiguousarray(res["piano"], dtype=np.float32), SR)


def guardar_mp3(wav: Path, mp3: Path):
    """Guarda la pista de piano para escucharla (si no se puede, no pasa nada)."""
    try:
        import lameenc
        import numpy as np
        import sphn
        d, sr = sphn.read(str(wav))
        pcm = (np.clip(np.asarray(d, dtype=np.float32).T, -1, 1) * 32767).astype("<i2")
        enc = lameenc.Encoder()
        enc.set_bit_rate(192); enc.set_in_sample_rate(int(sr)); enc.set_channels(pcm.shape[1]); enc.set_quality(2)
        mp3.write_bytes(enc.encode(pcm.tobytes()) + enc.flush())
    except Exception as e:
        print(f"  (no se pudo guardar el mp3 del piano: {e})")


def alargar_por_sonido(notas, audio_mono, fs, prueba=0.1, umbral=0.6, caida=0.2, maximo=6.0):
    """Cuánto SUENA cada nota (no solo cuánto se presionó la tecla).

    Al soltar una tecla sin pedal, el apagador corta el sonido en una fracción de segundo.
    Si en cambio la nota sigue sonando (pedal de sostenido), se alarga hasta que se apague.
    Se mira la frecuencia base y el 2º armónico: ambos deben sostenerse (un sonido ajeno
    casi nunca coincide en las dos). Valores ajustados con un banco de pruebas de piano real:
    duración correcta en piezas con pedal 42.7% → 63.9%, sin pedal 82.0% → 83.2%.
    """
    import numpy as np
    from scipy.signal import stft

    nfft, salto = 4096, 512
    fmax = 5000
    nb = int(fmax / (fs / nfft)) + 2
    bloques = []
    # Se antepone media ventana de silencio para que la ventana j quede centrada en j*salto
    audio_mono = np.concatenate([np.zeros(nfft // 2, dtype=np.float32), audio_mono.astype(np.float32)])
    trozo = salto * 2600                              # ~30 s por parte (múltiplo exacto del salto)
    for i in range(0, len(audio_mono), trozo):
        x = audio_mono[max(0, i - nfft):i + trozo + nfft]
        _, _, Z = stft(x, fs, nperseg=nfft, noverlap=nfft - salto, boundary=None, padded=False)
        a = 0 if i == 0 else nfft // salto
        bloques.append(np.abs(Z[:nb, a:a + trozo // salto]).astype(np.float32))
    M = np.concatenate(bloques, axis=1)
    dt = salto / fs
    frec = np.arange(nb) * fs / nfft
    por_tecla = {}
    for n in notas:
        por_tecla.setdefault(n["midi"], []).append(n["start"])

    for n in notas:
        n["tecla"] = n["dur"]
        f0 = 440 * 2 ** ((n["midi"] - 69) / 12)
        curvas = []
        for h in (1, 2):
            if h * f0 < fmax * 0.95:
                k = int(np.argmin(np.abs(frec - h * f0)))
                curvas.append(M[max(k - 1, 0):k + 2].max(axis=0))
        if not curvas:
            continue
        largo = len(curvas[0])
        ifin = min(largo - 2, int((n["start"] + n["dur"]) / dt))
        sig = [x for x in por_tecla[n["midi"]] if x > n["start"] + 0.05]
        tope = min([n["start"] + maximo] + [x - 0.02 for x in sig])
        niveles = [c[max(0, ifin - 2):ifin + 1].mean() + 1e-9 for c in curvas]
        rel = lambda j: min(c[j] / nv for c, nv in zip(curvas, niveles))
        ip = min(largo - 1, ifin + int(prueba / dt))
        if ip * dt >= tope or rel(ip) < umbral:
            continue                                  # actuó el apagador: la nota terminó al soltar
        j = ip
        while j < largo - 1 and j * dt < tope and rel(j) > caida:
            j += 1
        n["dur"] = round(max(n["dur"], min(j * dt, tope) - n["start"]), 4)
    return notas


def transcribir_cli(entrada: str, salida: str):
    """python teclamigo.py --transcribir audio salida.json   (Transkun 2)"""
    import importlib.resources as ir
    import math

    import moduleconf
    import numpy as np
    import soxr
    import sphn
    import torch

    disp = "cuda" if torch.cuda.is_available() else "cpu"
    base = ir.files("transkun") / "pretrained"
    conf = moduleconf.parseFromFile(str(base / "2.0.conf"))
    modelo = conf["Model"].module.TransKun(conf=conf["Model"].config).to(disp)
    ck = torch.load(str(base / "2.0.pt"), map_location=disp, weights_only=False)
    modelo.load_state_dict(ck.get("best_state_dict", ck.get("state_dict")), strict=False)
    modelo.eval()

    # Audio sin ffmpeg: sphn lee WAV/MP3; el modelo espera estéreo a su frecuencia
    datos, sr = sphn.read(entrada)
    audio = np.asarray(datos, dtype=np.float32).T
    if audio.shape[1] == 1:
        audio = np.repeat(audio, 2, axis=1)
    if int(sr) != modelo.fs:
        audio = soxr.resample(audio, int(sr), modelo.fs)

    # Avance real: se cuentan los trozos que procesa el modelo
    paso, largo = modelo.segmentHopSizeInSecond, modelo.segmentSizeInSecond
    total = math.ceil((len(audio) / modelo.fs + 2 * (largo - paso)) / paso)
    original, hechos = modelo.transcribeFrames, [0]

    def con_avance(*a, **k):
        r = original(*a, **k)
        hechos[0] += 1
        print(f"Segment {min(hechos[0], total)} / {total}", flush=True)
        return r
    modelo.transcribeFrames = con_avance

    with torch.no_grad():
        notas = modelo.transcribe(torch.from_numpy(np.ascontiguousarray(audio)).to(disp))
    out = [{"midi": int(n.pitch), "start": round(float(n.start), 4),
            "dur": round(float(n.end - n.start), 4), "vel": int(n.velocity)}
           for n in notas if n.pitch > 0 and n.end > n.start and math.isfinite(n.start) and math.isfinite(n.end)]
    print("Calculando cuánto suena cada nota...", flush=True)
    out = alargar_por_sonido(out, audio.mean(axis=1), modelo.fs)
    Path(salida).write_text(json.dumps(out, allow_nan=False), encoding="utf-8")


# ---------- trabajo completo: separar + detectar ----------
class Cancelado(Exception):
    pass


def correr(cmd, al_leer, t=None):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=ENV,
                         text=True, encoding="utf-8", errors="replace")
    if t is not None:
        t["_proc"] = p                  # para poder cancelarlo desde la app
        if t.get("cancelado"):
            p.kill()
    ultimas = []
    for linea in p.stdout:          # tqdm usa \r: el modo texto lo separa en líneas
        linea = linea.strip()
        if linea:
            ultimas = (ultimas + [linea])[-8:]
            al_leer(linea)
    p.wait()
    if t is not None and t.get("cancelado"):
        raise Cancelado()
    if p.returncode != 0:
        raise RuntimeError(" / ".join(ultimas[-3:]) or "falló el proceso")


def texto_tiempo(seg):
    return f"~{max(1, round(seg / 60))} min" if seg >= 60 else "menos de 1 min"


def procesar(tid: str, datos: bytes, nombre: str, separar_piano: bool, rapido: bool = False):
    t = TRABAJOS[tid]
    try:
        CACHE.mkdir(exist_ok=True)
        base = f"{nombre_limpio(nombre)} [{hashlib.sha1(datos).hexdigest()[:10]}]"
        sep = (" piano rapido" if rapido else " piano") if separar_piano else ""
        cache_json = CACHE / f"{base}{sep} {MOTOR}.json"
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
                piano = tmp / "piano.wav"

                # Avance de la separación: el modelo avisa al terminar cada trozo (cada ~30 s o más);
                # entre aviso y aviso, un reloj interpola para que la barra y el tiempo restante se muevan.
                sep = {"hecho": 0, "total": 0, "t_ultimo": None, "por_trozo": None, "inicio": time.time(),
                       "fase": "Cargando el separador"}
                parar = threading.Event()

                def leer_rf(l):
                    m = re.match(r"Trozo (\d+) / (\d+)", l)
                    if m:
                        hecho, total, ahora = int(m.group(1)), max(1, int(m.group(2))), time.time()
                        if sep["t_ultimo"] is not None and hecho > sep["hecho"]:
                            d = (ahora - sep["t_ultimo"]) / (hecho - sep["hecho"])
                            sep["por_trozo"] = d if sep["por_trozo"] is None else 0.6 * sep["por_trozo"] + 0.4 * d
                        sep.update(hecho=hecho, total=total, t_ultimo=ahora, fase="Separando")
                        print(f"  separando el piano: trozo {hecho} de {total}", flush=True)
                    elif "MODELO_LISTO" in l:
                        sep["fase"] = "Separando el primer trozo"
                    elif "PREPARANDO_SEPARADOR" in l:
                        sep["fase"] = "Preparando el separador (la primera vez descarga ~700 MB)"
                    else:
                        m = re.search(r"(\d{1,3})%\|", l)        # avance de la descarga
                        if m:
                            sep["fase"] = f"Descargando el separador {m.group(1)}% (solo la primera vez)"

                def reloj_sep():
                    while not parar.wait(1):
                        llevas = time.time() - sep["inicio"]
                        if not sep["total"]:                       # cargando el modelo o primer trozo
                            t["mensaje"] = f"{sep['fase']} · llevas {texto_tiempo(llevas)}"
                            continue
                        if sep["por_trozo"]:
                            extra = min(0.95, (time.time() - sep["t_ultimo"]) / sep["por_trozo"])
                            frac = (sep["hecho"] + extra) / sep["total"]
                            quedan = sep["por_trozo"] * (sep["total"] - sep["hecho"] - extra)
                            msg = f"quedan {texto_tiempo(quedan)} · llevas {texto_tiempo(llevas)}"
                        else:
                            frac = sep["hecho"] / sep["total"]
                            msg = f"calculando cuánto falta... · llevas {texto_tiempo(llevas)}"
                        t.update(progreso=round(50 * frac, 1), mensaje=msg)
                threading.Thread(target=reloj_sep, daemon=True).start()
                try:
                    if rapido:
                        raise RuntimeError("se pidió la separación rápida")
                    try:
                        correr([sys.executable, str(Path(__file__).resolve()), "--separar", str(entrada), str(piano)], leer_rf, t)
                    finally:
                        parar.set()
                except Cancelado:
                    raise
                except Exception as e:
                    print(f"  Separación con Demucs ({e})")
                    t["mensaje"] = "" if rapido else "Usando el separador de respaldo (Demucs)..."
                    avance = {"pasada": 0, "ultimo": 0}

                    def leer_sep(l):
                        m = re.search(r"(\d{1,3})%\|", l)
                        if m:
                            pct = int(m.group(1))
                            if pct < avance["ultimo"] - 50:      # empezó otra pasada (--shifts)
                                avance["pasada"] += 1
                            avance["ultimo"] = pct
                            total = (min(avance["pasada"], SHIFTS - 1) + pct / 100) / SHIFTS
                            t.update(progreso=int(total * 50), mensaje="")
                    correr([sys.executable, "-m", "demucs", "-n", MODELO, "--two-stems", "piano",
                            "--shifts", str(SHIFTS), "-o", str(tmp / "salida"), str(entrada)], leer_sep, t)
                    encontrado = next((tmp / "salida").rglob("piano.wav"), None)
                    if encontrado is None:
                        raise RuntimeError("No se generó la pista de piano")
                    shutil.move(str(encontrado), piano)
                nivel = porcentaje_piano(piano, entrada)
                guardar_mp3(piano, CACHE / f"{base} - piano.mp3")
                audio = piano
                inicio_det = 50

            print(f"Detectando notas de: {nombre}")
            t.update(etapa="Detectando las notas", progreso=inicio_det, mensaje="")
            salida = tmp / "notas.json"

            def leer_det(l):
                m = re.match(r"Segment (\d+) / (\d+)", l)
                if m:
                    hecho, total = int(m.group(1)), max(1, int(m.group(2)))
                    t.update(progreso=int(inicio_det + (100 - inicio_det) * hecho / total), mensaje="")
            correr([sys.executable, str(Path(__file__).resolve()), "--transcribir", str(audio), str(salida)], leer_det, t)

            notas = json.loads(salida.read_text(encoding="utf-8"))
            cache_json.write_text(json.dumps({"notas": notas, "nivel": nivel}), encoding="utf-8")

        print(f"  Listo: {len(notas)} notas")
        t.update(estado="listo", progreso=100, mensaje="", resultado=str(cache_json))
    except Cancelado:
        print("  Cancelado por el usuario")
        t.update(estado="error", mensaje="Cancelado")
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
            return self.json({k: v for k, v in t.items() if k != "resultado" and not k.startswith("_")})
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
        if url.path == "/api/cancelar":
            t = TRABAJOS.get(q.get("id", [""])[0])
            if t and t.get("estado") == "procesando":
                t["cancelado"] = True
                proc = t.get("_proc")
                if proc and proc.poll() is None:
                    proc.kill()
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
            rapido = q.get("calidad", ["maxima"])[0] == "rapida"
            threading.Thread(target=procesar, args=(tid, datos, nombre, separar_piano, rapido), daemon=True).start()
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
    if len(sys.argv) == 4 and sys.argv[1] == "--separar":
        return separar_cli(sys.argv[2], sys.argv[3])
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
