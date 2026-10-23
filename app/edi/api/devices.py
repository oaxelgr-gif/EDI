"""Ajustes → Dispositivos: PIN, accesos (Wi‑Fi y Tailscale), QR, dispositivos conectados y atajo de Siri."""
import asyncio
import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

from .. import security, tailnet

router = APIRouter(tags=["dispositivos"])
HTTPS_PORT = int(os.getenv("EDI_HTTPS_PORT", "8766") or 8766)


class PinIn(BaseModel):
    pin: str


def _wait_text(sec: int) -> str:
    m, s = divmod(sec, 60)
    return f"{m} min {s:02d} s" if m else f"{s} s"


@router.get("/login")
def login_page():
    from ..main import STATIC
    return FileResponse(STATIC / "login.html", headers={"Cache-Control": "no-cache"})


@router.get("/api/login/state")
def login_state():
    return {"wait": security.lock_remaining(), "max": security.MAX_FAILS}


@router.post("/api/login")
def login(body: PinIn, request: Request):
    ok, wait, left = security.check_pin(body.pin)
    if not ok:
        if wait:
            return JSONResponse({"detail": f"Demasiados intentos. Espera {_wait_text(wait)} y vuelve a intentar.",
                                 "wait": wait, "left": 0}, status_code=429)
        return JSONResponse({"detail": f"PIN incorrecto. Te quedan {left} intento{'s' if left != 1 else ''}.",
                             "wait": 0, "left": left}, status_code=401)
    did = security.register_device(request)
    r = JSONResponse({"ok": True})
    security.set_cookie(r, did)
    return r


def _lan() -> dict:
    host = os.getenv("EDI_LAN_HOST", "").strip()
    return {"host": host, "url": f"https://{host}:{HTTPS_PORT}" if host else ""}


@router.get("/api/devices")
async def devices(request: Request, fresh: bool = False):
    ts = await asyncio.to_thread(tailnet.info, fresh)
    lan = _lan()
    return {"lan_url": lan["url"], "host": lan["host"], "pin": security.get_pin(),
            "remote": security.is_remote(request), "via": security.via(request) if security.is_remote(request) else "mac",
            "lan": lan, "tailscale": ts, "lock": security.lock_remaining()}


@router.get("/api/devices/list")
def device_list(request: Request):
    return security.list_devices(getattr(request.state, "device_id", ""))


@router.delete("/api/devices/list/{did}")
def device_remove(did: str, request: Request):
    if security.is_remote(request) and did != getattr(request.state, "device_id", ""):
        raise HTTPException(403, "Quita otros dispositivos desde la Mac.")
    return {"ok": security.remove_device(did)}


@router.get("/api/devices/siri")
def siri(request: Request):
    host = os.getenv("EDI_LAN_HOST", "").strip()
    ts_host = os.getenv("EDI_TS_HOST", "").strip()
    port = security.SHORTCUT_PORT
    tok = security.api_token()
    url = f"http://{host}:{port}/api/shortcut?token={tok}" if host and port else ""
    url_ts = f"http://{ts_host}:{port}/api/shortcut?token={tok}" if ts_host and port else ""   # cifrado por Tailscale
    return {"url": url, "url_ts": url_ts, "enabled": bool(port)}


@router.post("/api/devices/siri/rotate")
def siri_rotate(request: Request):
    if security.is_remote(request):
        raise HTTPException(403, "Hazlo desde la Mac.")
    security.new_api_token()
    return siri(request)


@router.post("/api/devices/pin")
def rotate_pin(request: Request):
    if security.is_remote(request):
        raise HTTPException(403, "Cambia el PIN desde la Mac donde corre EDI.")
    return {"pin": security.new_pin()}


@router.post("/api/devices/logout-all")
def logout_all(request: Request):
    """Cierra la sesión en todos los dispositivos (también en éste si es un celular) y crea un PIN nuevo."""
    if security.is_remote(request):
        raise HTTPException(403, "Hazlo desde la Mac donde corre EDI.")
    security.reset_attempts()
    return {"pin": security.logout_all()}


@router.post("/api/devices/tailscale/serve")
async def tailscale_serve(request: Request):
    """Reintenta «tailscale serve» (p. ej. después de activar HTTPS en la cuenta de Tailscale)."""
    if security.is_remote(request):
        raise HTTPException(403, "Hazlo desde la Mac.")
    from ..serve import save_env
    r = await asyncio.to_thread(tailnet.enable_serve)
    vals = {"EDI_TS_URL": r["url"], "EDI_TS_ENABLE_URL": r["enable_url"]}
    os.environ.update(vals)
    save_env(vals)
    await asyncio.to_thread(tailnet.info, True)
    return r


@router.get("/api/devices/qr.svg")
async def qr(target: str = "lan"):
    import io

    import segno
    url = (await asyncio.to_thread(tailnet.info))["url"] if target == "tailscale" else _lan()["url"]
    if not url:
        raise HTTPException(404, "Sin dirección para ese acceso")
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", scale=8, border=0, dark="#1d1430")
    return Response(buf.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-cache"})
