from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..db import get_db
from ..inference import ModelNotAvailable, detector
from ..modelos import registro
from ..models import Captura, Deteccion, Tramo, Video
from .common import to_out

router = APIRouter(prefix="/api", tags=["panel"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {"db": db_ok, "modelo_cargado": detector.loaded, "modelo_version": detector.version}


def _ficha(m) -> dict:
    d = m.detector
    return {
        "id": m.id, "nombre": m.nombre, "etiqueta": m.etiqueta, "descripcion": m.descripcion,
        "predeterminado": m.id == registro.predeterminado().id,
        "disponible": m.archivo.exists(), "cargado": d.loaded,
        "metricas": m.metricas,
        "perfiles": {"normal": {"conf": settings.perfil_normal.conf},
                     "sensible": {"conf": m.perfil_sensible.conf, "conf_clase": m.perfil_sensible.conf_clase}},
    }


@router.get("/modelos")
def modelos():
    """Modelos que el usuario puede elegir, con sus cifras medidas y si el archivo .pt está disponible."""
    return {"predeterminado": registro.predeterminado().id, "modelos": [_ficha(m) for m in registro.lista()]}


@router.post("/modelos/{id_}/cargar")
def cargar_modelo(id_: str):
    """Precarga el modelo en memoria (para que el primer análisis no espere)."""
    from ..services import resolver_modelo
    m = resolver_modelo(id_)
    try:
        m.detector.load()
    except ModelNotAvailable as e:
        raise HTTPException(503, str(e))
    return _ficha(m)


@router.get("/config")
def config():
    """Límites y perfiles visibles para la interfaz (no incluye datos sensibles)."""
    return {
        "foto_mb": settings.max_upload_mb, "video_mb": settings.max_video_mb,
        "video_max_frames": settings.video_max_frames, "video_max_frames_cap": settings.video_max_frames_cap,
        "ms_por_imagen": detector.ms_tipico,   # medido en este equipo al arrancar (gris 1280x720, perfil normal)
        "perfiles": {
            "normal": {"conf": settings.perfil_normal.conf, "conf_clase": settings.perfil_normal.conf_clase},
            "sensible": {"conf": settings.perfil_sensible.conf, "conf_clase": settings.perfil_sensible.conf_clase},
        },
        "modelo_predeterminado": registro.predeterminado().id,
        "modelos": {m.id: {"normal": {"conf": settings.perfil_normal.conf, "conf_clase": settings.perfil_normal.conf_clase},
                           "sensible": {"conf": m.perfil_sensible.conf, "conf_clase": m.perfil_sensible.conf_clase}}
                    for m in registro.lista()},
    }


@router.get("/resumen")
def resumen(db: Session = Depends(get_db)):
    n_tramos = db.scalar(select(func.count()).select_from(Tramo)) or 0
    n_caps = db.scalar(select(func.count()).select_from(Captura)) or 0
    n_videos = db.scalar(select(func.count()).select_from(Video)) or 0
    n_dets = db.scalar(select(func.count()).select_from(Deteccion)) or 0
    medio = db.scalar(select(func.avg(Captura.indice_severidad)))
    por_clase = dict(db.execute(select(Deteccion.clase, func.count()).group_by(Deteccion.clase)).all())
    por_calif = dict(db.execute(select(Captura.calificacion, func.count()).group_by(Captura.calificacion)).all())
    recientes = db.scalars(
        select(Captura).options(selectinload(Captura.detecciones), selectinload(Captura.tramo))
        .order_by(Captura.creado_en.desc(), Captura.id.desc()).limit(8)
    ).all()
    con_gps = db.scalars(
        select(Captura).options(selectinload(Captura.tramo), selectinload(Captura.detecciones))
        .where(Captura.lat.is_not(None)).order_by(Captura.fecha_captura.desc()).limit(500)
    ).all()
    return {
        "tramos": n_tramos, "capturas": n_caps, "videos": n_videos, "detecciones": n_dets,
        "indice_medio": round(medio, 1) if medio is not None else None,
        "por_clase": por_clase, "por_calificacion": por_calif,
        "recientes": [to_out(c) for c in recientes],
        "marcadores": [
            {"id": c.id, "lat": c.lat, "lon": c.lon, "indice": c.indice_severidad,
             "calificacion": c.calificacion, "tramo": c.tramo.nombre,
             "fecha": c.fecha_captura, "url": f"/media/{c.ruta_anotada}"}
            for c in con_gps
        ],
    }
