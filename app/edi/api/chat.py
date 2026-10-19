import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import agent, db

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
    return res


@router.get("/greeting")
async def greeting():
    """Saludo al abrir EDI: pendientes + correo, sin crear una conversación."""
    return await asyncio.to_thread(agent.handle, "EDI", 0, False)


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
