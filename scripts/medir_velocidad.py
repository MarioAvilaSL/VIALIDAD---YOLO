"""Mide cuánto tarda el modelo EN TU COMPUTADOR con cada configuración de sensibilidad.

Uso (desde la carpeta del proyecto, con el entorno virtual activo):
    python scripts/medir_velocidad.py [ruta_a_una_foto.jpg] [repeticiones]

Si no das una foto, usa una imagen gris (el tiempo de inferencia casi no depende del contenido,
pero con una foto real es más fiel). Los números impresos son MEDIDOS en tu equipo; no los extrapoles
a otro computador ni a otra foto de distinto tamaño.
"""
import os
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("YOLO_AUTOINSTALL", "False")
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from PIL import Image  # noqa: E402

from app.config import MODEL_FILE, Perfil, settings  # noqa: E402
from app.inference import detector  # noqa: E402


def main() -> None:
    foto = sys.argv[1] if len(sys.argv) > 1 else None
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    if not MODEL_FILE.exists():
        raise SystemExit(f"No existe {MODEL_FILE}. Copia best.pt en la carpeta models/.")
    img = Image.open(foto).convert("RGB") if foto else Image.new("RGB", (1280, 720), (120, 120, 120))
    print(f"Imagen: {foto or 'gris sintética'} {img.size} | dispositivo: {settings.device} | repeticiones: {n}")
    t0 = time.perf_counter()
    detector.load()
    print(f"Carga del modelo + calentamiento: {time.perf_counter() - t0:.1f} s (solo ocurre al arrancar)\n")

    pruebas = [
        ("normal (perfil de la app)", settings.perfil_normal),
        ("sensible (perfil de la app)", settings.perfil_sensible),
        ("imgsz 800", Perfil(conf=0.25, imgsz=800)),
        ("imgsz 960", Perfil(conf=0.25, imgsz=960)),
        ("TTA 640", Perfil(conf=0.25, augment=True)),
    ]
    print(f"{'configuración':32s} {'mediana':>9s} {'mín':>8s} {'máx':>8s}   (ms por imagen)")
    for nombre, perfil in pruebas:
        detector.predict(img, perfil)  # una pasada previa, no se cuenta
        ms = []
        for _ in range(n):
            _, t = detector.predict(img, perfil)
            ms.append(t)
        print(f"{nombre:32s} {statistics.median(ms):9.0f} {min(ms):8.0f} {max(ms):8.0f}")
    print("\nPara video: tiempo aproximado = fotogramas analizados × mediana (más la lectura del video).")


if __name__ == "__main__":
    main()
