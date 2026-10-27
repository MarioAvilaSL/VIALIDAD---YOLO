from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def ensure_schema() -> None:
    """Crea las tablas nuevas y añade a las existentes las columnas introducidas después
    (create_all no modifica tablas ya creadas). Seguro de ejecutar muchas veces."""
    Base.metadata.create_all(engine)
    if engine.dialect.name != "postgresql":
        return
    nuevas = {
        "capturas": [
            "perfil VARCHAR(10) NOT NULL DEFAULT 'normal'",
            "parametros TEXT",
        ],
        "videos": [
            "modo VARCHAR(12) NOT NULL DEFAULT 'fotogramas'",
            "cada_n INTEGER",
            "ruta_anotado VARCHAR(255)",
            "ruta_gps TEXT",
        ],
        "video_frames": ["lat DOUBLE PRECISION", "lon DOUBLE PRECISION"],
    }
    insp = inspect(engine)
    with engine.begin() as con:
        for tabla, cols in nuevas.items():
            if not insp.has_table(tabla):
                continue
            for col in cols:
                con.execute(text(f"ALTER TABLE {tabla} ADD COLUMN IF NOT EXISTS {col}"))


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
