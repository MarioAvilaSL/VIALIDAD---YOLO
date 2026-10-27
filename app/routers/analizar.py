"""Modo «solo analizar»: procesa una foto y devuelve el resultado SIN guardar nada
(ni en la base de datos ni en disco)."""
from fastapi import APIRouter, File, Form, UploadFile

from ..config import settings
from ..inference import detector, draw
from ..services import Sensibilidad, abrir_imagen, analizar_imagen, data_url, leer_subida, parametros_json
from collections import Counter

router = APIRouter(prefix="/api", tags=["analizar"])


@router.post("/analizar")
def analizar(file: UploadFile = File(...), sensibilidad: Sensibilidad = Form("normal")):
    img, f_exif, gps = abrir_imagen(leer_subida(file, settings.max_upload_mb))
    dets, ms, indice, calif, perfil = analizar_imagen(img, sensibilidad)
    return {
        "guardado": False,
        "archivo": (file.filename or "imagen")[-255:],
        "ancho": img.width, "alto": img.height,
        "indice_severidad": indice, "calificacion": calif,
        "n_detecciones": len(dets), "conteo": dict(Counter(d.clase for d in dets)),
        "detecciones": [
            {"clase": d.clase, "confianza": round(d.confianza, 4), "x1": d.x1, "y1": d.y1,
             "x2": d.x2, "y2": d.y2, "area_frac": d.area_frac} for d in dets
        ],
        "imagen_anotada": data_url(draw(img, dets), 88),
        "imagen_original": data_url(img, 85),
        "tiempo_inferencia_ms": round(ms, 1),
        "perfil": sensibilidad, "conf_umbral": perfil.conf,
        "parametros": parametros_json(sensibilidad, perfil),
        "modelo_version": detector.version,
        "fecha_exif": f_exif.isoformat() if f_exif else None,
        "gps_exif": {"lat": gps[0], "lon": gps[1]} if gps else None,
    }
