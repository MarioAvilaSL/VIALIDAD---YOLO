import shutil
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from ..config import STORAGE, settings
from ..db import get_db
from ..models import Captura, Tramo, Video
from ..schemas import TramoIn, TramoOut
from .common import borrar_archivos, to_out

router = APIRouter(prefix="/api/tramos", tags=["tramos"])
TZ = ZoneInfo(settings.timezone)


def _tramo_out(db: Session, t: Tramo) -> dict:
    n = db.scalar(select(func.count()).select_from(Captura).where(Captura.tramo_id == t.id)) or 0
    nv = db.scalar(select(func.count()).select_from(Video).where(Video.tramo_id == t.id)) or 0
    ult = db.scalars(
        select(Captura).where(Captura.tramo_id == t.id).order_by(Captura.fecha_captura.desc()).limit(1)
    ).first()
    return {
        "id": t.id, "nombre": t.nombre, "descripcion": t.descripcion, "ciudad": t.ciudad,
        "lat": t.lat, "lon": t.lon, "creado_en": t.creado_en, "n_capturas": n, "n_videos": nv,
        "ultimo_indice": ult.indice_severidad if ult else None,
        "ultima_calificacion": ult.calificacion if ult else None,
        "ultima_fecha": ult.fecha_captura if ult else None,
    }


@router.get("", response_model=list[TramoOut])
def listar(db: Session = Depends(get_db)):
    return [_tramo_out(db, t) for t in db.scalars(select(Tramo).order_by(Tramo.nombre))]


@router.post("", response_model=TramoOut, status_code=201)
def crear(data: TramoIn, db: Session = Depends(get_db)):
    t = Tramo(**data.model_dump())
    t.nombre = t.nombre.strip()
    db.add(t)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Ya existe un tramo con ese nombre.")
    db.refresh(t)
    return _tramo_out(db, t)


@router.delete("/{tramo_id}", status_code=204)
def eliminar(tramo_id: int, db: Session = Depends(get_db)):
    t = db.get(Tramo, tramo_id)
    if not t:
        raise HTTPException(404, "Tramo no encontrado.")
    for c in db.scalars(select(Captura).where(Captura.tramo_id == tramo_id)):
        borrar_archivos(c)
    for v in db.scalars(select(Video).where(Video.tramo_id == tramo_id)):
        shutil.rmtree(STORAGE / "videos" / str(v.id), ignore_errors=True)
    db.delete(t)
    db.commit()


@router.get("/{tramo_id}/seguimiento")
def seguimiento(tramo_id: int, db: Session = Depends(get_db)):
    t = db.get(Tramo, tramo_id)
    if not t:
        raise HTTPException(404, "Tramo no encontrado.")
    caps = db.scalars(
        select(Captura).where(Captura.tramo_id == tramo_id)
        .options(selectinload(Captura.detecciones), selectinload(Captura.tramo))
        .order_by(Captura.fecha_captura)
    ).all()

    # Una observación por día (promedio de las fotos de ese día).
    por_dia: dict[str, list[Captura]] = {}
    for c in caps:
        por_dia.setdefault(c.fecha_captura.astimezone(TZ).date().isoformat(), []).append(c)
    puntos = []
    for dia, lst in por_dia.items():
        idx = sum(c.indice_severidad for c in lst) / len(lst)
        puntos.append({
            "fecha": dia, "indice": round(idx, 2), "n_capturas": len(lst),
            "n_detecciones": sum(c.n_detecciones for c in lst),
        })

    vids = db.scalars(select(Video).where(Video.tramo_id == tramo_id).order_by(Video.fecha_inicio)).all()
    perfiles = sorted({c.perfil for c in caps})
    return {
        "tramo": _tramo_out(db, t),
        "perfiles": perfiles,
        "videos": [{"id": v.id, "fecha": v.fecha_inicio.astimezone(TZ).date().isoformat(),
                    "fecha_inicio": v.fecha_inicio, "indice_medio": v.indice_medio, "indice_max": v.indice_max,
                    "pct_afectados": v.pct_afectados, "calificacion": v.calificacion, "perfil": v.perfil,
                    "n_frames": v.n_frames, "duracion_s": v.duracion_s, "archivo": v.archivo_original} for v in vids],
        "puntos": puntos,
        "tendencia": _tendencia(puntos),
        "capturas": [to_out(c) for c in caps],
    }


def _tendencia(puntos: list[dict]) -> dict:
    n = len(puntos)
    if n < 3:
        return {"disponible": False, "n_fechas": n,
                "mensaje": f"Se necesitan al menos 3 fechas distintas para estimar una tendencia (hay {n})."}
    t0 = datetime.fromisoformat(puntos[0]["fecha"])
    xs = [(datetime.fromisoformat(p["fecha"]) - t0).days for p in puntos]
    ys = [p["indice"] for p in puntos]
    span = xs[-1]
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return {"disponible": False, "n_fechas": n, "mensaje": "Las fechas no son distintas."}
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    pend = sxy / sxx
    syy = sum((y - my) ** 2 for y in ys)
    r2 = (sxy * sxy) / (sxx * syy) if syy > 0 else 0.0
    p30 = pend * 30
    aviso = " Periodo corto (<14 días): interpretar con cautela." if span < 14 else ""
    if r2 < 0.25:  # la recta explica poco de la variación: no afirmar una dirección
        return {
            "disponible": True, "n_fechas": n, "dias": span, "pendiente_30d": round(p30, 2),
            "r2": round(r2, 3), "sentido": "incierta",
            "mensaje": (f"Sin tendencia clara: los índices varían sin un patrón sostenido "
                        f"(R²={r2:.2f}, {n} fechas). Pueden influir el encuadre, la luz o el clima.{aviso}"),
        }
    if abs(p30) < 2:
        sentido = "estable"
    else:
        sentido = "empeorando" if p30 > 0 else "mejorando"
    return {
        "disponible": True, "n_fechas": n, "dias": span,
        "pendiente_30d": round(p30, 2), "r2": round(r2, 3), "sentido": sentido,
        "mensaje": (f"Tendencia lineal indicativa: {p30:+.1f} puntos de índice por 30 días "
                    f"({sentido}; R²={r2:.2f}, {n} fechas).{aviso}"),
    }
