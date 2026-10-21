"""CRUD de conexiones de trabajo (Jira, GitHub, Slack), prueba y sincronización."""
import asyncio
import json

from fastapi import APIRouter, HTTPException

from .. import connectors, db
from ..connectors import ConnectorError

router = APIRouter(prefix="/api/connections", tags=["conexiones"])


def _err(fn, *a):
    try:
        return fn(*a)
    except ConnectorError as e:
        raise HTTPException(409, str(e))


@router.get("/kinds")
def kinds():
    return connectors.schema()


@router.get("")
def list_all():
    return [connectors.public(r) for r in db.list_connections()]


@router.post("")
async def create(body: dict):
    cid = _err(connectors.save, body)
    res = await asyncio.to_thread(_test_and_sync, cid)
    return {"id": cid, **res}


@router.patch("/{cid}")
async def update(cid: int, body: dict):
    if not db.get_connection(cid):
        raise HTTPException(404, "Esa conexión ya no existe.")
    _err(connectors.save, body, cid)
    return {"ok": True, "connection": connectors.public(db.get_connection(cid))}


@router.delete("/{cid}")
def delete(cid: int, keep_tasks: bool = True):
    if not keep_tasks:
        db.run("DELETE FROM tasks WHERE conn_id=?", (cid,))
    return {"ok": db.delete_connection(cid)}


@router.post("/test")
async def test_unsaved(body: dict):
    """Prueba sin guardar (el formulario manda los datos tal cual)."""
    kind = body.get("kind")
    if kind not in connectors.KINDS:
        raise HTTPException(400, "Elige el tipo de conexión.")
    cid = body.get("id")
    row = dict(db.get_connection(cid)) if cid else {"id": None, "kind": kind, "base_url": "", "username": "", "secret": "", "config": "{}"}
    cfg = json.loads(row.get("config") or "{}")
    for f in connectors.KINDS[kind].FIELDS:
        if f["key"] in body:
            v = (body[f["key"]] or "").strip() if isinstance(body[f["key"]], str) else body[f["key"]]
            if f["target"] == "config":
                cfg[f["key"]] = v
            elif f["target"] == "secret":
                if v and v != connectors.SECRET_MASK:
                    row["secret"] = v
            else:
                row[f["target"]] = v
    cfg.pop("me", None)
    row["config"] = json.dumps(cfg)
    row["id"] = None   # no guarda nada durante la prueba
    try:
        return await asyncio.to_thread(connectors.make(row).test)
    except ConnectorError as e:
        return {"ok": False, "message": str(e)}
    except Exception as e:
        return {"ok": False, "message": f"{e.__class__.__name__}: {e}"}


def _test_and_sync(cid: int) -> dict:
    try:
        t = connectors.get(cid).test()
    except ConnectorError as e:
        db.update_connection(cid, last_error=str(e)[:300])
        return {"ok": False, "message": str(e)}
    s = connectors.sync_one(cid)
    return {"ok": True, "message": t["message"], "sync": s}


@router.post("/{cid}/test")
async def test(cid: int):
    return await asyncio.to_thread(_test_and_sync, cid)


@router.post("/{cid}/sync")
async def sync(cid: int):
    return await asyncio.to_thread(connectors.sync_one, cid)


@router.post("/sync")
async def sync_all():
    return await asyncio.to_thread(connectors.sync_all)


@router.get("/{cid}/projects")
async def projects(cid: int):
    c = _err(connectors.get, cid)
    if c.kind != "jira":
        return []
    return await asyncio.to_thread(_err, c.projects)
