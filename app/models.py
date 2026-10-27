from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Tramo(Base):
    """Un tramo de vía que se fotografía repetidamente (unidad de seguimiento)."""

    __tablename__ = "tramos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    descripcion: Mapped[str | None] = mapped_column(Text)
    ciudad: Mapped[str | None] = mapped_column(String(80))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    capturas: Mapped[list["Captura"]] = relationship(
        back_populates="tramo", cascade="all, delete-orphan", passive_deletes=True
    )


class Captura(Base):
    """Una foto analizada: archivo, fecha, GPS, versión del modelo y resultado."""

    __tablename__ = "capturas"
    __table_args__ = (Index("ix_capturas_tramo_fecha", "tramo_id", "fecha_captura"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tramo_id: Mapped[int] = mapped_column(ForeignKey("tramos.id", ondelete="CASCADE"))
    archivo_original: Mapped[str] = mapped_column(String(255))
    ruta_imagen: Mapped[str] = mapped_column(String(255))
    ruta_anotada: Mapped[str] = mapped_column(String(255))
    ancho: Mapped[int] = mapped_column(Integer)
    alto: Mapped[int] = mapped_column(Integer)
    fecha_captura: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    origen_fecha: Mapped[str] = mapped_column(String(10))  # manual | exif | subida
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    origen_gps: Mapped[str | None] = mapped_column(String(10))  # manual | exif
    notas: Mapped[str | None] = mapped_column(Text)
    modelo_version: Mapped[str] = mapped_column(String(80))
    conf_umbral: Mapped[float] = mapped_column(Float)
    perfil: Mapped[str] = mapped_column(String(10), default="normal", server_default="normal")
    parametros: Mapped[str | None] = mapped_column(Text)  # JSON con los parámetros de inferencia usados
    indice_severidad: Mapped[float] = mapped_column(Float)
    calificacion: Mapped[str] = mapped_column(String(12))
    n_detecciones: Mapped[int] = mapped_column(Integer)
    tiempo_inferencia_ms: Mapped[float] = mapped_column(Float)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tramo: Mapped[Tramo] = relationship(back_populates="capturas")
    detecciones: Mapped[list["Deteccion"]] = relationship(
        back_populates="captura", cascade="all, delete-orphan", passive_deletes=True,
        order_by="Deteccion.id",
    )


class Deteccion(Base):
    __tablename__ = "detecciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    captura_id: Mapped[int] = mapped_column(
        ForeignKey("capturas.id", ondelete="CASCADE"), index=True
    )
    clase: Mapped[str] = mapped_column(String(40))
    confianza: Mapped[float] = mapped_column(Float)
    x1: Mapped[float] = mapped_column(Float)
    y1: Mapped[float] = mapped_column(Float)
    x2: Mapped[float] = mapped_column(Float)
    y2: Mapped[float] = mapped_column(Float)
    area_frac: Mapped[float] = mapped_column(Float)  # área de la caja / área de la imagen

    captura: Mapped[Captura] = relationship(back_populates="detecciones")


class Video(Base):
    """Análisis de un video por muestreo de fotogramas. El archivo de video NO se conserva."""

    __tablename__ = "videos"
    __table_args__ = (Index("ix_videos_tramo_fecha", "tramo_id", "fecha_inicio"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tramo_id: Mapped[int] = mapped_column(ForeignKey("tramos.id", ondelete="CASCADE"))
    archivo_original: Mapped[str] = mapped_column(String(255))
    fecha_inicio: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    origen_fecha: Mapped[str] = mapped_column(String(10))  # manual | subida
    duracion_s: Mapped[float | None] = mapped_column(Float)
    fps: Mapped[float | None] = mapped_column(Float)
    ancho: Mapped[int] = mapped_column(Integer)
    alto: Mapped[int] = mapped_column(Integer)
    intervalo_s: Mapped[float] = mapped_column(Float)       # intervalo efectivo usado
    n_frames: Mapped[int] = mapped_column(Integer)
    indice_medio: Mapped[float] = mapped_column(Float)
    indice_max: Mapped[float] = mapped_column(Float)
    pct_afectados: Mapped[float] = mapped_column(Float)     # % de fotogramas con índice >= 15
    calificacion: Mapped[str] = mapped_column(String(12))   # según el índice medio
    perfil: Mapped[str] = mapped_column(String(10))
    parametros: Mapped[str | None] = mapped_column(Text)
    modo: Mapped[str] = mapped_column(String(12), default="fotogramas", server_default="fotogramas")  # fotogramas | anotado
    cada_n: Mapped[int | None] = mapped_column(Integer)           # modo anotado: se analiza 1 de cada N fotogramas
    ruta_anotado: Mapped[str | None] = mapped_column(String(255))  # video con las cajas dibujadas (solo modo anotado)
    ruta_gps: Mapped[str | None] = mapped_column(Text)             # JSON [[lat,lon],...] del GPX (opcional)
    modelo_version: Mapped[str] = mapped_column(String(80))
    tiempo_proceso_s: Mapped[float] = mapped_column(Float)
    notas: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tramo: Mapped[Tramo] = relationship()
    frames: Mapped[list["VideoFrame"]] = relationship(
        back_populates="video", cascade="all, delete-orphan", passive_deletes=True, order_by="VideoFrame.t_seg"
    )
    hallazgos: Mapped[list["VideoHallazgo"]] = relationship(
        back_populates="video", cascade="all, delete-orphan", passive_deletes=True, order_by="VideoHallazgo.t_ini"
    )


class VideoFrame(Base):
    __tablename__ = "video_frames"

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    t_seg: Mapped[float] = mapped_column(Float)
    indice: Mapped[float] = mapped_column(Float)
    n_detecciones: Mapped[int] = mapped_column(Integer)
    conteo: Mapped[str] = mapped_column(Text)               # JSON {clase: n}
    ruta_imagen: Mapped[str | None] = mapped_column(String(255))  # solo los fotogramas "peores"
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)

    video: Mapped[Video] = relationship(back_populates="frames")


class VideoHallazgo(Base):
    """Un daño distinto estimado por el seguimiento (modo anotado). Se puede descartar a mano."""

    __tablename__ = "video_hallazgos"

    id: Mapped[int] = mapped_column(primary_key=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), index=True)
    clase: Mapped[str] = mapped_column(String(32))
    t_ini: Mapped[float] = mapped_column(Float)
    t_fin: Mapped[float] = mapped_column(Float)
    n_apariciones: Mapped[int] = mapped_column(Integer)
    conf_max: Mapped[float] = mapped_column(Float)
    area_max: Mapped[float] = mapped_column(Float)
    ruta_imagen: Mapped[str] = mapped_column(String(255))
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    descartado: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    video: Mapped[Video] = relationship(back_populates="hallazgos")
