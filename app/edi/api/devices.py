import os

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

from .. import security

router = APIRouter(tags=["dispositivos"])


class PinIn(BaseModel):
    pin: str


@router.get("/login")
def login_page():
    from ..main import STATIC
    return FileResponse(STATIC / "login.html", headers={"Cache-Control": "no-cache"})


@router.post("/api/login")
def login(body: PinIn):
    if body.pin.strip() != security.get_pin():
        raise HTTPException(401, "PIN incorrecto.")
    r = JSONResponse({"ok": True})
    r.set_cookie(security.COOKIE, security.token(), max_age=60 * 60 * 24 * 365, httponly=True, secure=True, samesite="lax")
    return r


@router.get("/api/devices")
def devices(request: Request):
    host = os.getenv("EDI_LAN_HOST", "").strip()
    return {"lan_url": f"https://{host}:8766" if host else "", "pin": security.get_pin(),
            "remote": security.is_remote(request), "host": host}


@router.get("/api/devices/siri")
def siri(request: Request):
    host = os.getenv("EDI_LAN_HOST", "").strip()
    port = security.SHORTCUT_PORT
    url = f"http://{host}:{port}/api/shortcut?token={security.api_token()}" if host and port else ""
    return {"url": url, "enabled": bool(port)}


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


@router.get("/api/devices/qr.svg")
def qr():
    import io

    import segno
    host = os.getenv("EDI_LAN_HOST", "").strip()
    if not host:
        raise HTTPException(404, "Sin IP de red")
    buf = io.BytesIO()
    segno.make(f"https://{host}:8766", error="m").save(buf, kind="svg", scale=8, border=0, dark="#1d1430")
    return Response(buf.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-cache"})
