import math
import time

import cv2
import numpy as np
import pytest

from app.config import STORAGE, settings
from app.inference import Det, detector
from helpers import crear_tramo


def hacer_video(path, segundos=10, fps=10, size=(320, 240), rampa=True) -> bytes:
    """Video sintético: el brillo sube con el tiempo (para que el detector falso 'vea' más daño al final)."""
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, size)
    n = segundos * fps
    for i in range(n):
        v = int(255 * i / (n - 1)) if rampa else 128
        w.write(np.full((size[1], size[0], 3), v, np.uint8))
    w.release()
    return path.read_bytes()


@pytest.fixture
def detector_por_brillo(monkeypatch):
    """area = brillo medio/255 * 0.3 -> el índice crece a lo largo del video."""
    def predict(img, perfil=None):
        a = float(np.asarray(img).mean()) / 255 * 0.3
        if a < 0.01:
            return [], 5.0
        lado = math.sqrt(a)
        return [Det("pothole", 0.9, 5, 5, 5 + lado * img.width, 5 + lado * img.height, a)], 5.0
    monkeypatch.setattr(detector, "predict", predict)
    monkeypatch.setattr(detector, "load", lambda: None)
    monkeypatch.setattr(detector, "version", "falso@video")


def esperar(client, job_id, timeout=90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = client.get(f"/api/videos/jobs/{job_id}").json()
        if j["estado"] in ("listo", "error", "cancelado"):
            return j
        time.sleep(0.2)
    raise AssertionError("el trabajo no terminó a tiempo")


def subir_video(client, data, nombre="ruta.avi", **form):
    return client.post("/api/videos", data=form, files={"file": (nombre, data, "video/x-msvideo")})


def tmp_vacio():
    t = STORAGE / "tmp"
    return not t.exists() or not any(t.iterdir())


@pytest.fixture(autouse=True)
def tmp_limpio():
    from app.routers.videos import limpiar_tmp
    limpiar_tmp()
    yield


def test_video_solo_analizar(client, detector_por_brillo, tmp_path):
    data = hacer_video(tmp_path / "v.avi")
    r = subir_video(client, data, intervalo_s=1.0)
    assert r.status_code == 202, r.text
    j = esperar(client, r.json()["job_id"])
    assert j["estado"] == "listo", j
    res = j["resultado"]
    assert res["guardado"] is False and res["video_id"] is None
    rs = res["resumen"]
    assert rs["n_frames"] == 10 and rs["intervalo_s"] == 1.0 and abs(rs["duracion_s"] - 10) < 0.2
    idx = [m["indice"] for m in res["serie"]]
    assert idx == sorted(idx) and idx[0] == 0.0 and idx[-1] > idx[3]          # sube con el tiempo
    assert rs["indice_max"] == max(idx) and 0 < rs["pct_afectados"] < 100
    assert rs["indice_medio"] == pytest.approx(sum(idx) / len(idx), abs=0.01)
    ts = [m["t"] for m in res["mejores"]]
    assert 1 <= len(ts) <= settings.video_top_frames
    assert all(b - a >= 2 * rs["intervalo_s"] - 1e-6 for a, b in zip(ts, ts[1:]))  # fotogramas separados
    assert all(m["imagen"].startswith("data:image/jpeg;base64,") for m in res["mejores"])
    assert client.get("/api/videos").json() == []                                  # nada en la base
    assert not (STORAGE / "videos").exists() or not any((STORAGE / "videos").iterdir())
    assert tmp_vacio()                                                              # el video subido se borró


def test_video_se_limita_a_max_fotogramas(client, detector_por_brillo, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "video_max_frames", 5)
    data = hacer_video(tmp_path / "v.avi", segundos=10, fps=10)
    j = esperar(client, subir_video(client, data, intervalo_s=0.2).json()["job_id"])
    rs = j["resultado"]["resumen"]
    assert rs["n_frames"] <= 5 and rs["intervalo_s"] > rs["intervalo_pedido_s"]


def test_video_guardar_en_seguimiento(client, detector_por_brillo, tmp_path):
    tid = crear_tramo(client)
    data = hacer_video(tmp_path / "v.avi")
    r = subir_video(client, data, guardar="true", tramo_id=tid, fecha_inicio="2026-10-20T07:30",
                    sensibilidad="sensible", notas="recorrido de prueba", intervalo_s=1)
    j = esperar(client, r.json()["job_id"])
    assert j["estado"] == "listo", j
    vid = j["resultado"]["video_id"]
    assert j["resultado"]["guardado"] is True and vid
    carpeta = STORAGE / "videos" / str(vid)
    assert carpeta.is_dir() and len(list(carpeta.glob("*.jpg"))) == len(j["resultado"]["mejores"]) >= 1
    assert client.get(j["resultado"]["mejores"][0]["imagen"]).status_code == 200

    d = client.get(f"/api/videos/{vid}").json()
    assert d["resumen"]["perfil"] == "sensible" and d["resumen"]["notas"] == "recorrido de prueba"
    assert d["resumen"]["fecha_inicio"].startswith("2026-10-20T07:30")
    assert len(d["serie"]) == 10 and d["serie"][-1]["conteo"] == {"pothole": 1}
    assert [m["t"] for m in d["mejores"]] == [m["t"] for m in j["resultado"]["mejores"]]

    assert [v["id"] for v in client.get(f"/api/videos?tramo_id={tid}").json()] == [vid]
    seg = client.get(f"/api/tramos/{tid}/seguimiento").json()
    assert [v["id"] for v in seg["videos"]] == [vid] and seg["videos"][0]["fecha"] == "2026-10-20"
    assert client.get("/api/resumen").json()["videos"] == 1
    assert client.get("/api/tramos").json()[0]["n_videos"] == 1

    assert client.delete(f"/api/videos/{vid}").status_code == 204
    assert not carpeta.exists() and client.get(f"/api/videos/{vid}").status_code == 404


def test_eliminar_tramo_borra_videos_y_carpeta(client, detector_por_brillo, tmp_path):
    tid = crear_tramo(client)
    j = esperar(client, subir_video(client, hacer_video(tmp_path / "v.avi", 4), guardar="true",
                                    tramo_id=tid, intervalo_s=1).json()["job_id"])
    carpeta = STORAGE / "videos" / str(j["resultado"]["video_id"])
    assert carpeta.exists()
    assert client.delete(f"/api/tramos/{tid}").status_code == 204
    assert not carpeta.exists() and client.get("/api/videos").json() == []


def test_video_validaciones(client, detector_por_brillo, tmp_path, monkeypatch):
    data = hacer_video(tmp_path / "v.avi", 2)
    assert subir_video(client, data, nombre="x.exe").status_code == 415
    assert subir_video(client, data, guardar="true").status_code == 422              # falta tramo
    assert subir_video(client, data, guardar="true", tramo_id=999).status_code == 404
    assert subir_video(client, data, intervalo_s=0.01).status_code == 422
    assert subir_video(client, data, fecha_inicio="ayer", guardar="false").status_code == 422
    assert subir_video(client, b"").status_code == 400
    monkeypatch.setattr(settings, "max_video_mb", 0)
    assert subir_video(client, data).status_code == 413
    assert tmp_vacio()                                                                # no quedan restos


def test_video_corrupto_termina_en_error_claro(client, detector_por_brillo):
    j = esperar(client, subir_video(client, b"esto no es un video" * 100, nombre="malo.mp4").json()["job_id"])
    assert j["estado"] == "error" and "video" in j["error"].lower()
    assert tmp_vacio()


def test_trabajo_inexistente(client):
    assert client.get("/api/videos/jobs/noexiste").status_code == 404
    assert client.delete("/api/videos/jobs/noexiste").status_code == 404


def test_video_con_modelo_real(client, tmp_path):
    if not settings.resolved(settings.model_path).exists():
        pytest.skip("models/best.pt no está disponible")
    data = hacer_video(tmp_path / "v.avi", segundos=3, fps=10, rampa=False)
    j = esperar(client, subir_video(client, data, intervalo_s=1).json()["job_id"], timeout=180)
    assert j["estado"] == "listo", j
    assert j["resultado"]["resumen"]["n_frames"] == 3
    assert j["resultado"]["resumen"]["modelo_version"].startswith("best.pt@")


def test_cancelar_video_en_proceso(client, detector_por_brillo, tmp_path, monkeypatch):
    original = detector.predict

    def lento(img, perfil=None):
        time.sleep(0.25)
        return original(img, perfil)
    monkeypatch.setattr(detector, "predict", lento)
    data = hacer_video(tmp_path / "v.avi", segundos=20, fps=10)
    jid = subir_video(client, data, intervalo_s=1).json()["job_id"]
    t0 = time.time()
    while client.get(f"/api/videos/jobs/{jid}").json()["hechos"] < 2 and time.time() - t0 < 30:
        time.sleep(0.1)
    assert client.delete(f"/api/videos/jobs/{jid}").status_code == 204
    j = esperar(client, jid)
    assert j["estado"] == "cancelado" and j["resultado"] is None
    assert j["hechos"] < 20 and tmp_vacio()
    assert client.get("/api/videos").json() == []


def _ffprobe_ok(path):
    cap = cv2.VideoCapture(str(path))
    ok = cap.isOpened() and cap.get(cv2.CAP_PROP_FRAME_COUNT) > 0
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return ok, n


def test_video_anotado_solo_analizar(client, detector_por_brillo, tmp_path):
    data = hacer_video(tmp_path / "v.avi", segundos=4, fps=10)  # 40 fotogramas
    r = subir_video(client, data, modo="anotado", cada_n=4, guardar="false")
    assert r.status_code == 202, r.text
    j = esperar(client, r.json()["job_id"])
    assert j["estado"] == "listo", j
    res = j["resultado"]
    assert res["resumen"]["modo"] == "anotado" and res["resumen"]["n_frames"] == 10
    assert res["video_url"].endswith("/video")
    v = client.get(res["video_url"])
    assert v.status_code == 200 and v.headers["content-type"] == "video/mp4"
    destino = tmp_path / "out.mp4"
    destino.write_bytes(v.content)
    ok, n = _ffprobe_ok(destino)
    assert ok and n == 40  # todos los fotogramas, no solo los analizados
    assert client.delete(f"/api/videos/jobs/{j['id']}").status_code == 204


def test_video_anotado_guardado_y_borrado(client, detector_por_brillo, tmp_path):
    t = crear_tramo(client)
    data = hacer_video(tmp_path / "v.avi", segundos=2, fps=10)
    r = subir_video(client, data, modo="anotado", cada_n=2, guardar="true", tramo_id=t)
    j = esperar(client, r.json()["job_id"])
    assert j["estado"] == "listo", j
    res = j["resultado"]
    assert res["guardado"] and res["video_url"] == f"/media/videos/{res['video_id']}/anotado.mp4"
    assert (STORAGE / "videos" / str(res["video_id"]) / "anotado.mp4").exists()
    assert client.get(res["video_url"]).status_code == 200
    det = client.get(f"/api/videos/{res['video_id']}").json()
    assert det["video_url"] == res["video_url"] and det["resumen"]["modo"] == "anotado" and det["resumen"]["cada_n"] == 2
    assert client.delete(f"/api/videos/{res['video_id']}").status_code == 204
    assert not (STORAGE / "videos" / str(res["video_id"])).exists()
    assert tmp_vacio()


def test_limite_de_fotogramas_configurable(client, detector_por_brillo, tmp_path):
    data = hacer_video(tmp_path / "v.avi", segundos=20, fps=10)  # 200 fotogramas
    r = subir_video(client, data, intervalo_s=0.2, max_frames=40)
    res = esperar(client, r.json()["job_id"])["resultado"]["resumen"]
    assert res["n_frames"] <= 40 and res["limite_aplicado"] and res["max_frames"] == 40
    r = subir_video(client, data, intervalo_s=0.2, max_frames=200)
    res = esperar(client, r.json()["job_id"])["resultado"]["resumen"]
    assert res["n_frames"] == 100 and not res["limite_aplicado"]  # 200 fotogramas, 1 de cada 2


def test_limite_fuera_de_rango(client, detector_por_brillo, tmp_path):
    data = hacer_video(tmp_path / "v.avi", segundos=1)
    assert subir_video(client, data, max_frames=settings.video_max_frames_cap + 1).status_code == 422
    assert subir_video(client, data, max_frames=0).status_code == 422
    assert tmp_vacio()


def test_anotado_cancelado_no_deja_archivos(client, detector_por_brillo, tmp_path, monkeypatch):
    base = detector.predict
    def lento(img, perfil=None):
        time.sleep(0.05)
        return base(img, perfil)
    monkeypatch.setattr(detector, "predict", lento)
    data = hacer_video(tmp_path / "v.avi", segundos=10, fps=10)
    jid = subir_video(client, data, modo="anotado", cada_n=1).json()["job_id"]
    time.sleep(0.6)
    client.delete(f"/api/videos/jobs/{jid}")
    assert esperar(client, jid)["estado"] == "cancelado"
    assert tmp_vacio()


# ---------------- conteo de daños (seguimiento) y GPX ----------------
def video_con_cuadrados(path, fps=10, size=(320, 240)):
    """Dos «baches» (cuadrados blancos): el 1.º baja por la imagen entre 0 y 2 s; el 2.º aparece entre 4 y 6 s."""
    w = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), fps, size)
    for i in range(80):
        f = np.full((size[1], size[0], 3), 40, np.uint8)
        if i < 20:
            y = 10 + 8 * i
            f[y:y + 40, 60:100] = 255
        if 40 <= i < 60:
            y = 20 + 6 * (i - 40)
            f[y:y + 40, 200:240] = 255
        w.write(f)
    w.release()
    return path.read_bytes()


@pytest.fixture
def detector_cuadrados(monkeypatch):
    def predict(img, perfil=None):
        a = np.asarray(img)[..., 0] > 200
        if a.sum() < 100:
            return [], 5.0
        ys, xs = np.where(a)
        x1, y1, x2, y2 = float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())
        return [Det("pothole", 0.8, x1, y1, x2, y2, (x2 - x1) * (y2 - y1) / (img.width * img.height))], 5.0
    monkeypatch.setattr(detector, "predict", predict)
    monkeypatch.setattr(detector, "load", lambda: None)
    monkeypatch.setattr(detector, "version", "falso@cuadrados")


def test_conteo_cuenta_danos_distintos_no_fotogramas(client, detector_cuadrados, tmp_path):
    data = video_con_cuadrados(tmp_path / "v.avi")
    r = subir_video(client, data, modo="anotado", cada_n=2, guardar="false")
    res = esperar(client, r.json()["job_id"])["resultado"]
    h = res["hallazgos"]
    assert len(h) == 2, h                       # 20 fotogramas con daño, pero solo 2 daños distintos
    assert h[0]["t_ini"] < 1 and h[1]["t_ini"] >= 3.9 and all(x["clase"] == "pothole" for x in h)
    img = client.get(h[0]["imagen"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert res["resumen"]["n_hallazgos"] == 2 and res["ruta"] is None


def test_modo_fotogramas_no_cuenta(client, detector_cuadrados, tmp_path):
    data = video_con_cuadrados(tmp_path / "v.avi")
    res = esperar(client, subir_video(client, data, intervalo_s=1.0).json()["job_id"])["resultado"]
    assert res["hallazgos"] == []


def test_hallazgos_guardados_y_descarte_persistente(client, detector_cuadrados, tmp_path):
    t = crear_tramo(client)
    data = video_con_cuadrados(tmp_path / "v.avi")
    res = esperar(client, subir_video(client, data, modo="anotado", cada_n=2, guardar="true", tramo_id=t).json()["job_id"])["resultado"]
    vid, h = res["video_id"], res["hallazgos"]
    assert len(h) == 2 and h[0]["imagen"].startswith(f"/media/videos/{vid}/h_")
    assert client.get(h[0]["imagen"]).status_code == 200
    p = client.patch(f"/api/videos/{vid}/hallazgos/{h[0]['id']}", json={"descartado": True})
    assert p.status_code == 200 and p.json()["descartado"] is True
    det = client.get(f"/api/videos/{vid}").json()
    assert [x["descartado"] for x in det["hallazgos"]] == [True, False]
    assert client.patch(f"/api/videos/{vid}/hallazgos/999999", json={"descartado": True}).status_code == 404
    client.delete(f"/api/videos/{vid}")
    assert not (STORAGE / "videos" / str(vid)).exists()


def gpx_de(inicio_utc, n=30, lat0=-3.26, lon0=-79.96):
    from datetime import datetime, timedelta, timezone
    t0 = datetime.fromisoformat(inicio_utc).replace(tzinfo=timezone.utc)
    pts = "".join(f'<trkpt lat="{lat0 + i * 0.0001:.6f}" lon="{lon0:.6f}"><time>{(t0 + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ")}</time></trkpt>'
                  for i in range(n))
    return f'<?xml version="1.0"?><gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>{pts}</trkseg></trk></gpx>'.encode()


def test_gpx_ubica_hallazgos(client, detector_cuadrados, tmp_path):
    data = video_con_cuadrados(tmp_path / "v.avi")
    # 08:00 hora de Ecuador (UTC-5) = 13:00 UTC
    r = client.post("/api/videos", data={"modo": "anotado", "cada_n": 2, "guardar": "false", "fecha_inicio": "2026-01-10T08:00"},
                    files={"file": ("v.avi", data, "video/x-msvideo"), "gpx": ("r.gpx", gpx_de("2026-01-10T13:00:00"), "application/gpx+xml")})
    assert r.status_code == 202, r.text
    res = esperar(client, r.json()["job_id"])["resultado"]
    h = res["hallazgos"]
    assert len(h) == 2 and all(x["lat"] is not None for x in h)
    assert h[0]["lat"] < h[1]["lat"]                         # el 2.º daño ocurre más adelante en la ruta
    assert abs(h[1]["lat"] - (-3.26 + 0.0001 * 5)) < 0.0003  # ≈ t = 5 s
    assert res["ruta"] and res["resumen"]["gps_cubre_pct"] > 90


def test_gpx_errores(client, detector_cuadrados, tmp_path):
    data = video_con_cuadrados(tmp_path / "v.avi")
    f = {"file": ("v.avi", data, "video/x-msvideo")}
    sin_fecha = client.post("/api/videos", data={}, files={**f, "gpx": ("r.gpx", gpx_de("2026-01-10T13:00:00"), "x")})
    assert sin_fecha.status_code == 422
    otra_hora = client.post("/api/videos", data={"fecha_inicio": "2026-03-01T08:00"},
                            files={**f, "gpx": ("r.gpx", gpx_de("2026-01-10T13:00:00"), "x")})
    assert otra_hora.status_code == 422 and "no coincide" in otra_hora.json()["detail"]
    malo = client.post("/api/videos", data={"fecha_inicio": "2026-01-10T08:00"}, files={**f, "gpx": ("r.gpx", b"<gpx>", "x")})
    assert malo.status_code == 422
    xxe = b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x "y">]><gpx/>'
    assert client.post("/api/videos", data={"fecha_inicio": "2026-01-10T08:00"}, files={**f, "gpx": ("r.gpx", xxe, "x")}).status_code == 422
    assert tmp_vacio()
