from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TramoIn(BaseModel):
    nombre: str = Field(min_length=2, max_length=120)
    descripcion: str | None = Field(None, max_length=2000)
    ciudad: str | None = Field(None, max_length=80)
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=180)


class TramoOut(TramoIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    creado_en: datetime
    n_capturas: int = 0
    n_videos: int = 0
    ultimo_indice: float | None = None
    ultima_calificacion: str | None = None
    ultima_fecha: datetime | None = None


class DeteccionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    clase: str
    confianza: float
    x1: float
    y1: float
    x2: float
    y2: float
    area_frac: float


class CapturaOut(BaseModel):
    id: int
    tramo_id: int
    tramo_nombre: str
    archivo_original: str
    url_imagen: str
    url_anotada: str
    ancho: int
    alto: int
    fecha_captura: datetime
    origen_fecha: str
    lat: float | None
    lon: float | None
    origen_gps: str | None
    notas: str | None
    modelo_version: str
    conf_umbral: float
    perfil: str = "normal"
    parametros: str | None = None
    indice_severidad: float
    calificacion: str
    n_detecciones: int
    tiempo_inferencia_ms: float
    conteo: dict[str, int]
    detecciones: list[DeteccionOut] | None = None
