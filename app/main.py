import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .config import STORAGE, settings
from .db import ensure_schema
from .inference import ModelNotAvailable, detector
from . import security
from .routers import analizar, capturas, resumen, tramos, videos

log = logging.getLogger("vialidad")
STATIC = Path(__file__).resolve().parent / "static"
STORAGE.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_schema()      # crea tablas nuevas y añade columnas que falten
    videos.limpiar_tmp()  # borra restos de videos temporales de ejecuciones anteriores
    if settings.preload_model:
        try:
            detector.load()
            log.info("Modelo cargado: %s", detector.version)
        except ModelNotAvailable as e:
            log.warning("%s (la app arranca, pero no podrá analizar imágenes)", e)
    yield


app = FastAPI(title="Vialidad · Detección de daños viales", version="0.2.0", lifespan=lifespan)
security.instalar(app)
app.include_router(resumen.router)
app.include_router(tramos.router)
app.include_router(capturas.router)
app.include_router(analizar.router)
app.include_router(videos.router)
app.mount("/media", StaticFiles(directory=STORAGE), name="media")
app.mount("/", StaticFiles(directory=STATIC, html=True), name="web")
