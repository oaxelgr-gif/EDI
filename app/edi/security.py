"""Acceso desde otros dispositivos: todo lo que entra por la red (Wi‑Fi o Tailscale) necesita el PIN de 6 dígitos.
Tu Mac (http://localhost) entra directo. El PIN se ve y se cambia en Ajustes → Dispositivos.

- Cookie de sesión: "<id-del-dispositivo>.<firma>" (firma = HMAC del secreto con PIN + id). Si cambias el PIN
  o cierras sesión en todos los dispositivos, todas las cookies dejan de valer. La cookie anterior (sólo firma)
  sigue sirviendo y se cambia sola por la nueva la primera vez que entras.
- Límite de intentos: 5 PIN incorrectos seguidos → 5 minutos de espera (para todos los dispositivos).
- Dispositivos: cada navegador que entra queda en la lista con su último acceso; se puede quitar uno a uno."""
import hashlib
import hmac
import os
import secrets
import threading
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, RedirectResponse

from . import db

COOKIE = "edi_pin"
COOKIE_AGE = 60 * 60 * 24 * 365
OPEN_PATHS = ("/login", "/api/login", "/static/", "/manifest.webmanifest", "/sw.js", "/favicon")
MAX_FAILS = 5
LOCK_SECONDS = 5 * 60
SEEN_EVERY = 60          # segundos entre actualizaciones del «último acceso» (evita escribir en cada petición)

SHORTCUT_PORT = int(os.getenv("EDI_SHORTCUT_PORT", "0") or 0)
TS_PORT = int(os.getenv("EDI_TS_PORT", "0") or 0)   # puerto local al que llega «tailscale serve» (siempre con PIN)

DEVICES_SQL = """CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY, name TEXT, ip TEXT, via TEXT, user_agent TEXT, created TEXT, last_seen TEXT)"""


def init():
    db.run(DEVICES_SQL)
    get_pin()


# ---------------- secretos ----------------
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


def logout_all() -> str:
    """Cierra la sesión en todos los dispositivos: PIN nuevo + lista vacía."""
    pin = new_pin()
    db.run("DELETE FROM devices")
    _seen.clear()
    return pin


def token() -> str:
    """Firma de la versión anterior (sin id de dispositivo). Se acepta para no sacar a nadie al actualizar."""
    return hmac.new(_secret().encode(), get_pin().encode(), hashlib.sha256).hexdigest()


def _sign(device_id: str) -> str:
    return hmac.new(_secret().encode(), f"{get_pin()}:{device_id}".encode(), hashlib.sha256).hexdigest()


def cookie_for(device_id: str) -> str:
    return f"{device_id}.{_sign(device_id)}"


def check_cookie(value: str) -> tuple[bool, str, bool]:
    """→ (válida, id_dispositivo, es_formato_anterior)."""
    if not value:
        return False, "", False
    if "." in value:
        did, _, sig = value.partition(".")
        if did and hmac.compare_digest(sig, _sign(did)) and db.one("SELECT id FROM devices WHERE id=?", (did,)):
            return True, did, False
        return False, "", False
    return hmac.compare_digest(value, token()), "", True


# ---------------- límite de intentos ----------------
_lock = threading.Lock()
_fails: list[float] = []
_locked_until = 0.0


def lock_remaining() -> int:
    return max(0, int(_locked_until - time.time() + 0.999))


def check_pin(pin: str) -> tuple[bool, int, int]:
    """→ (correcto, segundos_de_espera, intentos_restantes). Con espera activa ni siquiera se compara."""
    global _locked_until
    with _lock:
        wait = lock_remaining()
        if wait:
            return False, wait, 0
        if hmac.compare_digest(pin.strip(), get_pin()):
            _fails.clear()
            return True, 0, MAX_FAILS
        _fails.append(time.time())
        if len(_fails) >= MAX_FAILS:
            _fails.clear()
            _locked_until = time.time() + LOCK_SECONDS
            return False, LOCK_SECONDS, 0
        return False, 0, MAX_FAILS - len(_fails)


def reset_attempts():
    global _locked_until
    with _lock:
        _fails.clear()
        _locked_until = 0.0


# ---------------- dispositivos ----------------
_seen: dict[str, float] = {}


def client_ip(request) -> str:
    if TS_PORT and _port(request) == TS_PORT:   # llega por «tailscale serve» (proxy local)
        fwd = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if fwd:
            return fwd
    return (request.client.host if request.client else "") or ""


def via(request) -> str:
    ip = client_ip(request)
    if (TS_PORT and _port(request) == TS_PORT) or ip.startswith("100.") and _is_cgnat(ip) or ip.startswith("fd7a:115c:a1e0"):
        return "tailscale"
    return "wifi"


def _is_cgnat(ip: str) -> bool:
    try:
        return 64 <= int(ip.split(".")[1]) <= 127
    except (IndexError, ValueError):
        return False


def device_name(ua: str) -> str:
    ua = ua or ""
    dev = ("iPhone" if "iPhone" in ua else "iPad" if "iPad" in ua else "Android" if "Android" in ua
           else "Mac" if "Macintosh" in ua else "Windows" if "Windows" in ua else "Linux" if "Linux" in ua else "Dispositivo")
    br = ("Edge" if "Edg/" in ua else "Chrome" if ("Chrome/" in ua or "CriOS" in ua) else "Firefox" if ("Firefox" in ua or "FxiOS" in ua)
          else "Safari" if "Safari" in ua else "")
    if dev in ("iPhone", "iPad") and "Safari" not in ua and br != "Chrome":
        br = "app de inicio"   # agregada a la pantalla de inicio (sin «Safari» en el agente)
    return f"{dev} · {br}" if br else dev


def register_device(request) -> str:
    did = secrets.token_urlsafe(9)
    ua = request.headers.get("user-agent", "")[:300]
    db.run("INSERT INTO devices(id, name, ip, via, user_agent, created, last_seen) VALUES (?,?,?,?,?,?,?)",
           (did, device_name(ua), client_ip(request), via(request), ua, db.iso(), db.iso()))
    _seen[did] = time.time()
    return did


def touch_device(did: str, request):
    now = time.time()
    if now - _seen.get(did, 0) < SEEN_EVERY:
        return
    _seen[did] = now
    db.run("UPDATE devices SET last_seen=?, ip=?, via=? WHERE id=?", (db.iso(), client_ip(request), via(request), did))


def list_devices(current: str = "") -> list[dict]:
    rows = db.rows("SELECT id, name, ip, via, created, last_seen FROM devices ORDER BY last_seen DESC")
    for r in rows:
        r["current"] = r["id"] == current
    return rows


def remove_device(did: str) -> bool:
    _seen.pop(did, None)
    return db.run("DELETE FROM devices WHERE id=?", (did,)) > 0


# ---------------- atajo de Siri ----------------
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


def _port(request):
    srv = request.scope.get("server") or (None, None)
    return srv[1]


def _is_shortcut_port(request) -> bool:
    return bool(SHORTCUT_PORT) and _port(request) == SHORTCUT_PORT


def is_remote(request) -> bool:
    """Viene de otro dispositivo: HTTPS directo (Wi‑Fi o IP de Tailscale) o el puerto de «tailscale serve»."""
    return request.url.scheme == "https" or (bool(TS_PORT) and _port(request) == TS_PORT)


class PinMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        # Puerto del atajo de Siri (HTTP en tu red): SÓLO /api/shortcut y con la llave correcta
        if _is_shortcut_port(request):
            given = request.query_params.get("token") or request.headers.get("x-edi-token", "")
            if path != "/api/shortcut" or not hmac.compare_digest(given, api_token()):
                return JSONResponse({"detail": "No autorizado"}, status_code=403)
            return await call_next(request)
        if not is_remote(request):
            return await call_next(request)
        if path.startswith(OPEN_PATHS):
            return await call_next(request)
        ok, did, legacy = check_cookie(request.cookies.get(COOKIE, ""))
        if not ok:
            if path.startswith("/api/"):
                return JSONResponse({"detail": "Escribe el PIN de EDI para entrar."}, status_code=401)
            return RedirectResponse("/login")
        if legacy:   # cookie de la versión anterior: se registra el dispositivo y se cambia por la nueva
            did = register_device(request)
        else:
            touch_device(did, request)
        request.state.device_id = did
        resp = await call_next(request)
        if legacy:
            set_cookie(resp, did)
        return resp


def set_cookie(resp, did: str):
    resp.set_cookie(COOKIE, cookie_for(did), max_age=COOKIE_AGE, httponly=True, secure=True, samesite="lax")
