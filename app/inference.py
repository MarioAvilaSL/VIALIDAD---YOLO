"""Detector YOLO26: carga única, inferencia en CPU y dibujo de las cajas."""
import hashlib
import threading
import time
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from .config import MODEL_FILE, Perfil, settings

# Colores por clase (también se usan en la interfaz web).
COLORS = {
    "pothole": (220, 38, 38),
    "alligator_crack": (234, 88, 12),
    "transverse_crack": (37, 99, 235),
    "longitudinal_crack": (13, 148, 136),
}
LABELS_ES = {
    "pothole": "Bache / daño mayor",
    "alligator_crack": "Piel de cocodrilo",
    "transverse_crack": "Grieta transversal",
    "longitudinal_crack": "Grieta longitudinal",
}


@dataclass
class Det:
    clase: str
    confianza: float
    x1: float
    y1: float
    x2: float
    y2: float
    area_frac: float


class ModelNotAvailable(RuntimeError):
    pass


class Detector:
    def __init__(self) -> None:
        self._model = None
        self._lock = threading.Lock()  # una inferencia a la vez (CPU)
        self.version = "sin-cargar"
        self.ms_tipico: float | None = None  # mediana medida al arrancar (solo orientativa)

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        if self._model is not None:
            return
        with self._lock:
            if self._model is not None:
                return
            if not MODEL_FILE.exists():
                raise ModelNotAvailable(f"No existe el modelo en {MODEL_FILE}. Copia best.pt en la carpeta models/.")
            from ultralytics import YOLO  # import tardío: acelera el arranque de las pruebas

            h = hashlib.sha256()
            with open(MODEL_FILE, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            self._model = YOLO(str(MODEL_FILE))
            # Calentamiento: la primera inferencia es lenta; así no la paga el primer usuario.
            blanco = Image.new("RGB", (1280, 720), (120, 120, 120))
            kw = dict(imgsz=640, conf=0.25, augment=False, device=settings.device, verbose=False)
            self._model.predict(blanco, **kw)
            tiempos = []
            for _ in range(3):
                t0 = time.perf_counter()
                self._model.predict(blanco, **kw)
                tiempos.append((time.perf_counter() - t0) * 1000.0)
            self.ms_tipico = round(sorted(tiempos)[1], 0)
            self.version = f"{MODEL_FILE.name}@{h.hexdigest()[:12]}"

    def predict(self, img: Image.Image, perfil: Perfil | None = None) -> tuple[list[Det], float]:
        """Inferencia con el perfil dado. Siempre se pasan todos los parámetros explícitos
        (Ultralytics conserva estado entre llamadas) y nunca se cambia la cabeza del modelo."""
        self.load()
        perfil = perfil or settings.perfil_normal
        w, h = img.size
        with self._lock:
            t0 = time.perf_counter()
            res = self._model.predict(
                img, imgsz=perfil.imgsz, conf=perfil.conf_minimo(), augment=perfil.augment,
                device=settings.device, verbose=False,
            )[0]
            ms = (time.perf_counter() - t0) * 1000.0
        names = self._model.names
        dets: list[Det] = []
        for xyxy, c, k in zip(res.boxes.xyxy.tolist(), res.boxes.conf.tolist(), res.boxes.cls.tolist()):
            if float(c) < perfil.conf_para(names[int(k)]):
                continue  # umbral propio de la clase
            x1, y1, x2, y2 = (max(0.0, xyxy[0]), max(0.0, xyxy[1]), min(float(w), xyxy[2]), min(float(h), xyxy[3]))
            area = max(0.0, x2 - x1) * max(0.0, y2 - y1) / float(w * h)
            dets.append(Det(names[int(k)], float(c), x1, y1, x2, y2, area))
        dets.sort(key=lambda d: -d.confianza)
        return dets, ms


def draw(img: Image.Image, dets: list[Det]) -> Image.Image:
    out = img.copy().convert("RGB")
    d = ImageDraw.Draw(out)
    lw = max(2, round(max(out.size) / 400))
    try:
        font = ImageFont.load_default(size=max(12, round(max(out.size) / 55)))
    except TypeError:  # Pillow antiguo
        font = ImageFont.load_default()
    for det in dets:
        col = COLORS.get(det.clase, (255, 255, 0))
        d.rectangle([det.x1, det.y1, det.x2, det.y2], outline=col, width=lw)
        txt = f"{LABELS_ES.get(det.clase, det.clase)} {det.confianza:.2f}"
        l, t, r, b = d.textbbox((0, 0), txt, font=font)
        th = b - t + 6
        ty = det.y1 - th if det.y1 - th >= 0 else det.y1
        d.rectangle([det.x1, ty, det.x1 + (r - l) + 8, ty + th], fill=col)
        d.text((det.x1 + 4, ty + 2 - t), txt, fill=(255, 255, 255), font=font)
    return out


detector = Detector()
