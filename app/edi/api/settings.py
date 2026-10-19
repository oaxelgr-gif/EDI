import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import db, providers

router = APIRouter(prefix="/api", tags=["ajustes"])


class ProviderIn(BaseModel):
    name: str = ""
    kind: str = "custom"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    priority: int = 10
    enabled: int = 1


class ProviderPatch(BaseModel):
    name: str | None = None
    kind: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    priority: int | None = None
    enabled: int | None = None


class Order(BaseModel):
    ids: list[int]


@router.get("/settings")
def get_settings():
    return db.all_settings()


@router.put("/settings")
def put_settings(values: dict):
    db.set_settings(values)
    return db.all_settings()


@router.get("/providers/kinds")
def kinds():
    return providers.KINDS


@router.get("/providers")
def list_providers():
    usage = providers.usage_today()
    return [{**providers.public(p), "usage": usage.get(p["id"])} for p in providers.list_all()]


@router.post("/providers")
def add_provider(body: ProviderIn):
    if body.kind not in providers.KINDS:
        raise HTTPException(400, "Tipo de proveedor desconocido.")
    if body.kind == "custom" and not body.base_url:
        raise HTTPException(400, "Escribe la URL base (termina en /v1).")
    return {"id": providers.add(body.name, body.kind, body.base_url, body.api_key, body.model, body.priority, body.enabled)}


@router.patch("/providers/{pid}")
def patch_provider(pid: int, body: ProviderPatch):
    return {"ok": providers.update(pid, body.model_dump(exclude_none=True))}


@router.put("/providers/order")
def reorder(body: Order):
    for i, pid in enumerate(body.ids, start=1):
        providers.update(pid, {"priority": i})
    return {"ok": True}


@router.delete("/providers/{pid}")
def delete_provider(pid: int):
    return {"ok": providers.delete(pid)}


@router.post("/providers/test")
async def test_new(body: ProviderIn):
    k = providers.KINDS.get(body.kind, providers.KINDS["custom"])
    p = {**body.model_dump(), "base_url": (body.base_url or k["base_url"]).rstrip("/"), "model": body.model or k["model"]}
    return await asyncio.to_thread(providers.test, p)


@router.post("/providers/{pid}/test")
async def test_saved(pid: int):
    p = providers.get(pid)
    if not p:
        raise HTTPException(404, "Ese proveedor no existe.")
    return await asyncio.to_thread(providers.test, p)


@router.get("/providers/{pid}/models")
async def models(pid: int):
    p = providers.get(pid)
    if not p:
        raise HTTPException(404, "Ese proveedor no existe.")
    return await asyncio.to_thread(providers.list_models, p)
