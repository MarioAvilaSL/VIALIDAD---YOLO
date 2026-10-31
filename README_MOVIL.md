# Vialidad en el celular (Android)

**Cómo funciona:** el modelo sigue corriendo en tu PC. La app del celular solo toma la foto/video, la envía al PC por el wifi, muestra el resultado y guarda el informe PDF en el teléfono.

```
Celular (app)  ──wifi──►  PC con el servidor (modelo YOLO26s)
```

Necesitas: el PC encendido con el servidor corriendo, y el celular **en la misma red wifi**.

---

## 1) Preparar el PC (una sola vez)

1. **Clave de acceso (recomendado).** En `.env` agrega una línea, por ejemplo:
   ```
   APP_TOKEN=una-clave-larga-sin-espacios
   ```
2. **Arrancar el servidor para que el celular lo vea.** Antes usabas `127.0.0.1`; ahora debe escuchar en toda la red:
   ```powershell
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
3. **Firewall de Windows.** La primera vez Windows pregunta si permite la conexión: marca **Redes privadas** y acepta. Si no apareció el aviso, en PowerShell **como administrador**:
   ```powershell
   New-NetFirewallRule -DisplayName "Vialidad 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
   ```
4. **Averigua la IP del PC:** `ipconfig` → «Dirección IPv4» de tu adaptador wifi (ej. `192.168.1.10`). Tu dirección será `http://192.168.1.10:8000`.
5. **Prueba rápida desde el navegador del celular** (mismo wifi): abre `http://192.168.1.10:8000/health`. Debe responder `{"ok":true}`. Si no responde, el problema es red/firewall, no la app.

> Si el wifi es de una universidad o un lugar público, a veces bloquea la comunicación entre dispositivos («aislamiento de clientes»). En ese caso usa el hotspot (punto de acceso) del celular y conecta el PC a él.

## 2) Probar sin instalar nada (opcional)

Con el celular en el mismo wifi, abre en Chrome: `http://192.168.1.10:8000/acceso?t=TU_CLAVE` (sin clave: `http://192.168.1.10:8000/m/`). Ya funciona la pantalla móvil completa. Lo único que cambia con la app es la comodidad: ícono propio, cámara integrada y guardado directo en Descargas. (Chrome no permite «instalar» páginas por HTTP; por eso existe la app.)

## 3) Crear la app (Android Studio)

1. **File ▸ Open** y elige la carpeta `android/` de este proyecto.
2. Espera a que termine el *Gradle Sync* (la primera vez descarga cosas; necesita internet). Si pide actualizar algo, acepta lo mínimo o cancela.
3. Activa en el celular **Opciones de desarrollador ▸ Depuración USB** y conéctalo por cable. Elige tu celular arriba y pulsa **Run ▶**. Se instala y abre.
   - Para un APK que puedas pasar: **Build ▸ Build Bundle(s)/APK(s) ▸ Build APK(s)**. Se genera en `android/app/build/outputs/apk/debug/`. Pásalo al teléfono e instálalo (permite «instalar apps desconocidas»).
4. Al abrir la app, escribe la dirección (`http://192.168.1.10:8000`) y, si definiste `APP_TOKEN`, la clave. Pulsa **Guardar y abrir**. El engranaje ⚙ de la esquina cambia el servidor.

Requisitos de la app: Android 10 o superior (minSdk 29). No usa librerías externas.

## 4) Uso

1. **Tomar foto**, **Grabar video** o **Galería**.
2. Elige sensibilidad (Normal / Sensible). Para video: **Video marcado** (devuelve el video con recuadros y un conteo de daños distintos) o **Por fotogramas** (muestrea y muestra los más dañados).
3. **Analizar.** Una foto tarda ~1 s. Un video procesa ≈10 fotogramas por segundo en un PC como el que mediste (≈94 ms/imagen); un video de 1 minuto con «1 de cada 3» son unos 600 fotogramas ≈ 1 min.
4. En el resultado, abre «Dónde están los daños» y toca **✕** para descartar falsas alarmas; el conteo baja.
5. **Guardar informe (PDF)** → queda en la carpeta **Descargas** del teléfono. **Guardar video marcado** descarga el mp4.

## Límite de fotogramas (video)

En las opciones de video, «Máximo de fotogramas a analizar» ofrece 250, 500, 1000, 2000, 4000 y 6000 (el tope lo fija `VIDEO_MAX_FRAMES_CAP` en el servidor; por defecto 6000). Si el video tiene más fotogramas, el servidor analiza uno de cada varios para no pasar del límite. Bajo el menú se muestra el tiempo máximo estimado (límite × milisegundos por imagen medidos en tu PC; es solo inferencia, la lectura y el guardado del video suman).

## Guardar en la base de datos del servidor

En «2. Opciones» elige **Guardar en el servidor** en lugar de «Solo analizar». Entonces el resultado, las imágenes y el conteo quedan en PostgreSQL, igual que con la versión de PC:

- **Tramo:** elígelo de la lista. Para crear uno nuevo, pulsa «Añadir / administrar tramos» o el engranaje ⚙ (Ajustes): nombre, ciudad, descripción y, si quieres, coordenadas (puedes usar tu ubicación actual).
- **Fecha y hora:** «Automática» usa la fecha de la foto (EXIF) o, si no la trae, la hora de envío; en video, la hora de envío. «Elegir» te deja poner la fecha y hora (para video, la hora en que **empezó** la grabación; se sugiere a partir del archivo, pero puede no ser exacta: corrígela).
- **Ubicación (foto):** «Automática» usa el GPS de la foto si lo trae; «Elegir» permite escribir latitud y longitud o pulsar «Usar mi ubicación actual» (la app pide permiso de ubicación y necesita el GPS encendido).
- **Ubicación (video):** adjunta un archivo **GPX** grabado en el mismo recorrido (opcional). Hay que indicar la hora de inicio del video y que coincida con el reloj del GPX; si no coincide, el servidor lo rechaza con un mensaje. Hay un ajuste de sincronía en segundos.
- **Notas** opcionales.
- En videos guardados, la ✕ que descarta un daño **también queda guardada** en el servidor.

Lo guardado se ve después en la versión web de PC (Tramos y Panel) y también en la app:

## Seguimientos (historial en el teléfono)

El botón 📋 de la esquina superior abre una vista simple del historial guardado:

- Eliges un **tramo** y ves cuántas fotos y videos tiene, el último índice con su calificación, el mensaje de tendencia (necesita al menos 3 fechas) y una gráfica del índice por fecha.
- Debajo, la lista de **análisis guardados** (fotos y videos, del más reciente al más antiguo). Al tocar uno se abre su resultado completo: foto marcada, o video con el conteo y los daños; en videos se pueden descartar daños (✕) y el cambio queda guardado.
- Desde ahí también se puede **guardar el informe PDF** de ese análisis o **eliminarlo del servidor** (pide pulsar dos veces para confirmar).

## Recorrido con GPS (rama `experimental`)

El botón **🛣 Recorrido con GPS** abre una pantalla de grabación propia de la app:

1. Concede los permisos de cámara y ubicación la primera vez.
2. Espera a que diga «GPS: ✓» y pulsa **● Iniciar grabación**. Apunta al camino con el celular fijo en vertical.
3. Pulsa **■ Detener y analizar**. La app guarda el video (sin audio, ≈ 720p) y la ruta GPS, y vuelve a la pantalla principal con la fecha de inicio exacta y el GPX ya cargados.
4. Elige las opciones (tramo, guardar en el servidor…) y pulsa **Analizar**. Cada daño queda ubicado en el mapa.

Detalles:
- Duración máxima: 15 minutos (≈ 340 MB; el servidor admite hasta 500 MB).
- Si sales de la pantalla mientras grabas, la grabación se detiene y se conserva.
- Sin señal GPS el video se graba igual, pero los daños no tendrán ubicación.
- Los archivos temporales se borran solos a los 2 días.
- Esta pantalla no analiza en vivo: el análisis se hace al terminar, en el PC.

## Límites y avisos

- **PC encendido y misma red.** Sin eso la app no analiza.
- **Sin cifrado:** la conexión es HTTP en red local. La clave y las fotos viajan sin cifrar por el wifi; úsalo solo en una red de confianza. Sin `APP_TOKEN`, cualquiera en esa red que conozca la dirección puede usar el servidor.
- Un solo análisis de video a la vez en el servidor.
- El video grande tarda en subir por wifi; el límite es `MAX_VIDEO_MB` (ver `.env`).
- Las limitaciones del modelo siguen iguales: puede dar falsas alarmas y omitir daños; el índice es una medida propia, no PCI/IRI.
- Si la IP del PC cambia (router), actualiza la dirección con ⚙. Conviene reservar una IP fija para el PC en el router.

## Problemas frecuentes

| Síntoma | Causa probable |
|---|---|
| «No se pudo conectar» | Servidor apagado, no arrancó con `--host 0.0.0.0`, IP incorrecta, otro wifi, o firewall |
| `/health` no abre en el navegador del celular | Firewall de Windows o aislamiento de clientes del wifi |
| «Acceso no autorizado» | Falta o está mal la clave (`APP_TOKEN`); cámbiala con ⚙ |
| El video marcado no se reproduce en la página | Guárdalo con «Guardar video marcado» y ábrelo con el reproductor del celular |
| Sync de Gradle falla | Sin internet, o versión de Android Studio muy antigua (pide AGP 8.5; actualiza Android Studio) |
