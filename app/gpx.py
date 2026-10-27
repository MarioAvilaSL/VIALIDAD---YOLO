"""Lectura de rutas GPX (opcional) para ubicar en el mapa los daños de un video."""
import bisect
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

MAX_BYTES = 15 * 1024 * 1024


class GpxError(ValueError):
    pass


def _t(txt: str) -> datetime:
    d = datetime.fromisoformat(txt.strip().replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


class Ruta:
    def __init__(self, pts: list[tuple[datetime, float, float]]):
        self.pts = sorted(pts)
        self._ts = [p[0].timestamp() for p in self.pts]

    @property
    def inicio(self) -> datetime:
        return self.pts[0][0]

    @property
    def fin(self) -> datetime:
        return self.pts[-1][0]

    def posicion(self, t: datetime, tolerancia_s: float = 5.0) -> tuple[float, float] | None:
        x = t.timestamp()
        if x < self._ts[0] - tolerancia_s or x > self._ts[-1] + tolerancia_s:
            return None
        i = bisect.bisect_left(self._ts, x)
        if i <= 0:
            return self.pts[0][1], self.pts[0][2]
        if i >= len(self.pts):
            return self.pts[-1][1], self.pts[-1][2]
        (t0, la0, lo0), (t1, la1, lo1) = self.pts[i - 1], self.pts[i]
        dt = self._ts[i] - self._ts[i - 1]
        f = 0.0 if dt <= 0 else (x - self._ts[i - 1]) / dt
        if dt > 30:  # hueco largo en el GPS: no se interpola, se usa el punto más cercano
            return (la0, lo0) if f < 0.5 else (la1, lo1)
        return round(la0 + (la1 - la0) * f, 6), round(lo0 + (lo1 - lo0) * f, 6)

    def tramo(self, desde: datetime, hasta: datetime, max_puntos: int = 500) -> list[list[float]]:
        a, b = desde.timestamp(), hasta.timestamp()
        sel = [[round(p[1], 6), round(p[2], 6)] for p, x in zip(self.pts, self._ts) if a - 5 <= x <= b + 5]
        if len(sel) > max_puntos:
            paso = len(sel) / max_puntos
            sel = [sel[int(i * paso)] for i in range(max_puntos)]
        return sel


def leer_gpx(data: bytes) -> Ruta:
    if len(data) > MAX_BYTES:
        raise GpxError("El archivo GPX es demasiado grande.")
    if b"<!DOCTYPE" in data[:4096].upper() or b"<!ENTITY" in data.upper():
        raise GpxError("GPX no válido.")
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise GpxError("No se pudo leer el GPX (XML inválido).")
    pts = []
    for el in root.iter():
        if el.tag.split("}")[-1] != "trkpt":
            continue
        tm = next((c for c in el if c.tag.split("}")[-1] == "time"), None)
        try:
            pts.append((_t(tm.text), float(el.get("lat")), float(el.get("lon"))))
        except (AttributeError, TypeError, ValueError):
            continue
    if len(pts) < 2:
        raise GpxError("El GPX no trae puntos de ruta con hora (trkpt/time).")
    return Ruta(pts)
