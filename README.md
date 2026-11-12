# 🎹 Teclamigo

App para aprender a tocar teclado o piano, pensada para principiantes. Conectas tu teclado por USB y la app te muestra qué tecla tocar, con qué mano y cuánto tiempo mantenerla, con notas que caen estilo Guitar Hero.

## Funciones

- **Detecta tu teclado** por USB-MIDI y calibra la cantidad de teclas.
- **Notas que caen**: el largo de cada barra indica cuánto mantener la tecla.
- **Dos colores**: dorado para la mano derecha, azul para la izquierda.
- **Modos**:
  - *Espera*: no avanza hasta que tocas la nota correcta.
  - *Continuo*: avanza con ritmo, como el juego.
  - *Escuchar*: la app toca la canción sola con sonido de piano real.
- **Sonido de piano en el PC sin retraso**, con la opción de silenciar el teclado para que se escuche solo el PC. Prueba varias órdenes MIDI (*Local Control*, volumen por canal, volumen general y cortar cada nota al instante) y te pregunta cuál funcionó; si tu teclado no acepta ninguna, te explica cómo apagar sus parlantes.
- **Pantalla completa** (botón ⛶, tecla `P` o doble clic): el teclado y las notas ocupan toda la pantalla, con la opción de acercarse solo a las teclas que usa la canción.
- **Barra de reproducción**: línea de tiempo que se puede arrastrar, tocar/pausar con la barra espaciadora y ← → para moverse 5 segundos.
- **Repetir una parte**: marcas dónde empieza y dónde termina, y se repite en bucle para practicarla.
- **Pantalla de bienvenida**: arrastra tu canción o elige una de la biblioteca.
- **Biblioteca incluida** de canciones de dominio público con arreglos simples a dos manos (Estrellita, Martinillo, Cumpleaños feliz, Himno a la Alegría, Jingle Bells, Noche de paz, Minueto en Sol, Para Elisa y más), por nivel.
- **Lee partituras MusicXML** (`.musicxml`, `.xml`, `.mxl`, el formato que exportan MuseScore, Finale y Sibelius):
  - El pentagrama de arriba es la mano derecha y el de abajo la izquierda.
  - Respeta acordes, ligaduras, repeticiones con 1ª y 2ª vuelta y cambios de tempo.
  - Si la partitura trae digitación, muestra qué dedo usar (1 = pulgar … 5 = meñique).
- **Carga canciones** en MIDI, WAV o MP3:
  - En los MIDI elige solo las pistas de piano y descarta la batería.
  - En los audios, separa el piano con BS-RoFormer (o [Demucs](https://github.com/facebookresearch/demucs) de Meta como respaldo) y detecta las notas con [Transkun 2](https://github.com/Yujia-Yan/Skipping-The-Frame-Level), uno de los transcriptores de piano más precisos publicados.
  - Sin el motor local, usa [Basic Pitch](https://github.com/spotify/basic-pitch) (Spotify) en el navegador.
- **Dificultad** para cualquier canción: Principiante (una nota por mano), Intermedio o Avanzado.
- **Reparte las manos solo**, siguiendo dónde está cada mano en el teclado.
- Practica con una mano o ambas, a la velocidad que quieras.

## Cómo convierte un audio en notas

Cada etapa usa lo más preciso que se puede correr gratis en un PC, elegido con datos:

1. **Separar el piano** con BS-RoFormer SW, el separador de piano con mejor puntaje público
   (7,83 dB contra 2,23 dB de Demucs 6 pistas, según la [tabla de MVSEP](https://www.mvsep.com/algorithms)).
   Si no está disponible, usa Demucs.
2. **Detectar las notas** con [Transkun 2](https://arxiv.org/html/2404.09466v6) (98,3% de inicios de nota
   y 93,5% de notas con duración correcta en MAESTRO).
3. **Calcular cuánto suena cada nota**: si la nota sigue sonando después de soltar la tecla (pedal de
   sostenido), la barra se alarga hasta que se apague. Se exige que se sostengan la frecuencia base y el
   2º armónico, para no confundir sonidos de otros instrumentos.
4. **Limpiar** notas falsas (cortas y mucho más suaves que sus vecinas), con valores ajustados en un banco
   de pruebas de piano real mezclado con voz, bajo y batería.
5. **Repartir las manos** respetando lo que una mano puede tocar (5 dedos, una octava, sin cruzarse).

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

La primera vez que conviertes un audio se descarga el separador (~700 MB); el detector de piano viene incluido en el paquete. Las canciones ya procesadas se guardan en la carpeta `Piano separado` y la próxima vez cargan al instante.

## Estructura

| Archivo | Qué hace |
|---|---|
| `teclamigo.py` | Servidor local: abre la app, separa el piano y detecta las notas |
| `teclamigo.html` | La app: piano, notas que caen, modos y conversión de audio |
| `requirements.txt` | Dependencias de Python |

## Créditos

- Sonido de piano: Salamander Grand Piano (vía [Tone.js](https://tonejs.github.io/)).
- Lectura de MIDI: [@tonejs/midi](https://github.com/Tonejs/Midi).
- Audio a notas: [Transkun 2](https://github.com/Yujia-Yan/Skipping-The-Frame-Level) (Yan & Duan, 2024) y [Basic Pitch](https://github.com/spotify/basic-pitch) de Spotify.
- Separación de instrumentos: [Demucs](https://github.com/facebookresearch/demucs) de Meta.
