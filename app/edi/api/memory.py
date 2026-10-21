from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import db, work
from ..connectors import ConnectorError
from ..intents import parse_when

router = APIRouter(prefix="/api", tags=["memoria"])


class TaskIn(BaseModel):
    text: str
    due: str | None = None      # ISO "2026-10-20T17:00" o texto natural ("mañana a las 5")
    notes: str = ""
    priority: str = "normal"
    link: str = ""
    category: str = "personal"  # personal | trabajo
    to_jira: bool = False       # además, crear el ticket en Jira


class TaskPatch(BaseModel):
    text: str | None = None
    due: str | None = None
    done: bool | None = None
    notes: str | None = None        # descripción / detalles
    priority: str | None = None     # baja | normal | alta
    link: str | None = None         # enlace (Jira, GitHub, documento…)
    category: str | None = None     # personal | trabajo


class NotePatch(BaseModel):
    text: str


class ToJira(BaseModel):
    project: str = ""


class MoveIn(BaseModel):
    transition_id: str


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
def tasks(all: bool = False, category: str | None = None):
    return db.list_tasks(include_done=all, category=category if category in ("personal", "trabajo") else None)


@router.get("/tasks/{tid}")
def task(tid: int):
    t = db.get_task(tid)
    if not t:
        raise HTTPException(404, "Ese pendiente ya no existe.")
    return t


@router.post("/tasks")
def add_task(body: TaskIn):
    text = body.text.strip()
    when = _due(body.due)
    if not body.due:
        when, text = parse_when(text, db.now())
    if not text:
        raise HTTPException(400, "Escribe qué tienes pendiente.")
    cat = body.category if body.category in ("personal", "trabajo") else "personal"
    if body.to_jira:
        try:
            r = work.create_ticket(text, body.notes, when)
        except ConnectorError as e:
            raise HTTPException(409, str(e))
        return {"id": db.task_by_ext(db.list_connections("jira", True)[0]["id"], r["key"])["id"], "jira": r}
    return {"id": db.add_task(text, when, notes=body.notes, priority=body.priority if body.priority in ("baja", "normal", "alta") else "normal",
                              link=body.link, category=cat)}


@router.patch("/tasks/{tid}")
def patch_task(tid: int, body: TaskPatch):
    data = body.model_dump(exclude_none=True)
    if "due" in data:
        d = _due(data["due"])
        data["due"] = d.isoformat(timespec="minutes") if d else None
    if "done" in data:
        data["done"] = int(data["done"])
    if "text" in data and not data["text"].strip():
        raise HTTPException(400, "El título no puede quedar vacío.")
    if "priority" in data and data["priority"] not in ("baja", "normal", "alta"):
        data["priority"] = "normal"
    if "category" in data and data["category"] not in ("personal", "trabajo"):
        data.pop("category")
    t = db.get_task(tid)
    if not t:
        raise HTTPException(404, "Ese pendiente ya no existe.")
    msg = ""
    if "done" in data:
        msg = work.set_done(t, bool(data.pop("done")))
    ok = db.update_task(tid, **data) if data else True
    warn = work.push_edit(t, data)
    return {"ok": ok, "message": warn or msg}


@router.post("/tasks/{tid}/to-jira")
def task_to_jira(tid: int, body: ToJira):
    t = db.get_task(tid)
    if not t:
        raise HTTPException(404, "Ese pendiente ya no existe.")
    try:
        return {"ok": True, **work.to_jira(t, body.project)}
    except ConnectorError as e:
        raise HTTPException(409, str(e))


@router.get("/tasks/{tid}/transitions")
def task_transitions(tid: int):
    t = db.get_task(tid)
    j = work.jira_for(t) if t else None
    if not j:
        return []
    try:
        return j.transitions(t["ext_key"])
    except ConnectorError as e:
        raise HTTPException(409, str(e))


@router.post("/tasks/{tid}/move")
def task_move(tid: int, body: MoveIn):
    t = db.get_task(tid)
    j = work.jira_for(t) if t else None
    if not j:
        raise HTTPException(409, "Este pendiente no está enlazado a Jira.")
    try:
        ts = {x["id"]: x for x in j.transitions(t["ext_key"])}
        tr = ts.get(body.transition_id)
        if not tr:
            raise HTTPException(409, "Ese cambio de estado ya no está disponible.")
        j.transition(t["ext_key"], tr["id"])
        db.update_task(tid, ext_status=tr["to"] or tr["name"], done=int(tr["category"] == "done"))
        return {"ok": True, "message": f"{t['ext_key']} ahora está en «{tr['to'] or tr['name']}»."}
    except ConnectorError as e:
        raise HTTPException(409, str(e))


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


@router.patch("/notes/{nid}")
def patch_note(nid: int, body: NotePatch):
    if not body.text.strip():
        raise HTTPException(400, "La nota está vacía.")
    return {"ok": db.update_note(nid, body.text.strip())}


@router.delete("/notes/{nid}")
def delete_note(nid: int):
    return {"ok": db.delete_note(nid)}
