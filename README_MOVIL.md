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

El análisis móvil es de tipo «solo analizar»: **no guarda nada en la base de datos** ni usa tramos/GPX. Para eso sigue la versión web de PC.

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
