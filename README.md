# 🎹 Teclamigo

App para aprender a tocar teclado o piano, pensada para principiantes. Conectas tu teclado por USB y la app te muestra qué tecla tocar, con qué mano y cuánto tiempo mantenerla, con notas que caen estilo Guitar Hero.

## Funciones

- **Detecta tu teclado** por USB-MIDI y calibra la cantidad de teclas.
- **Notas que caen**: el largo de cada barra indica cuánto mantener la tecla.
- **Dos colores**: verde para la mano derecha, morado para la izquierda.
- **Modos**:
  - *Espera*: no avanza hasta que tocas la nota correcta.
  - *Continuo*: avanza con ritmo, como el juego.
  - *Escuchar*: la app toca la canción sola con sonido de piano real.
- **Carga canciones** en MIDI, WAV o MP3:
  - En los MIDI elige solo las pistas de piano y descarta la batería.
  - Los audios se convierten a notas con [Basic Pitch](https://github.com/spotify/basic-pitch) (Spotify).
  - Antes de convertir, puede separar solo el piano con [Demucs](https://github.com/facebookresearch/demucs) (Meta).
  - Limpia las notas de más (ecos de octava, notas muy cortas o muy suaves).
- Practica con una mano o ambas, a la velocidad que quieras.

## Requisitos

- Windows, macOS o Linux con **Python 3.10 o superior**.
- **Chrome o Edge** (son los navegadores compatibles con MIDI).
- Teclado con salida USB-MIDI (opcional; también se puede probar con el teclado del PC).

## Cómo correrla

```
python -m pip install -r requirements.txt
python teclamigo.py
```

La app se abre sola en el navegador. Para cerrarla, aprieta `Ctrl + C` en la terminal.

La primera vez que separas el piano de un audio se descarga el modelo de Demucs (unos 80 MB).

## Estructura

| Archivo | Qué hace |
|---|---|
| `teclamigo.py` | Servidor local: abre la app y separa el piano con Demucs |
| `teclamigo.html` | La app: piano, notas que caen, modos y conversión de audio |
| `requirements.txt` | Dependencias de Python |

## Créditos

- Sonido de piano: Salamander Grand Piano (vía [Tone.js](https://tonejs.github.io/)).
- Lectura de MIDI: [@tonejs/midi](https://github.com/Tonejs/Midi).
- Audio a notas: [Basic Pitch](https://github.com/spotify/basic-pitch) de Spotify.
- Separación de instrumentos: [Demucs](https://github.com/facebookresearch/demucs) de Meta.
