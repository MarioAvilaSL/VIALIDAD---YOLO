import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import STORAGE, settings
from ..db import get_db
from ..inference import detector, draw
from ..models import Captura, Deteccion, Tramo
from ..schemas import CapturaOut
from ..services import Sensibilidad, abrir_imagen, analizar_imagen, leer_subida, parametros_json, parse_fecha
from .common import borrar_archivos, to_out

router = APIRouter(prefix="/api/capturas", tags=["capturas"])
TZ = ZoneInfo(settings.timezone)
@router.post("", response_model=CapturaOut, status_code=201)
def crear(
    file: UploadFile = File(...),
    tramo_id: int = Form(...),
    fecha_captura: str | None = Form(None),
    lat: float | None = Form(None, ge=-90, le=90),
    lon: float | None = Form(None, ge=-180, le=180),
    notas: str | None = Form(None, max_length=2000),
    sensibilidad: Sensibilidad = Form("normal"),
    db: Session = Depends(get_db),
):
    if (lat is None) != (lon is None):
        raise HTTPException(422, "Indica latitud y longitud juntas.")
    tramo = db.get(Tramo, tramo_id)
    if not tramo:
        raise HTTPException(404, "Tramo no encontrado.")

    img, f_exif, gps_exif = abrir_imagen(leer_subida(file, settings.max_upload_mb))

    if fecha_captura:
        fecha, o_fecha = parse_fecha(fecha_captura), "manual"
    elif f_exif:
        fecha, o_fecha = f_exif, "exif"
    else:
        fecha, o_fecha = datetime.now(TZ), "subida"
    if lat is not None:
        o_gps = "manual"
    elif gps_exif:
        (lat, lon), o_gps = gps_exif, "exif"
    else:
        o_gps = None

    dets, ms, indice, calif, perfil = analizar_imagen(img, sensibilidad)

    # Archivos: nombres aleatorios (nunca el nombre original) en storage/capturas/AAAA-MM/
    sub = f"capturas/{fecha.astimezone(TZ):%Y-%m}"
    (STORAGE / sub).mkdir(parents=True, exist_ok=True)
    base = uuid.uuid4().hex
    rel_img, rel_det = f"{sub}/{base}.jpg", f"{sub}/{base}_det.jpg"
    img.save(STORAGE / rel_img, "JPEG", quality=92)
    draw(img, dets).save(STORAGE / rel_det, "JPEG", quality=90)

    nombre_orig = (file.filename or "imagen")[-255:]
    cap = Captura(
        tramo_id=tramo_id, archivo_original=nombre_orig, ruta_imagen=rel_img, ruta_anotada=rel_det,
        ancho=img.width, alto=img.height, fecha_captura=fecha, origen_fecha=o_fecha,
        lat=lat, lon=lon, origen_gps=o_gps, notas=(notas or None),
        modelo_version=detector.version, conf_umbral=perfil.conf,
        perfil=sensibilidad, parametros=parametros_json(sensibilidad, perfil),
        indice_severidad=indice, calificacion=calif, n_detecciones=len(dets),
        tiempo_inferencia_ms=round(ms, 1),
    )
    cap.detecciones = [
        Deteccion(clase=d.clase, confianza=round(d.confianza, 4), x1=d.x1, y1=d.y1, x2=d.x2, y2=d.y2,
                  area_frac=d.area_frac)
        for d in dets
    ]
    try:
        db.add(cap)
        db.commit()
    except Exception:
        db.rollback()
        for rel in (rel_img, rel_det):
            (STORAGE / rel).unlink(missing_ok=True)
        raise
    cap.tramo = tramo
    return to_out(cap, with_dets=True)


@router.get("", response_model=list[CapturaOut])
def listar(
    tramo_id: int | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    q = select(Captura).options(selectinload(Captura.detecciones), selectinload(Captura.tramo))
    if tramo_id is not None:
        q = q.where(Captura.tramo_id == tramo_id)
    q = q.order_by(Captura.fecha_captura.desc(), Captura.id.desc()).limit(limit).offset(offset)
    return [to_out(c) for c in db.scalars(q)]


@router.get("/{captura_id}", response_model=CapturaOut)
def detalle(captura_id: int, db: Session = Depends(get_db)):
    c = db.scalars(
        select(Captura).where(Captura.id == captura_id)
        .options(selectinload(Captura.detecciones), selectinload(Captura.tramo))
    ).first()
    if not c:
        raise HTTPException(404, "Captura no encontrada.")
    return to_out(c, with_dets=True)


@router.delete("/{captura_id}", status_code=204)
def eliminar(captura_id: int, db: Session = Depends(get_db)):
    c = db.get(Captura, captura_id)
    if not c:
        raise HTTPException(404, "Captura no encontrada.")
    borrar_archivos(c)
    db.delete(c)
    db.commit()
