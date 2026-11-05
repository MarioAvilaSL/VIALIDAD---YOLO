#!/usr/bin/env python3
"""Mide cuánto tarda cada modelo por imagen en la CPU de ESTE computador.

Uso (desde la carpeta del proyecto, con el entorno virtual activado):

    python entrenamiento/yolo26m/medir_velocidad_cpu.py ^
        --modelos models/best.pt models/best_yolo26m.pt ^
        --imagenes ruta/a/una/carpeta/con/fotos ^
        --n 60

(En PowerShell la continuación de línea es el acento grave `, o pon todo en una línea.)

Qué mide: el tiempo de `model.predict()` por imagen (lectura del archivo + preprocesado + inferencia +
postprocesado), con umbral 0.25 y 640 px, que es lo que hace la app con el perfil normal.
No mide el tiempo de red, ni de la base de datos, ni de dibujar el video anotado.

Cómo se hace justo: mismas imágenes y mismas condiciones para todos los modelos, calentamiento descartado y
varias rondas alternando el orden de los modelos (para que el calor o la carga del equipo no favorezcan a uno).
Cierra otros programas pesados mientras mides. Los números dependen de TU equipo: no son transferibles a otro.
"""
import argparse
import csv
import hashlib
import os
import platform
import statistics
import sys
import time
from pathlib import Path

EXT = {".jpg", ".jpeg", ".png"}


def sha8(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()[:8]


def percentil(xs, q):
    xs = sorted(xs)
    k = (len(xs) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modelos", nargs="+", required=True, help="rutas a los .pt (2 o más)")
    ap.add_argument("--imagenes", required=True, help="carpeta con fotos (.jpg/.png)")
    ap.add_argument("--n", type=int, default=60, help="cuántas imágenes usar (las primeras por orden de nombre)")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--calentamiento", type=int, default=5, help="pasadas descartadas antes de medir")
    ap.add_argument("--rondas", type=int, default=2, help="veces que se recorren las imágenes por modelo")
    ap.add_argument("--hilos", type=int, default=0, help="hilos de torch (0 = dejar el valor por defecto)")
    ap.add_argument("--salida", default="velocidad_cpu.csv", help="archivo CSV de resultados")
    a = ap.parse_args()

    carpeta = Path(a.imagenes)
    if not carpeta.is_dir():
        sys.exit(f"No existe la carpeta de imágenes: {carpeta}")
    imgs = sorted(p for p in carpeta.iterdir() if p.suffix.lower() in EXT)[: a.n]
    if len(imgs) < 5:
        sys.exit(f"Encontré solo {len(imgs)} imágenes en {carpeta}; usa al menos 5 (ideal 50 o más).")
    rutas_m = [Path(m) for m in a.modelos]
    for m in rutas_m:
        if not m.is_file():
            sys.exit(f"No existe el modelo: {m}")

    import torch
    import ultralytics
    from ultralytics import YOLO

    if a.hilos > 0:
        torch.set_num_threads(a.hilos)

    print("=" * 70)
    print("Equipo:", platform.platform())
    print("CPU:", platform.processor() or "(no informa)", "| núcleos lógicos:", os.cpu_count(),
          "| hilos de torch:", torch.get_num_threads())
    print("Python", platform.python_version(), "| torch", torch.__version__, "| ultralytics", ultralytics.__version__)
    print(f"Imágenes: {len(imgs)} de {carpeta} | imgsz {a.imgsz} | conf {a.conf} | rondas {a.rondas}")
    for m in rutas_m:
        print(f"  {m.name}: {m.stat().st_size / 1e6:.1f} MB | SHA-256 {sha8(m)}…")
    print("=" * 70)

    modelos = {}
    for m in rutas_m:
        modelos[str(m)] = YOLO(str(m))

    def una(modelo, ruta):
        t0 = time.perf_counter()
        r = modelo.predict(source=str(ruta), imgsz=a.imgsz, conf=a.conf, device="cpu", verbose=False)[0]
        return (time.perf_counter() - t0) * 1000, r.speed

    for nombre, mod in modelos.items():
        for _ in range(a.calentamiento):
            una(mod, imgs[0])

    tot = {n: [] for n in modelos}
    comp = {n: {"preprocess": [], "inference": [], "postprocess": []} for n in modelos}
    for ronda in range(a.rondas):
        orden = list(modelos) if ronda % 2 == 0 else list(reversed(list(modelos)))
        for nombre in orden:
            for ruta in imgs:
                ms, sp = una(modelos[nombre], ruta)
                tot[nombre].append(ms)
                for k in comp[nombre]:
                    comp[nombre][k].append(sp[k])
        print(f"ronda {ronda + 1}/{a.rondas} lista")

    filas = []
    base = None
    print("\nRESULTADOS (ms por imagen, en esta CPU)")
    print(f"{'modelo':28s} {'media':>8s} {'mediana':>8s} {'p95':>8s} {'img/s':>7s} {'infer.':>8s}  vs 1.º")
    for nombre in modelos:
        xs = tot[nombre]
        med = statistics.mean(xs)
        if base is None:
            base = med
        fila = dict(
            modelo=Path(nombre).name, n_mediciones=len(xs), media_ms=round(med, 1),
            mediana_ms=round(statistics.median(xs), 1), p95_ms=round(percentil(xs, 0.95), 1),
            imagenes_por_s=round(1000 / med, 2),
            preproceso_ms=round(statistics.mean(comp[nombre]["preprocess"]), 1),
            inferencia_ms=round(statistics.mean(comp[nombre]["inference"]), 1),
            postproceso_ms=round(statistics.mean(comp[nombre]["postprocess"]), 1),
            veces_vs_primero=round(med / base, 2),
        )
        filas.append(fila)
        print(f"{fila['modelo']:28s} {fila['media_ms']:8.1f} {fila['mediana_ms']:8.1f} {fila['p95_ms']:8.1f} "
              f"{fila['imagenes_por_s']:7.2f} {fila['inferencia_ms']:8.1f}  x{fila['veces_vs_primero']:.2f}")

    with open(a.salida, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0]))
        w.writeheader()
        w.writerows(filas)
    print(f"\nGuardado en {a.salida}")
    print("Nota: el análisis en vivo envía ~1 fotograma por segundo; si la media de un modelo se acerca a 1000 ms "
          "(o la supera), ese modelo no podrá seguir el ritmo en este equipo.")


if __name__ == "__main__":
    main()
