import json
from types import SimpleNamespace

import pytest
from PIL import Image
from sqlalchemy import inspect, text

from app.config import STORAGE, Perfil, settings
from app.db import engine, ensure_schema
from app.inference import Detector

from helpers import crear_tramo, jpeg_bytes, subir


class _T:
    def __init__(self, v): self.v = v
    def tolist(self): return self.v


class ModeloFalso:
    """Imita lo mínimo de YOLO: devuelve 3 cajas con confianzas 0.90 (bache), 0.40 (bache), 0.15 (grieta)."""
    names = {0: "longitudinal_crack", 3: "pothole"}

    def __init__(self): self.llamadas = []

    def predict(self, img, **kw):
        self.llamadas.append(kw)
        keep = [(0.90, 3), (0.40, 3), (0.15, 0)]
        keep = [k for k in keep if k[0] >= kw["conf"]]
        b = SimpleNamespace(
            xyxy=_T([[10, 10, 60, 60]] * len(keep)), conf=_T([k[0] for k in keep]), cls=_T([float(k[1]) for k in keep]))
        return [SimpleNamespace(boxes=b)]


@pytest.fixture
def detector_falso():
    d = Detector()
    d._model = ModeloFalso()
    d.version = "falso@1"
    return d


def test_perfil_normal_filtra_por_umbral(detector_falso):
    dets, _ = detector_falso.predict(Image.new("RGB", (100, 100)), Perfil(conf=0.25))
    assert [round(d.confianza, 2) for d in dets] == [0.90, 0.40]


def test_perfil_sensible_recupera_mas(detector_falso):
    dets, _ = detector_falso.predict(Image.new("RGB", (100, 100)), Perfil(conf=0.10))
    assert len(dets) == 3
    assert detector_falso._model.llamadas[-1]["conf"] == 0.10


def test_umbral_por_clase_y_parametros_explicitos(detector_falso):
    p = Perfil(conf=0.10, conf_clase={"pothole": 0.5}, augment=True, imgsz=800)
    dets, _ = detector_falso.predict(Image.new("RGB", (100, 100)), p)
    assert sorted(d.clase for d in dets) == ["longitudinal_crack", "pothole"]  # bache 0.40 < 0.5 queda fuera
    kw = detector_falso._model.llamadas[-1]
    assert kw["augment"] is True and kw["imgsz"] == 800 and kw["conf"] == 0.10  # se envía el mínimo


def test_perfiles_por_defecto_son_distintos():
    assert settings.perfil("sensible").conf < settings.perfil("normal").conf
    assert settings.perfil("normal").conf == 0.25


def test_perfil_por_env_json():
    p = Perfil.model_validate_json('{"conf":0.1,"conf_clase":{"pothole":0.08},"imgsz":800,"augment":true}')
    assert p.conf_para("pothole") == 0.08 and p.conf_para("x") == 0.1 and p.conf_minimo() == 0.08


def test_captura_guarda_perfil(client):
    tid = crear_tramo(client)
    r = subir(client, tid, sensibilidad="sensible")
    assert r.status_code in (201, 503)
    if r.status_code == 201:
        c = r.json()
        assert c["perfil"] == "sensible" and c["conf_umbral"] == settings.perfil_sensible.conf
    assert subir(client, tid, sensibilidad="loquesea").status_code == 422


def test_migracion_agrega_columnas_a_tabla_vieja(client):
    with engine.begin() as con:
        con.execute(text("ALTER TABLE capturas DROP COLUMN perfil, DROP COLUMN parametros"))
    assert "perfil" not in {c["name"] for c in inspect(engine).get_columns("capturas")}
    ensure_schema()
    ensure_schema()  # idempotente
    cols = {c["name"] for c in inspect(engine).get_columns("capturas")}
    assert {"perfil", "parametros"} <= cols


# ---------- solo analizar ----------
def _archivos():
    return sorted(p.relative_to(STORAGE).as_posix() for p in STORAGE.rglob("*") if p.is_file())


def test_solo_analizar_no_guarda_nada(client, falso_detector):
    antes = _archivos()
    r = client.post("/api/analizar", data={"sensibilidad": "sensible"},
                    files={"file": ("a.jpg", jpeg_bytes(), "image/jpeg")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["guardado"] is False and d["perfil"] == "sensible" and d["n_detecciones"] == 1
    assert d["imagen_anotada"].startswith("data:image/jpeg;base64,") and d["conteo"] == {"pothole": 1}
    assert json.loads(d["parametros"])["perfil"] == "sensible"
    assert _archivos() == antes                               # nada escrito en disco
    assert client.get("/api/capturas").json() == []          # ni en la base
    assert client.get("/api/resumen").json()["capturas"] == 0


def test_solo_analizar_valida_archivo(client):
    assert client.post("/api/analizar", files={"file": ("a.jpg", b"basura", "image/jpeg")}).status_code == 400
    assert client.post("/api/analizar", data={"sensibilidad": "x"},
                       files={"file": ("a.jpg", jpeg_bytes(), "image/jpeg")}).status_code == 422


def test_perfil_sensible_desde_archivo_env(tmp_path):
    """La línea que imprime el notebook de calibración debe leerse bien desde un .env real."""
    from pydantic_settings import SettingsConfigDict

    from app.config import Settings

    env = tmp_path / ".env"
    env.write_text('PERFIL_SENSIBLE={"conf":0.05,"conf_clase":{"pothole":0.08,"alligator_crack":0.16},'
                   '"imgsz":800,"augment":true}\n')

    class S(Settings):
        model_config = SettingsConfigDict(env_file=str(env), extra="ignore")

    s = S()
    p = s.perfil("sensible")
    assert (p.conf, p.imgsz, p.augment) == (0.05, 800, True)
    assert p.conf_para("pothole") == 0.08 and p.conf_para("transverse_crack") == 0.05 and p.conf_minimo() == 0.05
    assert s.perfil("normal").conf == 0.25            # el normal no cambia


def test_analizar_vivo_es_ligero_y_no_guarda(client, falso_detector):
    antes = _archivos()
    r = client.post("/api/analizar_vivo", data={"sensibilidad": "sensible"},
                    files={"file": ("f.jpg", jpeg_bytes(540, 960), "image/jpeg")})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ancho"] == 540 and d["alto"] == 960 and len(d["detecciones"]) == 1
    assert d["detecciones"][0]["clase"] == "pothole" and "imagen_anotada" not in d
    assert _archivos() == antes and client.get("/api/capturas").json() == []
    assert client.post("/api/analizar_vivo", files={"file": ("a.jpg", b"basura", "image/jpeg")}).status_code == 400
