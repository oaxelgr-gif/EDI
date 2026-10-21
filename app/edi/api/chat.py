import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import tts, agent, db

router = APIRouter(prefix="/api", tags=["chat"])


class Ask(BaseModel):
    text: str
    session_id: int | None = None


class Rename(BaseModel):
    title: str


@router.post("/ask")
async def ask(body: Ask):
    if not body.text.strip():
        raise HTTPException(400, "Escribe o di algo para EDI.")
    sid = body.session_id if body.session_id and db.one("SELECT id FROM sessions WHERE id=?", (body.session_id,)) \
        else db.create_session()
    res = await asyncio.to_thread(agent.handle, body.text.strip(), sid)
    res["session_id"] = sid
    _with_voice(res)
    return res


def _with_voice(res: dict) -> dict:
    """Arranca la voz en el servidor antes de responder: el navegador la reproduce casi al mismo tiempo que el texto."""
    try:
        if res.get("reply") and not body_silent(res):
            res["tts_id"] = tts.start(res["reply"])
    except Exception:
        pass
    return res


def body_silent(res: dict) -> bool:
    return bool(res.get("repeat") and not res.get("reply"))


class ShortcutIn(BaseModel):
    text: str = ""


@router.post("/shortcut")
async def shortcut(body: ShortcutIn, format: str = "text"):
    """Atajo "Oye Siri, EDI": recibe lo dictado y regresa la respuesta (texto para que Siri la diga).
    Usa su propia conversación para que puedas seguir el hilo ("envíalo", "léeme el otro")."""
    from fastapi.responses import PlainTextResponse
    text = body.text.strip()
    if not text:
        g = await asyncio.to_thread(agent.greeting)
        return PlainTextResponse(g["reply"]) if format == "text" else g
    r = db.one("SELECT value FROM settings WHERE key='_siri_session'")
    sid = int(r["value"]) if r and db.one("SELECT id FROM sessions WHERE id=?", (int(r["value"]),)) else None
    if not sid:
        sid = db.create_session("Siri")
        db.run("INSERT INTO settings(key, value) VALUES('_siri_session', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(sid),))
    res = await asyncio.to_thread(agent.handle, text, sid)
    if format == "text":
        return PlainTextResponse(_strip(res.get("reply") or ""))
    res["session_id"] = sid
    return res


def _strip(t: str) -> str:
    return tts.speakable(t)


@router.get("/greeting")
async def greeting():
    """Saludo al abrir EDI: el primero del día con resumen; después, uno corto."""
    return _with_voice(await asyncio.to_thread(agent.greeting))


@router.get("/sessions")
def sessions():
    return db.list_sessions()


@router.post("/sessions")
def new_session():
    return {"id": db.create_session()}


@router.get("/sessions/{sid}")
def session(sid: int):
    s = db.one("SELECT * FROM sessions WHERE id=?", (sid,))
    if not s:
        raise HTTPException(404, "Esa conversación ya no existe.")
    return {**s, "messages": db.session_messages(sid)}


@router.patch("/sessions/{sid}")
def rename(sid: int, body: Rename):
    return {"ok": db.rename_session(sid, body.title)}


@router.delete("/sessions/{sid}")
def delete(sid: int):
    return {"ok": db.delete_session(sid)}
