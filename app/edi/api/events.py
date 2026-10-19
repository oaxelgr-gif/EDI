"""Avisos en vivo (Server-Sent Events): recordatorios vencidos y correo nuevo."""
import asyncio
import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from .. import agent, db, mail

log = logging.getLogger("edi.events")
router = APIRouter(prefix="/api", tags=["eventos"])
subscribers: set[asyncio.Queue] = set()


async def broadcast(event: dict):
    for q in list(subscribers):
        q.put_nowait(event)


async def loop():
    ticks = 0
    while True:
        try:
            # Sólo anuncia si EDI está abierto; si no, el recordatorio espera a que lo abras.
            for t in (db.due_reminders() if subscribers else []):
                await broadcast({"type": "reminder", "text": f"Recordatorio: {t['text']}.", "task": t})
            ticks += 1
            minutes = int(db.get_setting("mail_check_minutes") or 0)
            if subscribers and minutes > 0 and ticks % (minutes * 2) == 0 and mail.list_accounts(only_enabled=True):
                data = await asyncio.to_thread(agent.get_mail, True)
                items = [it for a in data["accounts"] for it in a["items"]]
                new = db.unseen_mail_uids([it["uid"] for it in items])
                if new:
                    fresh = [it for it in items if it["uid"] in new]
                    db.mark_mail_seen(list(new))
                    n = len(fresh)
                    await broadcast({"type": "mail", "mail": data,
                                     "text": f"{'Llegó un correo nuevo' if n == 1 else f'Llegaron {n} correos nuevos'}. "
                                             f"El último es de {fresh[0]['from']}: {fresh[0]['subject']}."})
        except Exception as e:
            log.warning("loop: %s", e)
        await asyncio.sleep(30)


@router.get("/events")
async def events():
    q: asyncio.Queue = asyncio.Queue()
    subscribers.add(q)

    async def gen():
        try:
            yield "retry: 3000\n\n"
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=25)
                    yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            subscribers.discard(q)

    return StreamingResponse(gen(), media_type="text/event-stream")
