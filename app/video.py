"""Análisis de video. Dos modos:

* ``fotogramas``: se analiza 1 fotograma cada ``intervalo_s`` segundos (rápido); no se genera video.
* ``anotado``: se analiza 1 de cada ``cada_n`` fotogramas y se escribe un video H.264 con las cajas dibujadas.
  En los fotogramas intermedios se repiten las cajas del último análisis (aproximadas si la cámara se mueve).
"""
import io
import math
import subprocess
import tempfile
import time
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import severity
from .config import settings
from .gpx import Ruta
from .inference import detector, draw
from .tracking import Hallazgo, Tracker

UMBRAL_AFECTADO = severity.BANDS[0][0]  # un fotograma cuenta como "afectado" si su índice supera "Bueno"
COLOR_CAL = {"Bueno": (22, 163, 74), "Regular": (202, 138, 4), "Malo": (234, 88, 12), "Muy malo": (220, 38, 38)}


class VideoError(Exception):
    pass


class Cancelado(Exception):
    pass


@dataclass
class Muestra:
    t: float
    indice: float
    n: int
    conteo: dict[str, int]
    lat: float | None = None
    lon: float | None = None


@dataclass
class Resultado:
    meta: dict
    muestras: list[Muestra]
    mejores: list[tuple[Muestra, bytes]] = field(default_factory=list)  # (muestra, JPEG anotado)
    salida: Path | None = None                                          # video anotado (modo anotado)
    hallazgos: list[Hallazgo] = field(default_factory=list)             # daños distintos estimados (modo anotado)
    hallazgos_truncado: bool = False
    ruta: list[list[float]] | None = None                               # recorrido GPS (si se subió un GPX)


def _jpeg(img: Image.Image, q: int = 85) -> bytes:
    b = io.BytesIO()
    img.save(b, "JPEG", quality=q)
    return b.getvalue()


class EscritorH264:
    """Escribe fotogramas RGB a un .mp4 H.264 (reproducible en el navegador) usando el ffmpeg de imageio-ffmpeg."""

    def __init__(self, ruta: Path, ancho: int, alto: int, fps: float):
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as e:  # noqa: BLE001
            raise VideoError("No se encontró ffmpeg (paquete imageio-ffmpeg). Ejecuta: pip install imageio-ffmpeg") from e
        self.ruta = ruta
        self._err = tempfile.TemporaryFile()
        cmd = [exe, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{ancho}x{alto}",
               "-r", f"{fps:.4f}", "-i", "-", "-an", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", str(settings.video_crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(ruta)]
        self._p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=self._err)

    def escribir(self, rgb: np.ndarray) -> None:
        try:
            self._p.stdin.write(rgb.tobytes())
        except (BrokenPipeError, OSError):
            raise VideoError("ffmpeg dejó de responder: " + self._mensaje_error())

    def _mensaje_error(self) -> str:
        try:
            self._err.seek(0)
            return self._err.read().decode(errors="replace").strip()[-400:] or "sin detalle"
        except Exception:  # noqa: BLE001
            return "sin detalle"

    def cerrar(self) -> None:
        try:
            self._p.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        rc = self._p.wait()
        if rc != 0:
            raise VideoError("No se pudo crear el video anotado: " + self._mensaje_error())
        self._err.close()

    def abortar(self) -> None:
        try:
            self._p.kill()
            self._p.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass
        try:
            self._err.close()
        except Exception:  # noqa: BLE001
            pass
        self.ruta.unlink(missing_ok=True)


def _fuente(px: int):
    try:
        return ImageFont.load_default(size=px)
    except TypeError:
        return ImageFont.load_default()


def _hud(img: Image.Image, indice: float, t: float) -> None:
    """Rótulo con el índice del último análisis (arriba a la izquierda)."""
    calif = severity.calificar(indice)
    d = ImageDraw.Draw(img)
    f = _fuente(max(14, img.width // 45))
    txt = f"Índice {indice:5.1f} · {calif} · {int(t // 60)}:{int(t % 60):02d}"
    l, tp, r, b = d.textbbox((0, 0), txt, font=f)
    pad = 6
    d.rectangle([0, 0, r - l + 2 * pad, b - tp + 2 * pad], fill=COLOR_CAL[calif])
    d.text((pad - l, pad - tp), txt, fill=(255, 255, 255), font=f)


def _ajustar(frame_bgr: np.ndarray) -> Image.Image:
    """BGR -> PIL RGB con lado mayor <= video_max_side y dimensiones pares (H.264 yuv420p lo exige)."""
    h, w = frame_bgr.shape[:2]
    k = min(1.0, settings.video_max_side / max(h, w))
    nw, nh = max(2, int(round(w * k))), max(2, int(round(h * k)))
    nw -= nw % 2
    nh -= nh % 2
    if (nw, nh) != (w, h):
        frame_bgr = cv2.resize(frame_bgr, (nw, nh), interpolation=cv2.INTER_AREA)
    return Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))


def analizar_video(path: Path, nombre_perfil: str, *, modo: str = "fotogramas", intervalo_s: float = 1.0,
                   cada_n: int = 1, max_frames: int | None = None, salida: Path | None = None,
                   on_progress=None, cancelado=None, gps: Ruta | None = None,
                   inicio_utc: datetime | None = None, desfase_s: float = 0.0) -> Resultado:
    max_frames = max(1, min(max_frames or settings.video_max_frames, settings.video_max_frames_cap))
    anotado = modo == "anotado"
    if anotado and salida is None:
        raise VideoError("Falta la ruta de salida del video anotado.")
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise VideoError("No se pudo abrir el video (formato o códec no soportado). Prueba con MP4 (H.264).")
    escritor = None
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        fps_asumido = not (fps and math.isfinite(fps) and 1 <= fps <= 240)
        if fps_asumido:
            fps = 30.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total < 0 or total > 50_000_000:
            total = 0

        pedido = intervalo_s
        step = max(1, int(cada_n)) if anotado else max(1, round(fps * intervalo_s))
        paso_pedido = step
        if total and math.ceil(total / step) > max_frames:
            step = math.ceil(total / max_frames)       # se amplía el paso para respetar el límite
        efectivo = step / fps
        perfil = settings.perfil(nombre_perfil)
        detector.load()

        muestras: list[Muestra] = []
        tracker = Tracker(min_hits=2 if step <= 5 else 1) if anotado else None
        candidatos: list[tuple[Muestra, bytes]] = []
        cota = settings.video_top_frames * 3
        ancho = alto = 0
        ultimas: list = []            # detecciones del último análisis (se repiten en los fotogramas intermedios)
        ult_indice, ult_t = 0.0, 0.0
        t0 = time.perf_counter()
        idx = 0
        while True:
            if anotado:
                ok, frame = cap.read()
                if not ok:
                    break
            else:
                if not cap.grab():
                    break
                frame = None
            analizar = idx % step == 0
            if analizar:
                if cancelado and cancelado():
                    raise Cancelado()
                if frame is None:
                    ok, frame = cap.retrieve()
            if frame is not None and (analizar or anotado):
                img = _ajustar(frame)
                if not ancho:
                    ancho, alto = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or img.width), (int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or img.height)
                    if anotado:
                        escritor = EscritorH264(salida, img.width, img.height, fps)
                if analizar:
                    dets, _ = detector.predict(img, perfil)
                    indice, _ = severity.calcular((d.clase, d.area_frac) for d in dets)
                    conteo: dict[str, int] = {}
                    for d in dets:
                        conteo[d.clase] = conteo.get(d.clase, 0) + 1
                    m = Muestra(round(idx / fps, 2), indice, len(dets), conteo)
                    muestras.append(m)
                    if tracker:
                        tracker.update(len(muestras) - 1, m.t, dets, img)
                    ultimas, ult_indice, ult_t = dets, indice, m.t
                if anotado:
                    vista = draw(img, ultimas)
                    _hud(vista, ult_indice, idx / fps)
                    escritor.escribir(np.asarray(vista))
                    if analizar and indice > 0 and (len(candidatos) < cota or indice > min(c[0].indice for c in candidatos)):
                        candidatos.append((m, _jpeg(vista)))
                        if len(candidatos) > cota:
                            candidatos.remove(min(candidatos, key=lambda c: c[0].indice))
                elif analizar and indice > 0 and (len(candidatos) < cota or indice > min(c[0].indice for c in candidatos)):
                    candidatos.append((m, _jpeg(draw(img, dets))))
                    if len(candidatos) > cota:
                        candidatos.remove(min(candidatos, key=lambda c: c[0].indice))
                if analizar and on_progress:
                    on_progress(len(muestras), math.ceil(total / step) if total else 0)
                if analizar and not total and len(muestras) >= max_frames:
                    idx += 1
                    break
            idx += 1
        if escritor:
            escritor.cerrar()
            escritor = None
    except BaseException:
        if escritor:
            escritor.abortar()
        elif salida:
            Path(salida).unlink(missing_ok=True)
        raise
    finally:
        cap.release()

    if not muestras:
        if salida:
            Path(salida).unlink(missing_ok=True)
        raise VideoError("No se pudo leer ningún fotograma del video.")

    indices = [m.indice for m in muestras]
    medio = round(sum(indices) / len(indices), 2)
    duracion = round(total / fps, 2) if total else round(idx / fps, 2)
    meta = {
        "modo": modo, "duracion_s": duracion, "fps": round(fps, 2), "fps_asumido": fps_asumido, "ancho": ancho, "alto": alto,
        "intervalo_pedido_s": pedido, "intervalo_s": round(efectivo, 3), "n_frames": len(muestras),
        "cada_n": step if anotado else None, "cada_n_pedido": paso_pedido if anotado else None,
        "max_frames": max_frames, "limite_aplicado": bool(total and step > paso_pedido),
        "indice_medio": medio, "indice_max": max(indices),
        "pct_afectados": round(100.0 * sum(1 for i in indices if i >= UMBRAL_AFECTADO) / len(indices), 1),
        "calificacion": severity.calificar(medio),
        "tiempo_proceso_s": round(time.perf_counter() - t0, 1),
        "perfil": nombre_perfil, "conf_umbral": perfil.conf,
    }

    elegidos: list[tuple[Muestra, bytes]] = []
    for m, jpg in sorted(candidatos, key=lambda c: -c[0].indice):
        if all(abs(m.t - e[0].t) >= 2 * efectivo for e in elegidos):
            elegidos.append((m, jpg))
        if len(elegidos) >= settings.video_top_frames:
            break
    elegidos.sort(key=lambda c: c[0].t)
    hallazgos, truncado = tracker.resultado() if tracker else ([], False)
    ruta = None
    if gps and inicio_utc:
        def pos(t):
            return gps.posicion(inicio_utc + timedelta(seconds=t + desfase_s))
        for m, _ in elegidos:
            p = pos(m.t)
            m.lat, m.lon = p if p else (None, None)
        for h in hallazgos:
            p = pos((h.t_ini + h.t_fin) / 2)
            h.lat, h.lon = p if p else (None, None)
        ini = inicio_utc + timedelta(seconds=desfase_s)
        ruta = gps.tramo(ini, ini + timedelta(seconds=duracion)) or None
        meta["gps_cubre_pct"] = round(100.0 * sum(1 for m in muestras if pos(m.t)) / len(muestras), 1)
    if tracker:
        meta["n_hallazgos"] = len(hallazgos)
    return Resultado(meta, muestras, elegidos, Path(salida) if anotado else None, hallazgos, truncado, ruta)
