import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import agent, db, drafts, mail

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
    smtp_host: str = ""
    smtp_port: int = 0


class AccountPatch(BaseModel):
    name: str | None = None
    provider: str | None = None
    user: str | None = None
    password: str | None = None
    host: str | None = None
    port: int | None = None
    folders: str | None = None
    enabled: int | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None


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


class ReadIn(BaseModel):
    uids: list[str] = []
    all: bool = False
    seen: bool = True


class SendIn(BaseModel):
    account_id: int
    to: str
    subject: str = ""
    body: str
    reply_uid: str = ""


@router.get("/mail/message")
async def message(uid: str):
    try:
        return await asyncio.to_thread(mail.get_message, uid)
    except Exception as e:
        raise HTTPException(409, str(e))


@router.post("/mail/read")
async def mark_read(body: ReadIn):
    try:
        n = await asyncio.to_thread(mail.mark_all_read) if body.all else await asyncio.to_thread(mail.mark_read, body.uids, body.seen)
    except Exception as e:
        raise HTTPException(409, mail.friendly(str(e)))
    agent.invalidate_mail()
    return {"ok": True, "count": n}


@router.post("/mail/send")
async def send(body: SendIn):
    """Envío directo desde el formulario (el usuario ya presionó Enviar)."""
    try:
        res = await asyncio.to_thread(drafts.send_email, body.account_id, body.to, body.subject, body.body, body.reply_uid)
    except Exception as e:
        raise HTTPException(409, str(e))
    return res


class DraftPatch(BaseModel):
    account_id: int | None = None
    to_addr: str | None = None
    to_name: str | None = None
    subject: str | None = None
    body: str | None = None
    extra: str | None = None


@router.get("/drafts/{did}")
def get_draft(did: int):
    d = db.get_draft(did)
    if not d:
        raise HTTPException(404, "Ese borrador ya no existe.")
    return d


@router.post("/drafts/{did}/send")
async def send_draft(did: int, body: DraftPatch):
    db.update_draft(did, **body.model_dump(exclude_none=True))
    try:
        return await asyncio.to_thread(drafts.send_draft, did)
    except Exception as e:
        raise HTTPException(409, str(e))


@router.delete("/drafts/{did}")
def cancel_draft(did: int):
    return {"ok": db.update_draft(did, status="cancelled")}
