"""Selector de modelos: catálogo, elección por petición, perfil propio de cada modelo y errores."""
import json

import pytest

from app.config import settings
from app.inference import Det
from app.modelos import registro
from helpers import crear_tramo, jpeg_bytes


@pytest.fixture
def falsos(monkeypatch):
    """Falsea los tres detectores y guarda con qué perfil se llamó a cada uno."""
    llamadas = []
    for m in registro.lista():
        d = m.detector

        def predict(img, perfil=None, _id=m.id):
            llamadas.append((_id, perfil.conf))
            w, h = img.size
            return [Det("pothole", 0.9, 10, 10, 60, 60, 0.05)], 5.0

        monkeypatch.setattr(d, "predict", predict)
        monkeypatch.setattr(d, "load", lambda: None)
        monkeypatch.setattr(d, "version", f"{m.id}.pt@test")
    return llamadas


def test_catalogo_tres_modelos_y_predeterminado_s(client):
    r = client.get("/api/modelos").json()
    assert r["predeterminado"] == "yolo26s"
    assert [m["id"] for m in r["modelos"]] == ["yolo26s", "yolo26n", "yolo26m"]
    assert [m["etiqueta"] for m in r["modelos"]] == ["Equilibrado (recomendado)", "Rápido", "Más preciso"]
    assert all("RDD2022" in m["descripcion"] for m in r["modelos"])


def test_sin_campo_modelo_usa_s(client, falsos):
    r = client.post("/api/analizar", files={"file": ("a.jpg", jpeg_bytes(), "image/jpeg")}, data={"sensibilidad": "sensible"})
    assert r.status_code == 200 and r.json()["modelo"] == "yolo26s"
    assert falsos == [("yolo26s", settings.perfil_sensible.conf_minimo())]


def test_modelo_n_usa_su_propio_perfil_sensible(client, falsos):
    r = client.post("/api/analizar", files={"file": ("a.jpg", jpeg_bytes(), "image/jpeg")},
                    data={"sensibilidad": "sensible", "modelo": "yolo26n"})
    j = r.json()
    assert r.status_code == 200 and j["modelo"] == "yolo26n" and j["modelo_version"] == "yolo26n.pt@test"
    assert falsos[-1][0] == "yolo26n"
    assert json.loads(j["parametros"])["conf_clase"] == settings.perfil_sensible_yolo26n.conf_clase
    assert json.loads(j["parametros"])["modelo_id"] == "yolo26n"


def test_modelo_desconocido_422(client, falsos):
    r = client.post("/api/analizar", files={"file": ("a.jpg", jpeg_bytes(), "image/jpeg")}, data={"modelo": "gpt"})
    assert r.status_code == 422 and "yolo26s" in r.json()["detail"]


def test_captura_guarda_el_modelo_elegido(client, falsos):
    tid = crear_tramo(client)
    r = client.post("/api/capturas", data={"tramo_id": tid, "modelo": "yolo26m"},
                    files={"file": ("a.jpg", jpeg_bytes(), "image/jpeg")})
    assert r.status_code in (200, 201)
    j = r.json()
    assert j["modelo_version"] == "yolo26m.pt@test" and j["modelo_nombre"].startswith("YOLO26m")


def test_modelo_sin_archivo_devuelve_503(client, monkeypatch, tmp_path):
    # simula que falta el .pt de n, tenga o no el archivo quien ejecute las pruebas
    d = registro.obtener("yolo26n").detector
    monkeypatch.setattr(d, "path", tmp_path / "no_existe.pt")
    monkeypatch.setattr(d, "_model", None)
    r = client.post("/api/analizar", files={"file": ("a.jpg", jpeg_bytes(), "image/jpeg")}, data={"modelo": "yolo26n"})
    assert r.status_code == 503 and "modelo" in r.json()["detail"].lower()


def test_habilitados_se_puede_restringir(client, monkeypatch):
    monkeypatch.setattr(settings, "modelos_habilitados", "yolo26s")
    r = client.post("/api/analizar", files={"file": ("a.jpg", jpeg_bytes(), "image/jpeg")}, data={"modelo": "yolo26n"})
    assert r.status_code == 422
    assert [m["id"] for m in client.get("/api/modelos").json()["modelos"]] == ["yolo26s"]


def test_seguimiento_avisa_modelos_mezclados(client, falsos):
    tid = crear_tramo(client)
    for m in ("yolo26s", "yolo26n"):
        r = client.post("/api/capturas", data={"tramo_id": tid, "modelo": m}, files={"file": ("a.jpg", jpeg_bytes(), "image/jpeg")})
        assert r.status_code in (200, 201)
    s = client.get(f"/api/tramos/{tid}/seguimiento").json()
    assert len(s["modelos"]) == 2


def test_cargar_modelo_y_desconocido(client, falsos):
    assert client.post("/api/modelos/yolo26n/cargar").status_code == 200
    assert client.post("/api/modelos/otro/cargar").status_code == 422
