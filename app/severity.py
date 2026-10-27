"""Índice de severidad (0-100) basado en reglas.

IMPORTANTE: es una HEURÍSTICA propia del proyecto, no un estándar de ingeniería vial
(como PCI/IRI) ni una medición validada. Los pesos y K son parámetros para calibrar
con criterio experto y datos reales. Sirve para comparar fotos de un mismo tramo
tomadas de forma similar; no para comparar entre cámaras o encuadres distintos.
"""
import math
from collections.abc import Iterable

# Peso de cada clase según su gravedad relativa (criterio del proyecto).
WEIGHTS: dict[str, float] = {
    "pothole": 1.0,
    "alligator_crack": 0.7,
    "transverse_crack": 0.4,
    "longitudinal_crack": 0.3,
}
K = 4.0  # saturación: a mayor K, el índice sube más rápido con el área dañada

BANDS = [(15.0, "Bueno"), (35.0, "Regular"), (60.0, "Malo")]
LAST_BAND = "Muy malo"


def calificar(indice: float) -> str:
    for limite, nombre in BANDS:
        if indice < limite:
            return nombre
    return LAST_BAND


def calcular(detecciones: Iterable[tuple[str, float]]) -> tuple[float, str]:
    """detecciones: pares (clase, area_frac). Devuelve (índice, calificación)."""
    daño = sum(WEIGHTS.get(clase, 0.5) * area for clase, area in detecciones)
    indice = 100.0 * (1.0 - math.exp(-K * daño))
    indice = round(indice, 2)
    return indice, calificar(indice)
