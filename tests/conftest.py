import math
import os
import tempfile

import pytest

# La configuración debe fijarse ANTES de importar la app.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/vialidad_test"
)
os.environ["STORAGE_DIR"] = tempfile.mkdtemp(prefix="vialidad_test_")
os.environ["PRELOAD_MODEL"] = "false"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import engine  # noqa: E402
from app.inference import Det, detector  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def limpiar_bd(client):
    with engine.begin() as con:
        con.execute(text("TRUNCATE video_frames, videos, detecciones, capturas, tramos RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def falso_detector(monkeypatch):
    """Detector determinista: devuelve un bache que ocupa `area` de la imagen."""
    estado = {"area": 0.10}

    def predict(img, perfil=None):
        a = estado["area"]
        w, h = img.size
        lado = math.sqrt(a)
        det = Det("pothole", 0.9, 10, 10, 10 + lado * w, 10 + lado * h, a)
        return ([det] if a > 0 else []), 12.3

    monkeypatch.setattr(detector, "predict", predict)
    monkeypatch.setattr(detector, "load", lambda: None)
    monkeypatch.setattr(detector, "version", "falso@test")
    return estado


