"""Catálogo de modelos que el usuario puede elegir (YOLO26s, YOLO26n y YOLO26m).

Todas las cifras de `metricas` son MEDIDAS (no estimadas) y provienen de los cuadernos de entrenamiento y
comparación del proyecto (carpeta entrenamiento/):
  * mAP50-95 y recall medio del perfil sensible: validación y test de RDD2022 (no carreteras de Ecuador);
    los umbrales de cada modelo se eligieron solo con validación.
  * ms por imagen en CPU: rango de 3 corridas de medir_velocidad_cpu.py (27 imágenes, 640 px) en el computador del
    autor (Windows 11, 12 núcleos lógicos). En otro equipo serán otras cifras.
Si cambias un modelo o recalibras sus umbrales, actualiza estas cifras o bórralas: no las inventes.
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

from .config import Perfil, settings
from .inference import Detector, detector as _detector_s


@dataclass
class Modelo:
    id: str
    nombre: str
    etiqueta: str
    resumen: str
    archivo_cfg: Path
    perfil_sensible: Perfil
    metricas: dict
    detector: Detector = field(repr=False, default=None)

    def perfil(self, nombre: str) -> Perfil:
        """Perfil de inferencia: «normal» es común (0,25); «sensible» es propio de cada modelo."""
        return self.perfil_sensible if nombre == "sensible" else settings.perfil_normal

    @property
    def archivo(self) -> Path:
        return self.detector.archivo()

    @property
    def descripcion(self) -> str:
        m = self.metricas
        return (f"{self.resumen} Medido en RDD2022 (no en carreteras de Ecuador): mAP50-95 {_n(m['map_val'])} en validación "
                f"y {_n(m['map_test'])} en test; en el computador del autor tardó {m['ms_cpu'][0]} a {m['ms_cpu'][1]} ms por imagen.")


def _n(x: float) -> str:
    return f"{x:.3f}".replace(".", ",")


class ModeloDesconocido(KeyError):
    pass


class Registro:
    def __init__(self) -> None:
        # El detector de YOLO26s es el global de siempre (inference.detector): así nada existente cambia.
        self._modelos: dict[str, Modelo] = {}
        self._modelos["yolo26s"] = Modelo(
            id="yolo26s", nombre="YOLO26s", etiqueta="Equilibrado (recomendado)",
            resumen="Modelo predeterminado: equilibrio entre precisión y velocidad.",
            archivo_cfg=settings.model_path, perfil_sensible=settings.perfil_sensible,
            metricas=dict(map_val=0.337, map_test=0.353, recall_sens_val=0.684, recall_sens_test=0.695,
                          ms_cpu=[108, 120], peso_mb=20.3),
            detector=_detector_s)
        self._modelos["yolo26n"] = Modelo(
            id="yolo26n", nombre="YOLO26n", etiqueta="Rápido",
            resumen="Unas 2 veces más rápido que el equilibrado, a cambio de detectar algo menos (pierde más en baches).",
            archivo_cfg=settings.model_path_yolo26n, perfil_sensible=settings.perfil_sensible_yolo26n,
            metricas=dict(map_val=0.322, map_test=0.346, recall_sens_val=0.657, recall_sens_test=0.666,
                          ms_cpu=[58, 71], peso_mb=5.5),
            detector=Detector(path=settings.resolved(settings.model_path_yolo26n), id="yolo26n"))
        self._modelos["yolo26m"] = Modelo(
            id="yolo26m", nombre="YOLO26m", etiqueta="Más preciso",
            resumen="Mejora pequeña frente al equilibrado y unas 2 veces más lento.",
            archivo_cfg=settings.model_path_yolo26m, perfil_sensible=settings.perfil_sensible_yolo26m,
            metricas=dict(map_val=0.341, map_test=0.362, recall_sens_val=0.698, recall_sens_test=0.714,
                          ms_cpu=[239, 281], peso_mb=44.0),
            detector=Detector(path=settings.resolved(settings.model_path_yolo26m), id="yolo26m"))

    # ---- consultas
    def ids_habilitados(self) -> list[str]:
        pedidos = [x.strip() for x in settings.modelos_habilitados.split(",") if x.strip()]
        ids = [i for i in self._modelos if i in pedidos]
        return ids or ["yolo26s"]

    def lista(self) -> list[Modelo]:
        return [self._modelos[i] for i in self.ids_habilitados()]

    def predeterminado(self) -> Modelo:
        i = settings.modelo_predeterminado
        return self._modelos[i] if i in self.ids_habilitados() else self._modelos[self.ids_habilitados()[0]]

    def obtener(self, id_: str | None) -> Modelo:
        """Modelo por id (None = el predeterminado). Lanza ModeloDesconocido si no existe o está deshabilitado."""
        if not id_:
            return self.predeterminado()
        if id_ not in self.ids_habilitados():
            raise ModeloDesconocido(id_)
        return self._modelos[id_]

    def por_version(self, version: str | None) -> Modelo | None:
        """Identifica el modelo a partir de la versión guardada con cada resultado («archivo.pt@huella»)."""
        if not version:
            return None
        archivo = version.split("@", 1)[0]
        for m in self._modelos.values():
            if m.archivo.name == archivo:
                return m
        return None

    def nombre_por_version(self, version: str | None, parametros: str | None = None) -> str | None:
        """Nombre legible del modelo de un resultado guardado: primero por `modelo_id` de los parámetros, luego por archivo."""
        m = None
        if parametros:
            try:
                m = self._modelos.get(json.loads(parametros).get("modelo_id"))
            except (ValueError, AttributeError):
                m = None
        m = m or self.por_version(version)
        return f"{m.nombre} ({m.etiqueta})" if m else None


registro = Registro()
