"""Funciones compartidas por fotos, «solo analizar» y video."""
import base64
import io
import json
from typing import Literal

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps

from . import severity
from .config import Perfil, settings
from .exif import read_exif
from .inference import ModelNotAvailable, detector, draw

Sensibilidad = Literal["normal", "sensible"]
ALLOWED = {"JPEG", "PNG", "WEBP"}
Image.MAX_IMAGE_PIXELS = settings.max_pixels


def leer_subida(file: UploadFile, limite_mb: int) -> bytes:
    limite = limite_mb * 1024 * 1024
    buf = bytearray()
    while chunk := file.file.read(1 << 20):
        buf += chunk
        if len(buf) > limite:
            raise HTTPException(413, f"El archivo supera {limite_mb} MB.")
    if not buf:
        raise HTTPException(400, "Archivo vacío.")
    return bytes(buf)


def abrir_imagen(data: bytes):
    """Valida que sea una imagen real y devuelve (imagen RGB orientada, fecha EXIF, GPS EXIF)."""
    try:
        probe = Image.open(io.BytesIO(data))
        fmt = probe.format
        probe.verify()
        if fmt not in ALLOWED:
            raise HTTPException(415, "Formato no soportado. Usa JPG, PNG o WEBP.")
        img = Image.open(io.BytesIO(data))
        fecha, gps = read_exif(img)
        img = ImageOps.exif_transpose(img).convert("RGB")
    except HTTPException:
        raise
    except Exception:  # UnidentifiedImageError, DecompressionBombError, OSError, ImportError (parche de ultralytics)...
        raise HTTPException(400, "El archivo no es una imagen válida o es demasiado grande.")
    return img, fecha, gps


def parse_fecha(s: str):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        raise HTTPException(422, "Fecha inválida (usa formato AAAA-MM-DDTHH:MM).")
    return d if d.tzinfo else d.replace(tzinfo=ZoneInfo(settings.timezone))


def parametros_json(nombre: str, perfil: Perfil) -> str:
    return json.dumps({
        "perfil": nombre, "conf": perfil.conf, "conf_clase": perfil.conf_clase,
        "imgsz": perfil.imgsz, "augment": perfil.augment, "modelo": detector.version,
    }, ensure_ascii=False)


def analizar_imagen(img: Image.Image, nombre_perfil: str):
    """Corre el detector con el perfil y calcula el índice. Devuelve (dets, ms, indice, calif, perfil)."""
    perfil = settings.perfil(nombre_perfil)
    try:
        dets, ms = detector.predict(img, perfil)
    except ModelNotAvailable as e:
        raise HTTPException(503, str(e))
    indice, calif = severity.calcular((d.clase, d.area_frac) for d in dets)
    return dets, ms, indice, calif, perfil


def data_url(img: Image.Image, calidad: int = 85, lado_max: int | None = None) -> str:
    if lado_max and max(img.size) > lado_max:
        img = img.copy()
        img.thumbnail((lado_max, lado_max))
    b = io.BytesIO()
    img.save(b, "JPEG", quality=calidad)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


__all__ = ["parse_fecha", "leer_subida", "abrir_imagen", "parametros_json", "analizar_imagen", "data_url", "draw", "Sensibilidad"]
