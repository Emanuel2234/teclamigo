# 🎹 Teclamigo

App para aprender a tocar teclado o piano, pensada para principiantes. Conectas tu teclado por USB y la app te muestra qué tecla tocar, con qué mano y cuánto tiempo mantenerla, con notas que caen estilo Guitar Hero.

## Funciones

- **Detecta tu teclado** por USB-MIDI y calibra la cantidad de teclas.
- **Notas que caen**: el largo de cada barra indica cuánto mantener la tecla.
- **Dos colores**: azul para la mano izquierda y dorado para la derecha, o los que elijas en Ajustes. En las teclas negras se usa un tono más oscuro del mismo color.
- **Modos**:
  - *Espera*: no avanza hasta que tocas la nota correcta.
  - *Continuo*: avanza con ritmo, como el juego.
  - *Escuchar*: la app toca la canción sola con sonido de piano real.
- **Sonido de piano en el PC sin retraso**, con la opción de silenciar el teclado para que se escuche solo el PC. Prueba varias órdenes MIDI (*Local Control*, volumen por canal, volumen general y cortar cada nota al instante) y te pregunta cuál funcionó; si tu teclado no acepta ninguna, te explica cómo apagar sus parlantes.
- **Pedal**: si tu teclado tiene pedal de sostenido, el sonido del PC lo respeta. Si no, el *pedal automático* deja sonar lo que tocas mientras sigas en el mismo acorde y lo corta cuando cambia la armonía.
- **Pantalla completa** (botón ⛶, tecla `P` o doble clic): el teclado y las notas ocupan toda la pantalla, con la opción de acercarse solo a las teclas que usa la canción.
- **Barra de reproducción**: línea de tiempo que se puede arrastrar, tocar/pausar con la barra espaciadora y ← → para moverse 5 segundos.
- **Repetir una parte**: marcas dónde empieza y dónde termina, y se repite en bucle para practicarla.
- **Pantalla de bienvenida**: arrastra tu canción o elige una de la biblioteca.
- **Biblioteca incluida** de canciones de dominio público con arreglos simples a dos manos (Estrellita, Martinillo, Cumpleaños feliz, Himno a la Alegría, Jingle Bells, Noche de paz, Minueto en Sol, Para Elisa y más), por nivel.
  Incluye además **versiones originales**, tomadas de ediciones reales (no escritas de memoria) y comprobadas nota por nota:
  - Minueto en Sol (BWV Anh. 114) y Para Elisa (WoO 59) completos, de ediciones de dominio público del [Mutopia Project](https://www.mutopiaproject.org/).
  - Noche de paz en su versión original de 1818 (dos voces y guitarra, pasadas a las dos manos) y el Himno a la Alegría a 4 voces, también del Mutopia Project.
  - Estrellita con el tema original de Mozart (K. 265), del corpus [TAVERN](https://github.com/jcdevaney/TAVERN) (Devaney y otros, 2015), licencia [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/): se tomó solo el tema y se desplegaron sus repeticiones.
- **Lee partituras MusicXML** (`.musicxml`, `.xml`, `.mxl`, el formato que exportan MuseScore, Finale y Sibelius):
  - El pentagrama de arriba es la mano derecha y el de abajo la izquierda.
  - Respeta acordes, ligaduras, repeticiones con 1ª y 2ª vuelta y cambios de tempo.
  - Si la partitura trae digitación, muestra qué dedo usar (1 = pulgar … 5 = meñique).
- **Lee videos tutoriales de piano** (los de notas que caen y teclas que se iluminan):
  - Desde un archivo de video (`.mp4`) o desde un video que se está reproduciendo en otra pestaña, por ejemplo en YouTube, **sin descargarlo**.
  - Encuentra el teclado del video, anota qué teclas se iluminan y cuánto rato, y separa las notas repetidas.
  - Si el video usa dos colores, los usa para saber qué mano toca cada nota.
  - También **escucha el audio del video** con el motor de piano y junta las dos cosas: el audio confirma qué notas suenan
    (y corrige el teclado si quedó corrido), y el video dice la mano y la duración exacta. Si el video no se puede leer,
    usa solo el audio.
  - El resultado se puede guardar como MIDI para no tener que leer el video otra vez.
- **Carga canciones** en MIDI, WAV o MP3:
  - En los MIDI elige solo las pistas de piano y descarta la batería.
  - En los audios, separa el piano con BS-RoFormer (o [Demucs](https://github.com/facebookresearch/demucs) de Meta como respaldo) y detecta las notas con [Transkun 2](https://github.com/Yujia-Yan/Skipping-The-Frame-Level), uno de los transcriptores de piano más precisos publicados.
  - Sin el motor local, usa [Basic Pitch](https://github.com/spotify/basic-pitch) (Spotify) en el navegador.
- **Dificultad** para cualquier canción: Principiante (una nota por mano), Intermedio o Avanzado.
- **Reparte las manos solo**, siguiendo dónde está cada mano en el teclado.
- Practica con una mano o ambas, a la velocidad que quieras.
- **Editor de notas** (✏️ Editar notas): dibuja notas arrastrando, alárgalas o acórtalas desde sus bordes o escribiendo los segundos, muévelas, bórralas y cámbialas de mano. Elige varias con un recuadro, cópialas y pégalas, con guías rosadas que muestran cuándo calzan con otras notas (como en Canva). Cada cambio se aprende: la app busca partes iguales de la canción y pregunta si repetirlo ahí.
- **Partitura** (📄 Partitura y video): convierte la canción en una partitura de piano (mano derecha en clave de sol, izquierda en clave de fa) y la descarga en **PDF** o **MusicXML** para abrirla en MuseScore. Sigue el pulso real de la canción aunque acelere o frene (con [Beat This!](https://github.com/CPJKU/beat_this) en el audio, o calculado a partir de las notas), detecta el compás y el compás de entrada, escribe repeticiones con casillas de 1.ª y 2.ª vez, tresillos, matices (si la fuerza de las notas cambia) y una digitación sugerida.
- **Video tutorial**: crea un video de la canción entera, con las notas cayendo, el teclado iluminado y el sonido del piano, en HD o Full HD (MP4, o WebM si el navegador no puede hacer MP4).

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

## Cómo lee un video tutorial

1. **Encuentra el teclado** por el patrón de las teclas negras (grupos de 2 y 3) y calcula qué nota es cada tecla
   (reconoce teclados de 88, 76, 61 y 49 teclas; si no, se puede subir o bajar una octava, o marcar el teclado a mano).
2. **Mira cada cuadro**: una tecla está apretada cuando su color se aleja del color que tiene apagada. Corrige cuando algo
   oscurece todo el teclado (los controles del reproductor) o cuando hay una foto encima.
3. **Separa notas repetidas** siguiendo la línea entre dos barras que caen, a la velocidad medida en el mismo video.
4. **Reparte las manos** por los colores del video; si usa un solo color, las reparte la app.
5. **Escucha el audio** (el de la pestaña o el del archivo) con Transkun y lo compara con lo que vio: busca el desfase y el
   corrimiento de teclas que más notas hace coincidir. Si casi todo coincide, usa las notas del video; si no, las del audio.
   Las notas que el audio escuchó pero el video no muestra (ecos, octavas fantasma) se descartan, y cada nota dura lo que
   muestra el video (su tecla encendida o su barra).

En videos de prueba fabricados con notas conocidas acierta entre el 97% y el 100% de las notas; con el audio, también
cuando el teclado quedó marcado una octava corrido o cuando las teclas del video no se iluminan.

**Siguiendo las barras completas.** Además de mirar las teclas que se iluminan, la app sigue cada barra de color mientras cae: un pedazo de barra a cierta altura en un cuadro corresponde al momento en que esa parte llega a la tecla. Así cada nota se mide en decenas de cuadros, el hueco entre dos notas repetidas se ve claro y la duración sale exacta. Como muchos videos (grabaciones de pantalla) repiten o saltan cuadros, el momento real de cada cuadro se corrige midiendo cuánto bajaron las barras. Cuando el video deja un hueco entre notas (como Synthesia), esta lectura manda; si no, se combina con la de las teclas iluminadas.

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
- Partituras: [Verovio](https://www.verovio.org/) y [jsPDF](https://github.com/parallax/jsPDF).
- Videos: [mp4-muxer y webm-muxer](https://github.com/Vanilagy/mp4-muxer).
- Audio a notas: [Transkun 2](https://github.com/Yujia-Yan/Skipping-The-Frame-Level) (Yan & Duan, 2024) y [Basic Pitch](https://github.com/spotify/basic-pitch) de Spotify.
- Versiones originales: ediciones de dominio público del [Mutopia Project](https://www.mutopiaproject.org/) y el corpus [TAVERN](https://github.com/jcdevaney/TAVERN) (CC BY-SA 4.0).
- Pulso y compases: [Beat This!](https://github.com/CPJKU/beat_this) (Foscarin, Schlüter y Widmer, 2024).
- Separación de instrumentos: [Demucs](https://github.com/facebookresearch/demucs) de Meta.
