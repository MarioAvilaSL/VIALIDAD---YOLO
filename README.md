# Vialidad · Detección y seguimiento de daños viales

Aplicación web local que analiza **fotos y videos** de carreteras con **YOLO26s** (entrenado sobre RDD2022),
marca baches y grietas, calcula un **índice de severidad** y guarda todo en **PostgreSQL** para
seguir la evolución de cada tramo en el tiempo.

## Qué hace
- **Analizar fotos o videos** con dos destinos:
  - **Guardar en seguimiento:** se guardan el resultado, las imágenes, la fecha, el GPS (foto) y los parámetros usados.
  - **Solo analizar:** ves el resultado y **no se guarda nada** (ni en la base ni en disco). El video subido se borra siempre.
- **Sensibilidad Normal / Sensible:** el perfil Sensible detecta más daños leves a costa de más falsas alarmas (ver «Sensibilidad»).
- **Video:** se analiza **1 fotograma cada N segundos** (0,5 / 1 / 2 / 5 s). Resultado: índice a lo largo del video, % de fotogramas con daños y los fotogramas más críticos.
- **Seguimiento por tramo:** evolución del índice por fecha (fotos y videos), tendencia indicativa, comparación de dos capturas y línea de tiempo.
- **Panel:** totales, mapa de capturas con GPS, distribución de daños y últimas capturas.

## Requisitos (Windows)
- Python **3.11–3.13** (marca "Add python.exe to PATH" al instalar)
- PostgreSQL y una base de datos vacía llamada `vialidad`
- El archivo `best.pt` que entrenaste en Colab

## Instalación paso a paso (PowerShell, dentro de la carpeta del proyecto)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # si PowerShell lo bloquea: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# PyTorch SOLO CPU (evita descargar ~2 GB de CUDA que tu equipo no usará)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

copy .env.example .env                # edita .env y pon tu contraseña de PostgreSQL
# copia best.pt a la carpeta models\  (models\best.pt)

psql -U postgres -c "CREATE DATABASE vialidad;"     # una sola vez (o créala desde pgAdmin)
uvicorn app.main:app --host 127.0.0.1 --port 8000
```
Abre **http://127.0.0.1:8000** · API interactiva en **/docs**.

**Si ya tenías la versión anterior (Fase 5):** copia los archivos nuevos encima y arranca. Al iniciar, la app **añade sola**
las tablas y columnas nuevas (`videos`, `video_frames`, `capturas.perfil`, `capturas.parametros`) sin tocar tus datos;
las capturas antiguas quedan marcadas como sensibilidad «normal». Por prudencia, antes haz una copia:
`pg_dump -U postgres vialidad > respaldo.sql` (y copia la carpeta `storage\`).

Notas: el primer arranque es lento (carga de PyTorch). El mapa necesita internet para los mosaicos de OpenStreetMap; lo demás funciona sin conexión.

## Sensibilidad: qué es y cómo calibrarla con datos
Bajar el umbral de confianza hace que el modelo acepte detecciones menos seguras: **sube el recall (detecta más daños reales) y baja la precisión (más falsas alarmas)**. Siempre es un intercambio; no existe un umbral "correcto".

| Perfil | Umbral | Estado |
|---|---|---|
| Normal | 0.25 | Valor por defecto de Ultralytics. |
| Sensible | 0,11–0,17 según la clase (grieta longitudinal 0,16 · transversal 0,17 · piel de cocodrilo 0,11 · bache 0,14) | **Calibrado** con el notebook sobre validación (2100 imágenes) y confirmado una vez en test. |

**Resultado medido en test (RDD2022, tu modelo):** el perfil sensible sube el recall de 0,608 a 0,695, pero la precisión baja de 0,637 a 0,500. Las falsas alarmas pasan de 1410 a 2771 y los daños no detectados de 1486 a 1150: **por cada detección verdadera extra aparecen ≈4 falsas alarmas**. El bache es la clase más débil (precisión 0,470 y recall 0,584 en test). Subir la resolución (800/960) o usar TTA no mejoró de forma relevante (TTA a 800: +0,015 de recall con ≈2,6× el tiempo), así que el umbral es la única palanca eficaz sin reentrenar; mejorar el bache requiere más y mejores datos. Hipótesis sin medir: parte de las «falsas alarmas» podrían ser daños reales sin etiquetar en RDD2022.

Para repetir o ajustar la calibración:

1. Abre `calibracion/calibracion_sensibilidad.ipynb` en Google Colab (GPU T4) y ejecútalo en orden. Reconstruye el dataset, **comprueba que el split es idéntico al de la Fase 4** (si no lo es, se detiene), y mide precisión y recall por clase para varias configuraciones (umbral, resolución 800/960, TTA).
2. Tú eliges `PRECISION_MIN` (cuántas falsas alarmas toleras; por defecto 0,50). El notebook elige umbrales por clase **con validación** y los confirma **una sola vez en test**.
3. Al final imprime una línea `PERFIL_SENSIBLE={...}`. Pégala en tu `.env` y reinicia la app.

Otras opciones del perfil (en `.env`): `conf_clase` (umbral propio por clase, p. ej. más bajo para baches), `imgsz` (resolución) y `augment` (TTA). La resolución mayor y el TTA **cuestan tiempo de CPU**: mide en tu equipo con
`python scripts/medir_velocidad.py ruta\foto.jpg` antes de usarlos en videos largos.

Hallazgos técnicos verificados (Ultralytics 8.4): tu `best.pt` trae dos cabezas (con NMS y sin NMS); la app usa la de NMS, que es la que se midió en el entrenamiento y la única que admite TTA. Ultralytics conserva estado entre llamadas, por lo que la app envía siempre todos los parámetros explícitos.

**Importante:** el índice de severidad depende del perfil. Un mismo tramo analizado con «Normal» y con «Sensible» da índices distintos; el seguimiento avisa si mezclas perfiles. Mantén el mismo perfil dentro de un tramo.

## Video
- Formatos: MP4, MOV, AVI, MKV, WEBM (lo más seguro es MP4 con H.264). Máximo 500 MB (`MAX_VIDEO_MB`).
- **Dos modos:** *Por fotogramas* (rápido: gráfica del índice y los 8 fotogramas más críticos) y *Video con baches marcados* (devuelve un `.mp4` H.264 con las cajas dibujadas y un rótulo con el índice; se reproduce y descarga desde la pantalla). En el modo anotado se analiza 1 de cada N fotogramas (N = 1, 2, 3, 5 o 10) y los intermedios repiten las cajas del último análisis, por lo que con la cámara en movimiento se desfasan un poco. **No es en tiempo real** (se procesa y luego se entrega) y el video sale **sin audio**. Se codifica con el ffmpeg incluido en `imageio-ffmpeg` (no instalas nada más). Ocupa disco: unos pocos MB por minuto a 1280 px (`VIDEO_CRF`, 23 por defecto; más alto = más liviano). En «solo analizar» el archivo es temporal: descárgalo antes de recargar.
- **Límite de fotogramas ajustable** en la pantalla (por defecto `VIDEO_MAX_FRAMES` = 300, máximo `VIDEO_MAX_FRAMES_CAP` = 6000). Si el video da más análisis que el límite, el paso se amplía solo y la pantalla lo avisa.
- El análisis corre en segundo plano con barra de progreso y botón Cancelar. **Un video a la vez.** Los trabajos viven en memoria: si reinicias el servidor se pierden los que estén en curso (los ya guardados no).
- **Tiempo aproximado = fotogramas analizados × ms por imagen.** En tu Ryzen 5 se midió ≈94 ms (≈10 fotogramas/s) con 640 px: analizar *todos* los fotogramas de un video a 30 fps tarda ≈3 veces su duración; con 1 de cada 3 es ≈ la duración del video. La pantalla muestra esta estimación.
- **Límites actuales (honestos):**
  - **Conteo estimado (solo «Video con baches marcados»).** Un seguimiento sencillo (IoU + desplazamiento previsto) une las detecciones de la misma clase entre fotogramas analizados para contar cada daño una vez. Es una **heurística**: puede unir dos daños cercanos o partir uno en dos, y con 1 de cada >5 fotogramas puede perder daños. Se descartan los que aparecen en un solo análisis (salvo con 1 de cada 10). Por eso el resultado trae un menú «Daños distintos estimados» con la imagen de cada uno y una ✕ para descartar falsas alarmas; el conteo baja y, en videos guardados, el descarte queda en la base de datos. El modo «por fotogramas» **no cuenta**: con un fotograma por segundo no se puede saber si es el mismo daño.
  - **Ruta GPS opcional (GPX).** Sube un `.gpx` (de tu teléfono o app de ciclismo/rutas) e indica la hora local en que empezó el video: cada daño y cada fotograma crítico se ubican por hora y se dibujan en un mapa. Funciona solo si los relojes coinciden; hay un ajuste de sincronía en segundos. Se rechaza el GPX si su rango no coincide con la hora indicada. Sin GPX no hay ubicación.
  - El video original **no se conserva**; se guardan los resultados, los fotogramas más críticos (8 por video, `VIDEO_TOP_FRAMES`) y, solo en el modo anotado guardado, el `.mp4` anotado.
  - Los fotogramas se reducen a 1280 px de lado mayor antes de analizarse (`VIDEO_MAX_SIDE`).

## Versión móvil (Android)
Hay una pantalla simple para celular en `/m/` y un proyecto de Android Studio en `android/`. Guía completa: **[README_MOVIL.md](README_MOVIL.md)**.

## Descargar el análisis
Cada resultado (foto o video, guardado o «solo analizar») tiene el botón **Descargar análisis**: un ZIP armado en tu navegador (por eso funciona también sin guardar nada) con `informe.html` (ábrelo tras descomprimir; se puede imprimir a PDF), `analisis.json`, CSV y las imágenes marcadas. Foto: `foto_marcada.jpg`, `foto_original.jpg`, `detecciones.csv`. Video: `serie_indice.csv`, `muestras/` (fotogramas críticos), y en el modo marcado `danos.csv` (con el estado conservado/descartado) y `danos/` (solo los conservados); con GPX, `ruta.geojson`. El video anotado se descarga aparte (botón propio) porque pesa más. En «solo analizar» el video anotado es temporal.

## Pruebas
Crea una base de datos aparte (**las pruebas vacían sus tablas**, nunca uses la real):
```powershell
psql -U postgres -c "CREATE DATABASE vialidad_test;"
$env:TEST_DATABASE_URL="postgresql+psycopg://postgres:TU_PASSWORD@localhost:5432/vialidad_test"
pytest -q
```
48 pruebas: severidad, tramos, subida (con el modelo real si `models/best.pt` existe), EXIF, validaciones, perfiles de sensibilidad, migración de esquema, «solo analizar» (verifica que no escribe nada), video (muestreo, límites, cancelación, guardado, borrado de archivos), video anotado (H.264 con todos los fotogramas, guardado/borrado, cancelación sin restos) límite de fotogramas configurable, conteo de daños distintos, descarte persistente y GPX (sincronía, errores, rechazo de XML con DOCTYPE).

## Estructura
(Además: `app/static/m/` = página móvil, `android/` = app Android que la envuelve.)

```
app/
  main.py, config.py, db.py, models.py   arranque, configuración, SQLAlchemy (tramos, capturas, detecciones, videos, video_frames)
  inference.py   carga única de YOLO, perfiles de sensibilidad, dibujo de cajas
  video.py, jobs.py   análisis de video por muestreo y trabajos en segundo plano
  services.py, severity.py, exif.py
  routers/       tramos, capturas, analizar (solo analizar), videos, resumen
  static/        interfaz web (HTML + CSS + JS, sin build; Leaflet y Chart.js incluidos)
calibracion/calibracion_sensibilidad.ipynb   notebook de Colab (ver arriba)
scripts/medir_velocidad.py                   mide ms/imagen en tu equipo
models/best.pt     tu modelo (no se incluye)
storage/           fotos y fotogramas guardados (no se versiona)
sql/schema.sql     esquema de referencia (la app crea y actualiza el suyo sola)
tests/
```

## Cómo se calcula el índice de severidad (léelo antes de citarlo)
`índice = 100 · (1 − e^(−K · Σ peso_clase · área_caja/área_imagen))`, con K = 4 y pesos
bache 1.0, piel de cocodrilo 0.7, grieta transversal 0.4, grieta longitudinal 0.3
(bandas: <15 Bueno, <35 Regular, <60 Malo, ≥60 Muy malo).

**Es una heurística propia, no un estándar de ingeniería (PCI, IRI) ni una medición validada.**
Los pesos y K son criterio del proyecto y deben calibrarse con un experto o con datos reales.
Solo es comparable entre fotos del mismo tramo, con el mismo perfil y con encuadre, altura y luz parecidos.
El área de una caja sobrestima el daño real y las cajas solapadas se suman.

## Cómo tomar fotos para que el seguimiento sirva
Mismo punto, misma altura y ángulo, preferiblemente a la misma hora; registra siempre fecha y tramo.
Una tendencia necesita **al menos 3 fechas distintas**, y si los índices no siguen un patrón (R² < 0,25) la app dice «sin tendencia clara» en vez de inventar una dirección.

## Seguridad y límites actuales
- **No tiene autenticación.** Es para uso local (`--host 127.0.0.1`). No la expongas a Internet ni a tu red sin añadir login y HTTPS.
- Valida el tipo real de imagen, el tamaño máximo y el límite de píxeles; guarda con nombres aleatorios; desactiva la autoinstalación de paquetes de Ultralytics (`YOLO_AUTOINSTALL=False`).
- El modelo se evaluó solo con RDD2022 (Japón, India, Chequia, EE. UU., China-moto): **no se ha probado con fotos de Ecuador**. Mide con tus fotos antes de confiar en los resultados.
- Copias de seguridad: `pg_dump` **y** copiar `storage/` (la base guarda solo las rutas).

## Licencias
Ultralytics YOLO es AGPL-3.0 (uso académico/personal local sin problema; para ofrecer el servicio a terceros revisa la licencia Enterprise). Leaflet (BSD-2) y Chart.js (MIT) van incluidos con sus licencias. RDD2022 se distribuye bajo CC BY 4.0 según su registro en Figshare: verifícalo y cítalo.
