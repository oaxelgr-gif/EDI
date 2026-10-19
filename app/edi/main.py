"""EDI · servidor. Ensambla las rutas por módulo y sirve la interfaz."""
import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, db, mail, providers
from .api import chat, events, mail as mail_api, memory, settings, voice

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("edi")

STATIC = Path(__file__).resolve().parent.parent / "static"
app = FastAPI(title="EDI", version=__version__)
for r in (chat.router, memory.router, mail_api.router, settings.router, voice.router, events.router):
    app.include_router(r)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.on_event("startup")
async def startup():
    db.init()
    providers.seed_from_env()
    mail.import_yaml_once()
    asyncio.create_task(events.loop())
    log.info("EDI %s listo · IA activa: %s", __version__, [p["name"] for p in providers.active()] or "ninguna")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/api/health")
def health():
    try:
        import edge_tts  # noqa: F401
        tts_ok = True
    except ImportError:
        tts_ok = False
    return {"ok": True, "version": __version__, "user": db.get_setting("user_name"),
            "llm": [p["name"] for p in providers.active()],
            "accounts": len(mail.list_accounts(only_enabled=True)), "tts": tts_ok}
