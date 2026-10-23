import asyncio
import io

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from .. import live, whatsapp

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])


class SendIn(BaseModel):
    to: str
    text: str


class PairIn(BaseModel):
    phone: str


class ReadIn(BaseModel):
    jid: str


def _wrap(fn, *a):
    try:
        return fn(*a)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    except Exception as e:
        raise HTTPException(503, f"WhatsApp no disponible: {e}")


@router.get("/status")
async def status(start: bool = False):
    s = await asyncio.to_thread(whatsapp.status, start)
    s["has_qr"] = bool(s.pop("qr", None))
    return s


@router.get("/qr.svg")
async def qr():
    s = await asyncio.to_thread(whatsapp.status)
    if not s.get("qr"):
        raise HTTPException(404, "No hay código QR (ya está vinculado o aún está iniciando).")
    import segno
    buf = io.BytesIO()
    segno.make(s["qr"], error="l").save(buf, kind="svg", scale=6, border=1, dark="#111")
    return Response(buf.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@router.get("/chats")
async def chats():
    return await asyncio.to_thread(_wrap, whatsapp.chats)


@router.get("/contacts")
async def contacts():
    return await asyncio.to_thread(_wrap, whatsapp.contacts)


@router.get("/messages")
async def messages(jid: str):
    return await asyncio.to_thread(_wrap, whatsapp.messages, jid)


@router.post("/send")
async def send(body: SendIn):
    if not body.text.strip():
        raise HTTPException(400, "El mensaje está vacío.")
    res = await asyncio.to_thread(_wrap, whatsapp.send, body.to, body.text.strip())
    live.notify("whatsapp")
    return res


@router.post("/read")
async def read(body: ReadIn):
    res = await asyncio.to_thread(_wrap, whatsapp.read, body.jid)
    live.notify("whatsapp")
    return res


@router.post("/pair")
async def pair(body: PairIn):
    return await asyncio.to_thread(_wrap, whatsapp.pair, body.phone)


@router.post("/logout")
async def logout():
    return await asyncio.to_thread(_wrap, whatsapp.logout)
