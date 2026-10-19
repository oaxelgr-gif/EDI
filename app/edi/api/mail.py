import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import agent, mail

router = APIRouter(prefix="/api", tags=["correo"])


class AccountIn(BaseModel):
    name: str = ""
    provider: str = "gmail"
    user: str
    password: str = ""
    host: str = ""
    port: int = 993
    folders: str = "INBOX"
    enabled: int = 1


class AccountPatch(BaseModel):
    name: str | None = None
    provider: str | None = None
    user: str | None = None
    password: str | None = None
    host: str | None = None
    port: int | None = None
    folders: str | None = None
    enabled: int | None = None


@router.get("/mail")
async def get_mail(force: bool = False):
    return await asyncio.to_thread(agent.get_mail, force)


@router.get("/mail/presets")
def presets():
    return mail.PRESETS


@router.get("/accounts")
def accounts():
    return [mail.public(a) for a in mail.list_accounts()]


@router.post("/accounts")
def add_account(body: AccountIn):
    if "@" not in body.user and body.provider != "imap":
        raise HTTPException(400, "Escribe el correo completo, por ejemplo nombre@gmail.com.")
    aid = mail.add_account(body.model_dump())
    agent.invalidate_mail()
    return {"id": aid}


@router.patch("/accounts/{aid}")
def patch_account(aid: int, body: AccountPatch):
    ok = mail.update_account(aid, body.model_dump(exclude_none=True))
    agent.invalidate_mail()
    return {"ok": ok}


@router.delete("/accounts/{aid}")
def delete_account(aid: int):
    agent.invalidate_mail()
    return {"ok": mail.delete_account(aid)}


@router.post("/accounts/test")
async def test_new(body: AccountIn):
    return await asyncio.to_thread(mail.test_login, body.model_dump())


@router.post("/accounts/{aid}/test")
async def test_saved(aid: int):
    a = next((x for x in mail.list_accounts() if x["id"] == aid), None)
    if not a:
        raise HTTPException(404, "Esa cuenta no existe.")
    return await asyncio.to_thread(mail.test_login, a)
