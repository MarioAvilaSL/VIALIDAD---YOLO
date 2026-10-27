"""Acceso opcional por token, pensado para cuando la app se abre a la red local (celular -> PC).

Si APP_TOKEN está vacío no hace nada (uso local en 127.0.0.1). Si tiene valor, /api y /media exigen una cookie
que se obtiene una sola vez abriendo /acceso?t=TOKEN. No cifra el tráfico: sirve para que otra persona conectada
a la misma wifi no pueda ver tus fotos con solo abrir la dirección. Usa una red de confianza.
"""
import hmac

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .config import settings

COOKIE = "vialidad_token"
PROTEGIDOS = ("/api", "/media")


def _ok(valor: str | None) -> bool:
    tok = settings.app_token
    return bool(tok) and valor is not None and hmac.compare_digest(valor.encode(), tok.encode())


def instalar(app: FastAPI) -> None:
    @app.middleware("http")
    async def exigir_token(request: Request, call_next):
        if settings.app_token and request.url.path.startswith(PROTEGIDOS) and not _ok(request.cookies.get(COOKIE)):
            return JSONResponse({"detail": "Acceso no autorizado. Abre /acceso?t=TU_TOKEN una vez desde este dispositivo."},
                                status_code=401)
        return await call_next(request)

    @app.get("/acceso", include_in_schema=False)
    def acceso(t: str = ""):
        if not settings.app_token:
            return RedirectResponse("/m/", status_code=303)
        if not _ok(t):
            return HTMLResponse("<h3>Token incorrecto</h3><p>Revisa APP_TOKEN en el archivo .env del servidor.</p>", status_code=401)
        r = RedirectResponse("/m/", status_code=303)
        r.set_cookie(COOKIE, settings.app_token, max_age=365 * 24 * 3600, httponly=True, samesite="lax")
        return r

    @app.get("/health", include_in_schema=False)
    def health_simple():
        return {"ok": True}
