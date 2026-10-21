"""EDI · servidor. Ensambla las rutas por módulo y sirve la interfaz."""
import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, db, mail, providers, security
from .api import chat, connections as conn_api, devices, events, mail as mail_api, memory, settings, voice, whatsapp as wa_api

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("edi")

STATIC = Path(__file__).resolve().parent.parent / "static"
app = FastAPI(title="EDI", version=__version__)
app.add_middleware(security.PinMiddleware)
for r in (chat.router, memory.router, mail_api.router, settings.router, voice.router, events.router, devices.router, wa_api.router, conn_api.router):
    app.include_router(r)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def fresh_static(request, call_next):
    """La interfaz siempre se revalida (ETag): cada actualización se ve al recargar, sin caché vieja."""
    resp = await call_next(request)
    if request.url.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.on_event("startup")
async def startup():
    db.init()
    security.get_pin()
    providers.seed_from_env()
    mail.import_yaml_once()
    asyncio.create_task(events.loop())
    log.info("EDI %s listo · IA activa: %s", __version__, [p["name"] for p in providers.active()] or "ninguna")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(STATIC / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    return FileResponse(STATIC / "sw.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})


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
