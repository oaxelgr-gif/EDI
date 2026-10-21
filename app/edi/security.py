"""Acceso desde la red: todo lo que entra por HTTPS (otros dispositivos) necesita el PIN.
Tu Mac (http://localhost) entra directo. El PIN se ve y se cambia en Ajustes → Dispositivos."""
import hashlib
import hmac
import os
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, RedirectResponse

from . import db

COOKIE = "edi_pin"
OPEN_PATHS = ("/login", "/api/login", "/static/", "/manifest.webmanifest", "/sw.js", "/favicon")


def _secret() -> str:
    s = db.one("SELECT value FROM settings WHERE key='_secret'")
    if s:
        return s["value"]
    v = secrets.token_hex(16)
    db.run("INSERT INTO settings(key, value) VALUES('_secret', ?)", (v,))
    return v


def get_pin() -> str:
    r = db.one("SELECT value FROM settings WHERE key='_lan_pin'")
    if r:
        return r["value"]
    pin = f"{secrets.randbelow(1_000_000):06d}"
    db.run("INSERT INTO settings(key, value) VALUES('_lan_pin', ?)", (pin,))
    return pin


def new_pin() -> str:
    pin = f"{secrets.randbelow(1_000_000):06d}"
    db.run("INSERT INTO settings(key, value) VALUES('_lan_pin', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (pin,))
    return pin


def token() -> str:
    return hmac.new(_secret().encode(), get_pin().encode(), hashlib.sha256).hexdigest()


SHORTCUT_PORT = int(os.getenv("EDI_SHORTCUT_PORT", "0") or 0)


def api_token() -> str:
    """Llave para el atajo de Siri (y otras integraciones). Se ve y se renueva en Ajustes → Dispositivos."""
    r = db.one("SELECT value FROM settings WHERE key='_api_token'")
    if r:
        return r["value"]
    v = secrets.token_urlsafe(18)
    db.run("INSERT INTO settings(key, value) VALUES('_api_token', ?)", (v,))
    return v


def new_api_token() -> str:
    v = secrets.token_urlsafe(18)
    db.run("INSERT INTO settings(key, value) VALUES('_api_token', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (v,))
    return v


def _is_shortcut_port(request) -> bool:
    srv = request.scope.get("server") or (None, None)
    return bool(SHORTCUT_PORT) and srv[1] == SHORTCUT_PORT


def is_remote(request) -> bool:
    return request.url.scheme == "https"


class PinMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        # Puerto del atajo de Siri (HTTP en tu red): SÓLO /api/shortcut y con la llave correcta
        if _is_shortcut_port(request):
            given = request.query_params.get("token") or request.headers.get("x-edi-token", "")
            if path != "/api/shortcut" or not hmac.compare_digest(given, api_token()):
                return JSONResponse({"detail": "No autorizado"}, status_code=403)
            return await call_next(request)
        if is_remote(request) and not path.startswith(OPEN_PATHS):
            if not hmac.compare_digest(request.cookies.get(COOKIE, ""), token()):
                if path.startswith("/api/"):
                    return JSONResponse({"detail": "Escribe el PIN de EDI para entrar."}, status_code=401)
                return RedirectResponse("/login")
        return await call_next(request)
