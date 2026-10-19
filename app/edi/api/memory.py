from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import db
from ..intents import parse_when

router = APIRouter(prefix="/api", tags=["memoria"])


class TaskIn(BaseModel):
    text: str
    due: str | None = None      # ISO "2026-10-20T17:00" o texto natural ("mañana a las 5")


class TaskPatch(BaseModel):
    text: str | None = None
    due: str | None = None
    done: bool | None = None


class NoteIn(BaseModel):
    text: str


def _due(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        when, _ = parse_when(value, db.now())
        return when


@router.get("/tasks")
def tasks(all: bool = False):
    return db.list_tasks(include_done=all)


@router.post("/tasks")
def add_task(body: TaskIn):
    text = body.text.strip()
    when = _due(body.due)
    if not body.due:
        when, text = parse_when(text, db.now())
    if not text:
        raise HTTPException(400, "Escribe qué tienes pendiente.")
    return {"id": db.add_task(text, when)}


@router.patch("/tasks/{tid}")
def patch_task(tid: int, body: TaskPatch):
    data = body.model_dump(exclude_none=True)
    if "due" in data:
        d = _due(data["due"])
        data["due"] = d.isoformat(timespec="minutes") if d else None
    if "done" in data:
        data["done"] = int(data["done"])
    return {"ok": db.update_task(tid, **data)}


@router.delete("/tasks/{tid}")
def delete_task(tid: int):
    return {"ok": db.delete_task(tid)}


@router.get("/notes")
def notes(q: str = ""):
    return db.search_notes(q, 50) if q else db.list_notes()


@router.post("/notes")
def add_note(body: NoteIn):
    if not body.text.strip():
        raise HTTPException(400, "La nota está vacía.")
    return {"id": db.add_note(body.text.strip())}


@router.delete("/notes/{nid}")
def delete_note(nid: int):
    return {"ok": db.delete_note(nid)}
