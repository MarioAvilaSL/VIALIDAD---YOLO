import io
import math
from datetime import datetime

import pytest
from PIL import Image

from app import severity
from app.config import STORAGE, settings
from app.inference import detector
from helpers import crear_tramo, exif_con_fecha_y_gps, jpeg_bytes, subir


# ---------- severidad ----------
def test_severidad_sin_daños_es_bueno():
    assert severity.calcular([]) == (0.0, "Bueno")


def test_severidad_crece_y_satura():
    a, _ = severity.calcular([("pothole", 0.05)])
    b, _ = severity.calcular([("pothole", 0.20)])
    c, calif = severity.calcular([("pothole", 5.0)])
    assert 0 < a < b < c <= 100 and calif == "Muy malo"


def test_severidad_pesa_mas_el_bache_que_la_grieta():
    p, _ = severity.calcular([("pothole", 0.1)])
    g, _ = severity.calcular([("longitudinal_crack", 0.1)])
    assert p > g


# ---------- tramos ----------
def test_tramo_crud_y_duplicado(client):
    tid = crear_tramo(client)
    assert client.post("/api/tramos", json={"nombre": "Av. Test"}).status_code == 409
    assert client.post("/api/tramos", json={"nombre": "x"}).status_code == 422
    assert client.post("/api/tramos", json={"nombre": "Ok", "lat": 200}).status_code == 422
    assert [t["id"] for t in client.get("/api/tramos").json()] == [tid]
    assert client.delete(f"/api/tramos/{tid}").status_code == 204
    assert client.delete(f"/api/tramos/{tid}").status_code == 404


# ---------- capturas ----------
def test_captura_con_modelo_real_y_exif(client):
    if not (settings.resolved(settings.model_path)).exists():
        pytest.skip("models/best.pt no está disponible")
    tid = crear_tramo(client)
    r = subir(client, tid, jpeg_bytes(exif=exif_con_fecha_y_gps()))
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["origen_fecha"] == "exif" and c["fecha_captura"].startswith("2026-10-20T08:30:00")
    assert c["origen_gps"] == "exif" and abs(c["lat"] - (-3.26)) < 0.01 and abs(c["lon"] - (-79.96)) < 0.01
    assert c["modelo_version"].startswith("best.pt@") and c["tiempo_inferencia_ms"] > 0
    assert 0 <= c["indice_severidad"] <= 100 and c["n_detecciones"] == len(c["detecciones"])
    assert (STORAGE / c["url_imagen"].removeprefix("/media/")).exists()
    assert client.get(c["url_anotada"]).status_code == 200


def test_captura_manual_tiene_prioridad_sobre_exif(client, falso_detector):
    tid = crear_tramo(client)
    r = subir(client, tid, jpeg_bytes(exif=exif_con_fecha_y_gps()),
              fecha_captura="2026-09-01T10:00", lat="-3.0", lon="-79.0")
    c = r.json()
    assert c["origen_fecha"] == "manual" and c["fecha_captura"].startswith("2026-09-01T10:00")
    assert c["origen_gps"] == "manual" and c["lat"] == -3.0
    assert c["calificacion"] == "Regular" and c["conteo"] == {"pothole": 1}
    assert c["indice_severidad"] == round(100 * (1 - math.exp(-4 * 0.10)), 2)


@pytest.mark.parametrize("data,code", [
    (b"", 400),
    (b"esto no es una imagen", 400),
    (b"GIF89a" + b"\x00" * 50, 400),
])
def test_archivos_invalidos(client, data, code):
    tid = crear_tramo(client)
    r = client.post("/api/capturas", data={"tramo_id": tid}, files={"file": ("x.jpg", data, "image/jpeg")})
    assert r.status_code == code


def test_formato_no_permitido(client):
    tid = crear_tramo(client)
    b = io.BytesIO()
    Image.new("RGB", (50, 50)).save(b, "BMP")
    r = client.post("/api/capturas", data={"tramo_id": tid}, files={"file": ("x.bmp", b.getvalue(), "image/bmp")})
    assert r.status_code == 415


def test_validaciones_de_formulario(client, falso_detector, monkeypatch):
    tid = crear_tramo(client)
    assert subir(client, 9999).status_code == 404
    assert subir(client, tid, lat="-3.0").status_code == 422          # lat sin lon
    assert subir(client, tid, lat="95", lon="0").status_code == 422   # fuera de rango
    assert subir(client, tid, fecha_captura="ayer").status_code == 422
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    grande = jpeg_bytes(3000, 3000, color=(1, 2, 3)) + b"\x00" * (2 * 1024 * 1024)
    assert subir(client, tid, grande).status_code == 413


def test_sin_modelo_devuelve_503(client, monkeypatch):
    from app import inference
    tid = crear_tramo(client)
    monkeypatch.setattr(detector, "_model", None)
    monkeypatch.setattr(inference, "MODEL_FILE", STORAGE / "no_existe.pt")
    r = subir(client, tid)
    assert r.status_code == 503 and "modelo" in r.json()["detail"].lower()
    assert client.get("/api/capturas").json() == []  # no quedó nada a medias


def test_eliminar_captura_borra_archivos(client, falso_detector):
    tid = crear_tramo(client)
    c = subir(client, tid).json()
    rutas = [STORAGE / c[k].removeprefix("/media/") for k in ("url_imagen", "url_anotada")]
    assert all(p.exists() for p in rutas)
    assert client.delete(f"/api/capturas/{c['id']}").status_code == 204
    assert not any(p.exists() for p in rutas)
    assert client.get(f"/api/capturas/{c['id']}").status_code == 404


def test_eliminar_tramo_borra_capturas_y_archivos(client, falso_detector):
    tid = crear_tramo(client)
    c = subir(client, tid).json()
    p = STORAGE / c["url_imagen"].removeprefix("/media/")
    client.delete(f"/api/tramos/{tid}")
    assert not p.exists() and client.get("/api/capturas").json() == []


# ---------- seguimiento ----------
def test_seguimiento_pocas_fechas(client, falso_detector):
    tid = crear_tramo(client)
    subir(client, tid, fecha_captura="2026-10-01T09:00")
    s = client.get(f"/api/tramos/{tid}/seguimiento").json()
    assert s["tendencia"]["disponible"] is False and len(s["puntos"]) == 1


def test_seguimiento_tendencia_empeorando(client, falso_detector):
    tid = crear_tramo(client)
    for dia, area in [("2026-09-01", 0.01), ("2026-09-15", 0.05), ("2026-10-01", 0.10), ("2026-10-15", 0.18)]:
        falso_detector["area"] = area
        subir(client, tid, fecha_captura=f"{dia}T09:00")
    s = client.get(f"/api/tramos/{tid}/seguimiento").json()
    t = s["tendencia"]
    assert t["disponible"] and t["sentido"] == "empeorando" and t["pendiente_30d"] > 2
    assert [p["fecha"] for p in s["puntos"]] == ["2026-09-01", "2026-09-15", "2026-10-01", "2026-10-15"]
    assert s["puntos"][0]["indice"] < s["puntos"][-1]["indice"]


def test_seguimiento_datos_dispersos_no_afirma_direccion(client, falso_detector):
    tid = crear_tramo(client)
    for dia, area in [("2026-09-01", 0.10), ("2026-09-15", 0.01), ("2026-10-01", 0.12), ("2026-10-15", 0.02)]:
        falso_detector["area"] = area
        subir(client, tid, fecha_captura=f"{dia}T09:00")
    t = client.get(f"/api/tramos/{tid}/seguimiento").json()["tendencia"]
    assert t["disponible"] and t["sentido"] == "incierta" and "Sin tendencia clara" in t["mensaje"]


def test_seguimiento_promedia_fotos_del_mismo_dia(client, falso_detector):
    tid = crear_tramo(client)
    for area in (0.0, 0.20):
        falso_detector["area"] = area
        subir(client, tid, fecha_captura="2026-10-01T09:00")
    p = client.get(f"/api/tramos/{tid}/seguimiento").json()["puntos"]
    assert len(p) == 1 and p[0]["n_capturas"] == 2
    esperado = 100 * (1 - math.exp(-4 * 0.20)) / 2  # cada foto se guarda redondeada a 2 decimales
    assert p[0]["indice"] == pytest.approx(esperado, abs=0.01)


# ---------- panel ----------
def test_resumen_y_health(client, falso_detector):
    h = client.get("/api/health").json()
    assert h["db"] is True
    r0 = client.get("/api/resumen").json()
    assert r0["capturas"] == 0 and r0["indice_medio"] is None
    tid = crear_tramo(client)
    subir(client, tid, lat="-3.26", lon="-79.96")
    r = client.get("/api/resumen").json()
    assert r["tramos"] == 1 and r["capturas"] == 1 and r["detecciones"] == 1
    assert r["por_clase"] == {"pothole": 1} and len(r["marcadores"]) == 1 and len(r["recientes"]) == 1
    assert isinstance(datetime.fromisoformat(r["marcadores"][0]["fecha"]), datetime)


# ---------------- acceso por token (red local) ----------------
def test_health_simple_responde(client):
    assert client.get("/health").json() == {"ok": True}


def test_sin_token_configurado_no_se_exige(client):
    assert client.get("/api/health").status_code == 200


def test_con_token_exige_cookie(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "app_token", "secreto123")
    assert client.get("/api/health").status_code == 401
    assert client.get("/media/lo-que-sea.jpg").status_code == 401
    assert client.get("/health").status_code == 200                      # el sondeo simple sigue abierto
    assert client.get("/acceso?t=malo", follow_redirects=False).status_code == 401
    r = client.get("/acceso?t=secreto123", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/m/"
    assert client.get("/api/health").status_code == 200                  # el cliente conserva la cookie
    client.cookies.clear()
    assert client.get("/api/health").status_code == 401


def test_pagina_movil_y_manifest(client):
    r = client.get("/m/")
    assert r.status_code == 200 and "Vialidad" in r.text
    assert client.get("/m/m.js").status_code == 200
    assert client.get("/m/manifest.webmanifest").status_code == 200
    assert client.get("/vendor/jspdf.umd.min.js").status_code == 200
