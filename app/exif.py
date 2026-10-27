"""Lectura de fecha y GPS desde los metadatos EXIF (si existen)."""
from datetime import datetime
from zoneinfo import ZoneInfo

from PIL import Image

from .config import settings

_GPS_IFD = 0x8825
_EXIF_IFD = 0x8769
_DATETIME_ORIGINAL = 0x9003
_DATETIME = 0x0132


def _to_degrees(value, ref) -> float | None:
    try:
        d, m, s = (float(x) for x in value)
        deg = d + m / 60.0 + s / 3600.0
        if str(ref).upper() in ("S", "W"):
            deg = -deg
        return deg
    except Exception:
        return None


def read_exif(img: Image.Image) -> tuple[datetime | None, tuple[float, float] | None]:
    """Devuelve (fecha con zona horaria o None, (lat, lon) o None)."""
    fecha = None
    gps = None
    try:
        exif = img.getexif()
        raw = None
        try:
            raw = exif.get_ifd(_EXIF_IFD).get(_DATETIME_ORIGINAL)
        except Exception:
            pass
        raw = raw or exif.get(_DATETIME)
        if raw:
            fecha = datetime.strptime(str(raw).strip(), "%Y:%m:%d %H:%M:%S").replace(
                tzinfo=ZoneInfo(settings.timezone)
            )
        g = exif.get_ifd(_GPS_IFD)
        if g:
            lat = _to_degrees(g.get(2), g.get(1))
            lon = _to_degrees(g.get(4), g.get(3))
            if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
                if not (lat == 0 and lon == 0):
                    gps = (lat, lon)
    except Exception:
        pass
    return fecha, gps
