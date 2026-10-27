import shutil
from collections import Counter

from ..config import STORAGE
from ..models import Captura


def to_out(c: Captura, with_dets: bool = False) -> dict:
    conteo = dict(Counter(d.clase for d in c.detecciones))
    out = {
        "id": c.id,
        "tramo_id": c.tramo_id,
        "tramo_nombre": c.tramo.nombre,
        "archivo_original": c.archivo_original,
        "url_imagen": f"/media/{c.ruta_imagen}",
        "url_anotada": f"/media/{c.ruta_anotada}",
        "ancho": c.ancho,
        "alto": c.alto,
        "fecha_captura": c.fecha_captura,
        "origen_fecha": c.origen_fecha,
        "lat": c.lat,
        "lon": c.lon,
        "origen_gps": c.origen_gps,
        "notas": c.notas,
        "modelo_version": c.modelo_version,
        "conf_umbral": c.conf_umbral,
        "perfil": c.perfil,
        "parametros": c.parametros,
        "indice_severidad": c.indice_severidad,
        "calificacion": c.calificacion,
        "n_detecciones": c.n_detecciones,
        "tiempo_inferencia_ms": c.tiempo_inferencia_ms,
        "conteo": conteo,
    }
    if with_dets:
        out["detecciones"] = c.detecciones
    return out


def borrar_archivos(c: Captura) -> None:
    for rel in (c.ruta_imagen, c.ruta_anotada):
        p = (STORAGE / rel).resolve()
        if STORAGE.resolve() in p.parents and p.exists():
            p.unlink(missing_ok=True)


def borrar_carpeta_vacia(rel_dir: str) -> None:
    p = (STORAGE / rel_dir).resolve()
    if STORAGE.resolve() in p.parents and p.is_dir():
        shutil.rmtree(p, ignore_errors=True)
