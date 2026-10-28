# Vialidad · Detección de daños viales con YOLO26

Sistema para detectar **baches y grietas** en fotos y videos de carreteras, estimar un **índice de severidad** y llevar el **seguimiento por tramo** a lo largo del tiempo. Incluye una aplicación web, un modo de video con los daños marcados y una app Android que usa el modelo desde un PC en la misma red.

> **Estado:** proyecto académico / prototipo. El modelo se evaluó solo con RDD2022 y **no se ha validado con carreteras de Ecuador**. Los resultados deben verificarse visualmente.

---

## Contenido
1. [Características](#características)
2. [Modelo y resultados medidos](#modelo-y-resultados-medidos)
3. [Arquitectura](#arquitectura)
4. [Requisitos](#requisitos)
5. [Instalación](#instalación)
6. [Uso](#uso)
7. [App móvil (Android)](#app-móvil-android)
8. [Configuración](#configuración)
9. [Pruebas](#pruebas)
10. [Estructura del repositorio](#estructura-del-repositorio)
11. [Índice de severidad](#índice-de-severidad)
12. [Limitaciones y seguridad](#limitaciones-y-seguridad)
13. [Licencias y datos](#licencias-y-datos)

---

## Características

| Función | Descripción |
|---|---|
| Foto | Detecta 4 tipos de daño, dibuja las cajas y calcula el índice de severidad. Lee fecha y GPS del EXIF. |
| Video, modo fotogramas | Analiza un fotograma cada 0,5 / 1 / 2 / 5 s. Muestra la evolución del índice y los fotogramas más críticos. |
| Video, modo marcado | Devuelve un `.mp4` (H.264) con los daños recuadrados y un **conteo estimado de daños distintos**. Cada daño tiene una ✕ para descartar falsas alarmas. |
| Ruta GPX (opcional) | Ubica cada daño en un mapa sincronizando el video con un archivo `.gpx`. |
| Seguimiento por tramo | Guarda capturas en PostgreSQL, compara fechas y muestra una tendencia indicativa. |
| Sensibilidad | Perfil **Normal** (menos falsas alarmas) o **Sensible** (detecta más, calibrado con datos). |
| Descargas | ZIP con informe HTML, JSON, CSV e imágenes marcadas. |
| Móvil | Foto, video, informe PDF y video marcado desde Android. |

**Clases:** `longitudinal_crack`, `transverse_crack`, `alligator_crack`, `pothole`.

## Modelo y resultados medidos

Modelo **YOLO26s** entrenado sobre **RDD2022** (Ultralytics 8.4). Todas las cifras de esta tabla fueron medidas durante el proyecto.

| Conjunto | Precisión | Recall | mAP50 | mAP50-95 |
|---|---|---|---|---|
| Validación (Ultralytics) | 0,672 | 0,602 | 0,660 | 0,337 |

**Calibración de sensibilidad (conjunto de test):**

| Perfil | Umbral | Precisión | Recall | Falsas alarmas | Daños no detectados |
|---|---|---|---|---|---|
| Normal | 0,25 | 0,637 | 0,608 | 1410 | 1486 |
| Sensible | 0,11–0,17 según la clase | 0,500 | 0,695 | 2771 | 1150 |

Por cada detección verdadera adicional del perfil Sensible aparecen ≈ 4 falsas alarmas. El **bache** es la clase más débil (precisión 0,470 y recall 0,584 en test).

**Velocidad en CPU** (AMD Ryzen 5 5000, 640 px): ≈ 94 ms por imagen (≈ 10 imágenes/s). Carga del modelo: ≈ 8 s.

La calibración se puede repetir con `calibracion/calibracion_sensibilidad.ipynb` (Google Colab).

<!-- Si subes la carpeta de entrenamiento, añade aquí: curvas (results.png), matriz de confusión y args.yaml -->

## Arquitectura

```
 Navegador / App Android ──HTTP──►  FastAPI  ──►  YOLO26s (CPU)
                                       │
                                       ├──► PostgreSQL  (tramos, capturas, detecciones, videos)
                                       └──► storage/    (imágenes y videos guardados)
```

- **Backend:** FastAPI, SQLAlchemy 2, PostgreSQL (psycopg 3).
- **Inferencia:** Ultralytics, OpenCV, Pillow. Video anotado con `imageio-ffmpeg` (sin instalar ffmpeg aparte).
- **Interfaz web:** HTML + CSS + JavaScript sin proceso de build (Leaflet, Chart.js, JSZip y jsPDF incluidos).
- **Android:** envoltorio WebView en Java, sin dependencias externas.

## Requisitos

- Windows (probado), Python **3.11–3.13**
- PostgreSQL con una base de datos vacía llamada `vialidad`
- El modelo entrenado `models/best.pt`
- Para la app móvil: Android Studio y un teléfono con Android 10 o superior

## Instalación

En PowerShell, dentro de la carpeta del proyecto:

```powershell
# 1. Entorno virtual
python -m venv .venv
.\.venv\Scripts\Activate.ps1      # si se bloquea: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# 2. PyTorch solo CPU (evita descargar CUDA)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

# 3. Dependencias
pip install -r requirements.txt

# 4. Configuración
copy .env.example .env            # edita .env y escribe tu contraseña de PostgreSQL

# 5. Base de datos (una sola vez)
psql -U postgres -c "CREATE DATABASE vialidad;"

# 6. Modelo: copia best.pt a models\best.pt si no vino con el repositorio

# 7. Arrancar
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abre **http://127.0.0.1:8000**. La documentación interactiva de la API está en **/docs**. Al iniciar, la aplicación crea sola las tablas que falten.

> El primer arranque es lento (carga de PyTorch). El mapa necesita internet para los mosaicos de OpenStreetMap; lo demás funciona sin conexión.

## Uso

1. **Analizar** una foto o un video. Elige *Guardar en seguimiento* o *Solo analizar* (no guarda nada).
2. Para video elige el modo (*por fotogramas* o *video marcado*) y, si quieres, sube un `.gpx`.
3. En el resultado, abre el menú de daños y pulsa ✕ en las falsas alarmas: el conteo baja.
4. **Descargar análisis** genera un ZIP con el informe, los datos y las imágenes.
5. En **Tramos** consultas la evolución del índice y comparas capturas de distintas fechas.

**Tiempo de análisis de video ≈ fotogramas analizados × 94 ms** en el equipo medido. Un video se procesa a la vez y en segundo plano, con barra de progreso y botón Cancelar. El video original nunca se conserva.

## App móvil (Android)

El modelo sigue ejecutándose en el PC; el teléfono envía las fotos y videos por wifi.

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Luego abre la carpeta `android/` con Android Studio y ejecuta la app. Pasos completos (firewall, IP, clave de acceso, generación del APK y problemas frecuentes) en **[README_MOVIL.md](README_MOVIL.md)**.

## Configuración

Todas las opciones están en `.env` (plantilla en `.env.example`):

| Variable | Descripción | Valor por defecto |
|---|---|---|
| `DATABASE_URL` | Conexión a PostgreSQL | — |
| `MODEL_PATH` | Ruta del modelo | `models/best.pt` |
| `DEVICE` | Dispositivo de inferencia | `cpu` |
| `MAX_UPLOAD_MB` / `MAX_VIDEO_MB` | Tamaño máximo de foto / video | 15 / 500 |
| `VIDEO_MAX_FRAMES` | Límite de fotogramas por video | 300 (tope 6000) |
| `PERFIL_SENSIBLE` | Perfil sensible (solo si repites la calibración) | calibrado |
| `APP_TOKEN` | Clave de acceso opcional para `/api` y `/media` | vacío (sin clave) |
| `TIMEZONE` | Zona horaria | `America/Guayaquil` |

## Pruebas

Usa una base **aparte**: las pruebas vacían sus tablas.

```powershell
psql -U postgres -c "CREATE DATABASE vialidad_test;"
$env:TEST_DATABASE_URL="postgresql+psycopg://postgres:TU_PASSWORD@localhost:5432/vialidad_test"
pytest -q
```

La suite (53 pruebas) cubre severidad, tramos, subida, EXIF, validaciones, perfiles de sensibilidad, migración de esquema, modo «solo analizar», video, video marcado, conteo y descarte de daños, GPX y acceso con clave.

## Estructura del repositorio

```
app/                  backend (FastAPI) y interfaz web
  routers/            tramos, capturas, analizar, videos, resumen
  static/             interfaz de escritorio; static/m/ = interfaz móvil
android/              proyecto de Android Studio (WebView)
calibracion/          notebook de calibración de sensibilidad (Colab)
scripts/              medición de velocidad en tu equipo
sql/schema.sql        esquema de referencia
tests/                pruebas automáticas
models/               modelo entrenado
storage/              archivos guardados por la app (no se versiona)
README_MOVIL.md       guía de la app Android
```

## Índice de severidad

```
índice = 100 · (1 − e^(−4 · Σ peso_clase · área_caja / área_imagen))
```

Pesos: bache 1,0 · piel de cocodrilo 0,7 · grieta transversal 0,4 · grieta longitudinal 0,3.
Bandas: < 15 Bueno · < 35 Regular · < 60 Malo · ≥ 60 Muy malo.

**Es una heurística propia, no PCI ni IRI, y no está validada con un experto.** Solo es comparable entre fotos del mismo tramo, con el mismo perfil y con encuadre y luz parecidos. Una tendencia requiere al menos 3 fechas distintas.

## Limitaciones y seguridad

- El modelo se evaluó solo con RDD2022; **no se ha probado con fotos de Ecuador**. Puede dar falsas alarmas y omitir daños.
- El conteo de daños distintos en video es una **estimación** por seguimiento simple: puede unir dos daños cercanos o partir uno en dos.
- El video marcado no es en tiempo real y sale sin audio.
- La ruta GPX solo funciona si el reloj del video y el del GPX coinciden.
- **Sin `APP_TOKEN` no hay autenticación.** Usa `--host 127.0.0.1` para uso local. Con `--host 0.0.0.0` (app móvil) la conexión es HTTP sin cifrar: úsala solo en una red de confianza y con `APP_TOKEN`.
- Copias de seguridad: `pg_dump` y la carpeta `storage/` (la base guarda solo las rutas).

## Licencias y datos

- **Ultralytics YOLO:** AGPL-3.0. Verifica sus condiciones si ofreces el sistema como servicio a terceros.
- **RDD2022:** conjunto de datos de daños viales; revisa su licencia y cita a sus autores en tu trabajo.
- **Leaflet** (BSD-2), **Chart.js** (MIT), **JSZip** y **jsPDF** (MIT): incluidos con sus licencias en `app/static/vendor/`.
- **Licencia de este repositorio:** **MIT** (ver `LICENSE`): uso libre, con la condición de conservar el aviso de copyright y el nombre del autor. Los componentes de terceros (en especial Ultralytics, AGPL-3.0) mantienen sus propias licencias: ver `THIRD_PARTY_NOTICES.md`.

## Autor y cómo citar

Mario Ávila · Universidad Técnica de Machala

Si usas este trabajo, menciona al autor y el repositorio: *Mario Ávila, «Vialidad · Detección de daños viales con YOLO26», 2026, https://github.com/MarioAvilaSL/VIABILIDAD---YOLO*.
