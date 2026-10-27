"""Seguimiento sencillo de daños entre fotogramas analizados (modo «video anotado»).

Une detecciones de la MISMA clase entre análisis consecutivos para estimar cuántos daños distintos hay,
en vez de contar el mismo bache una vez por fotograma. Es una heurística (IoU + desplazamiento previsto):
puede unir dos daños cercanos o partir uno en dos si la cámara se mueve mucho entre análisis. Por eso el
resultado se presenta como CONTEO ESTIMADO y cada hallazgo se puede descartar a mano.
"""
import io
import math
from dataclasses import dataclass, field

from PIL import Image, ImageDraw

from .inference import COLORS, Det

MAX_HALLAZGOS = 400


def _iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / u if u > 0 else 0.0


@dataclass
class _Track:
    id: int
    clase: str
    box: list[float]
    vel: tuple[float, float] = (0.0, 0.0)
    k_ult: int = 0
    t_ini: float = 0.0
    t_fin: float = 0.0
    hits: int = 1
    conf_max: float = 0.0
    area_max: float = 0.0
    score: float = -1.0
    crop: Image.Image | None = None

    def previsto(self, k: int) -> list[float]:
        g = k - self.k_ult
        dx, dy = self.vel[0] * g, self.vel[1] * g
        b = self.box
        return [b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy]


@dataclass
class Hallazgo:
    clase: str
    t_ini: float
    t_fin: float
    n_apariciones: int
    conf_max: float
    area_max: float
    jpg: bytes
    lat: float | None = None
    lon: float | None = None


def _recorte(img: Image.Image, d: Det, lado_max: int = 360) -> Image.Image:
    w, h = img.size
    bw, bh = d.x2 - d.x1, d.y2 - d.y1
    mx, my = max(bw * 0.6, 40), max(bh * 0.6, 40)
    x1, y1 = max(0, int(d.x1 - mx)), max(0, int(d.y1 - my))
    x2, y2 = min(w, int(d.x2 + mx)), min(h, int(d.y2 + my))
    c = img.crop((x1, y1, x2, y2)).convert("RGB")
    ImageDraw.Draw(c).rectangle([d.x1 - x1, d.y1 - y1, d.x2 - x1, d.y2 - y1],
                                outline=COLORS.get(d.clase, (255, 0, 0)), width=max(2, c.width // 90))
    k = lado_max / max(c.size)
    if k < 1:
        c = c.resize((max(1, int(c.width * k)), max(1, int(c.height * k))), Image.BILINEAR)
    return c


class Tracker:
    def __init__(self, min_hits: int = 2, max_gap: int = 2, iou_min: float = 0.15, dist_frac: float = 0.8):
        self.min_hits, self.max_gap, self.iou_min, self.dist_frac = min_hits, max_gap, iou_min, dist_frac
        self._tracks: list[_Track] = []
        self._n = 0

    def _afinidad(self, tr: _Track, d: Det, k: int) -> float:
        p = tr.previsto(k)
        box = (d.x1, d.y1, d.x2, d.y2)
        iou = max(_iou(p, box), _iou(tr.box, box))
        if iou >= self.iou_min:
            return 1.0 + iou
        # respaldo: centros cercanos respecto al tamaño del daño
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        px, py = (p[0] + p[2]) / 2, (p[1] + p[3]) / 2
        tam = max(box[2] - box[0], box[3] - box[1], p[2] - p[0], p[3] - p[1], 1.0)
        dist = math.hypot(cx - px, cy - py) / tam
        return (1.0 - dist / self.dist_frac) if dist < self.dist_frac else -1.0

    def update(self, k: int, t: float, dets: list[Det], img: Image.Image) -> None:
        vivos = [tr for tr in self._tracks if k - tr.k_ult <= self.max_gap + 1]
        pares = []
        for i, d in enumerate(dets):
            for j, tr in enumerate(vivos):
                if tr.clase == d.clase:
                    a = self._afinidad(tr, d, k)
                    if a > 0:
                        pares.append((a, i, j))
        usados_d, usados_t = set(), set()
        for a, i, j in sorted(pares, reverse=True):
            if i in usados_d or j in usados_t:
                continue
            usados_d.add(i); usados_t.add(j)
            self._actualizar(vivos[j], dets[i], k, t, img)
        for i, d in enumerate(dets):
            if i not in usados_d:
                self._n += 1
                tr = _Track(self._n, d.clase, [d.x1, d.y1, d.x2, d.y2], k_ult=k, t_ini=t, t_fin=t)
                self._tracks.append(tr)
                self._actualizar(tr, d, k, t, img, nuevo=True)

    def _actualizar(self, tr: _Track, d: Det, k: int, t: float, img: Image.Image, nuevo: bool = False) -> None:
        nb = [d.x1, d.y1, d.x2, d.y2]
        if not nuevo:
            g = max(1, k - tr.k_ult)
            tr.vel = ((nb[0] - tr.box[0]) / g, (nb[1] - tr.box[1]) / g)
            tr.hits += 1
        tr.box, tr.k_ult, tr.t_fin = nb, k, t
        tr.conf_max = max(tr.conf_max, d.confianza)
        tr.area_max = max(tr.area_max, d.area_frac)
        score = d.confianza * math.sqrt(max(d.area_frac, 1e-6))
        if score > tr.score:
            tr.score, tr.crop = score, _recorte(img, d)

    def resultado(self) -> tuple[list[Hallazgo], bool]:
        validos = [tr for tr in self._tracks if tr.hits >= self.min_hits and tr.crop is not None]
        truncado = len(validos) > MAX_HALLAZGOS
        if truncado:
            validos = sorted(validos, key=lambda tr: -tr.score)[:MAX_HALLAZGOS]
        out = []
        for tr in sorted(validos, key=lambda tr: tr.t_ini):
            b = io.BytesIO()
            tr.crop.save(b, "JPEG", quality=85)
            out.append(Hallazgo(tr.clase, round(tr.t_ini, 2), round(tr.t_fin, 2), tr.hits,
                                round(tr.conf_max, 3), round(tr.area_max, 4), b.getvalue()))
        return out, truncado
