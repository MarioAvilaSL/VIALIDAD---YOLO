"""Utilidades compartidas por las pruebas."""
import io

from PIL import Image


def jpeg_bytes(w=640, h=480, color=(120, 120, 120), exif=None) -> bytes:
    b = io.BytesIO()
    kw = {"exif": exif} if exif else {}
    Image.new("RGB", (w, h), color).save(b, "JPEG", **kw)
    return b.getvalue()


def exif_con_fecha_y_gps() -> bytes:
    ex = Image.Exif()
    ex.get_ifd(0x8769)[0x9003] = "2026:10:20 08:30:00"
    gps = ex.get_ifd(0x8825)
    gps[1], gps[2] = "S", (3.0, 15.0, 36.0)
    gps[3], gps[4] = "W", (79.0, 57.0, 36.0)
    return ex.tobytes()


def crear_tramo(client, nombre="Av. Test") -> int:
    r = client.post("/api/tramos", json={"nombre": nombre, "ciudad": "Machala"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def subir(client, tramo_id, data=None, **form):
    data = data or jpeg_bytes()
    return client.post("/api/capturas", data={"tramo_id": tramo_id, **form},
                       files={"file": ("foto.jpg", data, "image/jpeg")})
