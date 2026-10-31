import json
import shutil
from typing import Literal
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.responses import FileResponse
from pydantic import BaseModel
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import jobs
from ..config import STORAGE, settings
from ..db import SessionLocal, get_db
from ..inference import detector
from ..gpx import GpxError, leer_gpx
from ..models import Tramo, Video, VideoFrame, VideoHallazgo
from ..services import Sensibilidad, parametros_json, parse_fecha
from ..video import analizar_video

router = APIRouter(prefix="/api/videos", tags=["videos"])
TZ = ZoneInfo(settings.timezone)
EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
TMP = STORAGE / "tmp"
META_BD = ("duracion_s", "fps", "ancho", "alto", "intervalo_s", "n_frames", "indice_medio", "indice_max",
           "pct_afectados", "calificacion", "tiempo_proceso_s", "perfil")
Modo = Literal["fotogramas", "anotado"]


def limpiar_tmp() -> None:
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.mkdir(parents=True, exist_ok=True)


def _guardar_subida(file: UploadFile, ext: str) -> Path:
    TMP.mkdir(parents=True, exist_ok=True)
    destino = TMP / f"{uuid.uuid4().hex}{ext}"
    limite = settings.max_video_mb * 1024 * 1024
    n = 0
    try:
        with open(destino, "wb") as f:
            while chunk := file.file.read(1 << 20):
                n += len(chunk)
                if n > limite:
                    raise HTTPException(413, f"El video supera {settings.max_video_mb} MB.")
                f.write(chunk)
        if n == 0:
            raise HTTPException(400, "Archivo vacío.")
    except BaseException:
        destino.unlink(missing_ok=True)
        raise
    return destino


def _resultado_vivo(res, archivo: str, guardado: bool, video_id: int | None, imagenes: list[str],
                    video_url: str | None = None, hallazgos: list[dict] | None = None) -> dict:
    return {
        "guardado": guardado, "video_id": video_id, "video_url": video_url,
        "hallazgos": hallazgos or [], "hallazgos_truncado": res.hallazgos_truncado, "ruta": res.ruta,
        "resumen": {**res.meta, "archivo": archivo, "modelo_version": detector.version},
        "serie": [{"t": m.t, "indice": m.indice, "n": m.n, "conteo": m.conteo} for m in res.muestras],
        "mejores": [{"t": m.t, "indice": m.indice, "conteo": m.conteo, "imagen": img, "lat": m.lat, "lon": m.lon}
                    for (m, _), img in zip(res.mejores, imagenes)],
    }


@router.post("", status_code=202)
def analizar(
    file: UploadFile = File(...),
    gpx: UploadFile | None = File(None),
    desfase_s: float = Form(0.0, ge=-3600, le=3600),
    sensibilidad: Sensibilidad = Form("normal"),
    modo: Modo = Form("fotogramas"),
    intervalo_s: float = Form(1.0, ge=0.2, le=30),
    cada_n: int = Form(3, ge=1, le=60),
    max_frames: int = Form(None),
    guardar: bool = Form(False),
    tramo_id: int | None = Form(None),
    fecha_inicio: str | None = Form(None),
    notas: str | None = Form(None, max_length=2000),
    db: Session = Depends(get_db),
):
    nombre = (file.filename or "video")[-255:]
    ext = Path(nombre).suffix.lower()
    if ext not in EXTS:
        raise HTTPException(415, f"Formato no soportado. Usa: {', '.join(sorted(EXTS))}.")
    if guardar:
        if tramo_id is None:
            raise HTTPException(422, "Para guardar en el seguimiento indica el tramo.")
        if not db.get(Tramo, tramo_id):
            raise HTTPException(404, "Tramo no encontrado.")
    if max_frames is None:
        max_frames = settings.video_max_frames
    if not 1 <= max_frames <= settings.video_max_frames_cap:
        raise HTTPException(422, f"El límite de fotogramas debe estar entre 1 y {settings.video_max_frames_cap}.")
    inicio = parse_fecha(fecha_inicio) if fecha_inicio else None
    if inicio is None:
        inicio_ahora = datetime.now(TZ)
    gps = None
    if gpx is not None and gpx.filename:
        if inicio is None:
            raise HTTPException(422, "Con un GPX indica la fecha y hora de inicio del video para sincronizarlo.")
        try:
            gps = leer_gpx(gpx.file.read(15 * 1024 * 1024 + 1))
        except GpxError as e:
            raise HTTPException(422, str(e))
        if inicio.tzinfo is None:
            inicio = inicio.replace(tzinfo=TZ)
        inicio_utc = inicio.astimezone(timezone.utc)
        if not (gps.inicio.timestamp() - 7200 < inicio_utc.timestamp() < gps.fin.timestamp() + 7200):
            raise HTTPException(422, f"La hora de inicio del video no coincide con el GPX (el GPX va de {gps.inicio.astimezone(TZ):%d/%m/%Y %H:%M} a {gps.fin.astimezone(TZ):%H:%M}, hora local). Revisa la fecha/hora.")
    else:
        inicio_utc = None
    ruta = _guardar_subida(file, ext)

    def trabajo(job: jobs.Job) -> dict:
        salida = TMP / f"{uuid.uuid4().hex}_anotado.mp4" if modo == "anotado" else None
        job.salida = salida
        try:
            def prog(h, t):
                job.hechos, job.total = h, t
            res = analizar_video(ruta, sensibilidad, modo=modo, intervalo_s=intervalo_s, cada_n=cada_n,
                                 max_frames=max_frames, salida=salida, on_progress=prog, cancelado=job.cancelar.is_set,
                                 gps=gps, inicio_utc=inicio_utc, desfase_s=desfase_s)
        finally:
            ruta.unlink(missing_ok=True)  # el video original nunca se conserva
        if not guardar:
            url = f"/api/videos/jobs/{job.id}/video" if salida else None
            hall = []
            for k, h in enumerate(res.hallazgos):
                job.adjuntos[f"h{k}"] = h.jpg
                hall.append(_hall_dict(h, k, f"/api/videos/jobs/{job.id}/hallazgo/{k}.jpg", False))
            return _resultado_vivo(res, nombre, False, None, [data_url_bytes(j) for _, j in res.mejores], url, hall)
        return _persistir(res, nombre, tramo_id, inicio or inicio_ahora, "manual" if inicio else "subida",
                          sensibilidad, notas, job)

    job = jobs.lanzar(trabajo)
    return {"job_id": job.id}


def _hall_dict(h, id_, imagen: str, descartado: bool) -> dict:
    return {"id": id_, "clase": h.clase, "t_ini": h.t_ini, "t_fin": h.t_fin, "n_apariciones": h.n_apariciones,
            "conf_max": h.conf_max, "area_max": h.area_max, "imagen": imagen, "lat": h.lat, "lon": h.lon,
            "descartado": descartado}


def data_url_bytes(jpg: bytes) -> str:
    import base64
    return "data:image/jpeg;base64," + base64.b64encode(jpg).decode()


def _persistir(res, archivo, tramo_id, inicio, origen, sensibilidad, notas, job=None) -> dict:
    m = res.meta
    perfil = settings.perfil(sensibilidad)
    db = SessionLocal()
    carpeta = None
    try:
        v = Video(
            tramo_id=tramo_id, archivo_original=archivo, fecha_inicio=inicio, origen_fecha=origen,
            duracion_s=m["duracion_s"], fps=m["fps"], ancho=m["ancho"], alto=m["alto"],
            intervalo_s=m["intervalo_s"], n_frames=m["n_frames"], indice_medio=m["indice_medio"],
            indice_max=m["indice_max"], pct_afectados=m["pct_afectados"], calificacion=m["calificacion"],
            perfil=sensibilidad, parametros=parametros_json(sensibilidad, perfil), modelo_version=detector.version,
            tiempo_proceso_s=m["tiempo_proceso_s"], notas=(notas or None),
            modo=m["modo"], cada_n=m.get("cada_n"),
            ruta_gps=json.dumps(res.ruta) if res.ruta else None,
        )
        db.add(v)
        db.flush()
        carpeta = STORAGE / "videos" / str(v.id)
        carpeta.mkdir(parents=True, exist_ok=True)
        rutas: dict[float, str] = {}
        for k, (mu, jpg) in enumerate(res.mejores):
            rel = f"videos/{v.id}/f_{k:02d}.jpg"
            (STORAGE / rel).write_bytes(jpg)
            rutas[mu.t] = rel
        lat_lon = {mu.t: (mu.lat, mu.lon) for mu, _ in res.mejores}
        hall_rows = []
        for k, h in enumerate(res.hallazgos):
            rel = f"videos/{v.id}/h_{k:03d}.jpg"
            (STORAGE / rel).write_bytes(h.jpg)
            hall_rows.append(VideoHallazgo(video_id=v.id, clase=h.clase, t_ini=h.t_ini, t_fin=h.t_fin,
                                           n_apariciones=h.n_apariciones, conf_max=h.conf_max, area_max=h.area_max,
                                           ruta_imagen=rel, lat=h.lat, lon=h.lon))
        db.add_all(hall_rows)
        if res.salida and res.salida.exists():
            shutil.move(str(res.salida), str(carpeta / "anotado.mp4"))
            v.ruta_anotado = f"videos/{v.id}/anotado.mp4"
            if job:
                job.salida = None
        db.add_all(VideoFrame(video_id=v.id, t_seg=mu.t, indice=mu.indice, n_detecciones=mu.n,
                              conteo=json.dumps(mu.conteo), ruta_imagen=rutas.get(mu.t),
                              lat=lat_lon.get(mu.t, (None, None))[0], lon=lat_lon.get(mu.t, (None, None))[1])
                      for mu in res.muestras)
        db.commit()
        db.flush()
        vid, ruta_anot = v.id, v.ruta_anotado
        hall = [_hall_dict(h, r.id, f"/media/{r.ruta_imagen}", False) for h, r in zip(res.hallazgos, hall_rows)]
    except Exception:
        db.rollback()
        if carpeta:
            shutil.rmtree(carpeta, ignore_errors=True)
        raise
    finally:
        db.close()
    return _resultado_vivo(res, archivo, True, vid, [f"/media/{rutas[mu.t]}" for mu, _ in res.mejores],
                          f"/media/{ruta_anot}" if ruta_anot else None, hall)


@router.get("/jobs/{job_id}")
def estado(job_id: str):
    j = jobs.obtener(job_id)
    if not j:
        raise HTTPException(404, "Trabajo no encontrado (el servidor pudo haberse reiniciado).")
    return j.publico()


@router.get("/jobs/{job_id}/video")
def video_temporal(job_id: str):
    j = jobs.obtener(job_id)
    if not j or not j.salida or not j.salida.exists():
        raise HTTPException(404, "El video anotado ya no está disponible.")
    return FileResponse(j.salida, media_type="video/mp4", filename="anotado.mp4")


@router.get("/jobs/{job_id}/hallazgo/{k}.jpg")
def hallazgo_temporal(job_id: str, k: int):
    from fastapi.responses import Response
    j = jobs.obtener(job_id)
    jpg = j.adjuntos.get(f"h{k}") if j else None
    if not jpg:
        raise HTTPException(404, "Imagen no disponible.")
    return Response(jpg, media_type="image/jpeg")


@router.delete("/jobs/{job_id}", status_code=204)
def cancelar(job_id: str):
    j = jobs.obtener(job_id)
    if not j:
        raise HTTPException(404, "Trabajo no encontrado.")
    j.cancelar.set()
    jobs.descartar(j)


def video_resumen(v: Video) -> dict:
    return {
        "id": v.id, "tramo_id": v.tramo_id, "tramo_nombre": v.tramo.nombre, "archivo": v.archivo_original,
        "fecha_inicio": v.fecha_inicio.astimezone(TZ) if v.fecha_inicio else None, "origen_fecha": v.origen_fecha, "duracion_s": v.duracion_s, "fps": v.fps,.duracion_s, "fps": v.fps,
        "ancho": v.ancho, "alto": v.alto, "intervalo_s": v.intervalo_s, "n_frames": v.n_frames,
        "indice_medio": v.indice_medio, "indice_max": v.indice_max, "pct_afectados": v.pct_afectados,
        "calificacion": v.calificacion, "perfil": v.perfil, "modelo_version": v.modelo_version,
        "tiempo_proceso_s": v.tiempo_proceso_s, "notas": v.notas,
        "modo": v.modo, "cada_n": v.cada_n,
        "video_url": f"/media/{v.ruta_anotado}" if v.ruta_anotado else None,
    }


@router.get("")
def listar(tramo_id: int | None = None, limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    q = select(Video).options(selectinload(Video.tramo))
    if tramo_id is not None:
        q = q.where(Video.tramo_id == tramo_id)
    return [video_resumen(v) for v in db.scalars(q.order_by(Video.fecha_inicio.desc()).limit(limit))]


@router.get("/{video_id}")
def detalle(video_id: int, db: Session = Depends(get_db)):
    v = db.scalars(select(Video).where(Video.id == video_id)
                   .options(selectinload(Video.tramo), selectinload(Video.frames))).first()
    if not v:
        raise HTTPException(404, "Video no encontrado.")
    return {
        "guardado": True, "video_id": v.id, "video_url": f"/media/{v.ruta_anotado}" if v.ruta_anotado else None,
        "resumen": {**video_resumen(v), "parametros": v.parametros},
        "serie": [{"t": f.t_seg, "indice": f.indice, "n": f.n_detecciones, "conteo": json.loads(f.conteo)}
                  for f in v.frames],
        "mejores": [{"t": f.t_seg, "indice": f.indice, "conteo": json.loads(f.conteo),
                     "imagen": f"/media/{f.ruta_imagen}", "lat": f.lat, "lon": f.lon} for f in v.frames if f.ruta_imagen],
        "hallazgos": [{"id": h.id, "clase": h.clase, "t_ini": h.t_ini, "t_fin": h.t_fin, "n_apariciones": h.n_apariciones,
                       "conf_max": h.conf_max, "area_max": h.area_max, "imagen": f"/media/{h.ruta_imagen}",
                       "lat": h.lat, "lon": h.lon, "descartado": h.descartado} for h in v.hallazgos],
        "hallazgos_truncado": False,
        "ruta": json.loads(v.ruta_gps) if v.ruta_gps else None,
    }


class Descarte(BaseModel):
    descartado: bool


@router.patch("/{video_id}/hallazgos/{hallazgo_id}")
def descartar(video_id: int, hallazgo_id: int, body: Descarte, db: Session = Depends(get_db)):
    h = db.get(VideoHallazgo, hallazgo_id)
    if not h or h.video_id != video_id:
        raise HTTPException(404, "Hallazgo no encontrado.")
    h.descartado = body.descartado
    db.commit()
    return {"id": h.id, "descartado": h.descartado}


@router.delete("/{video_id}", status_code=204)
def eliminar(video_id: int, db: Session = Depends(get_db)):
    v = db.get(Video, video_id)
    if not v:
        raise HTTPException(404, "Video no encontrado.")
    shutil.rmtree(STORAGE / "videos" / str(video_id), ignore_errors=True)
    db.delete(v)
    db.commit()
