"""Sincronización al instante entre la Mac y el celular.

Cada vez que algo se guarda en la base (pendientes, notas, conversaciones, mensajes, borradores, ajustes,
conexiones, cuentas, dispositivos…), se emite por /api/events un aviso:
    {"type": "changed", "kinds": ["tasks"], "kind": "tasks", "origin": "<id de la pestaña que lo hizo>"}

No hace falta llamar a nada desde las rutas: db.conn() registra qué tablas se escribieron (autorizador de SQLite)
y avisa al confirmar. Para cambios que no pasan por la base (correo IMAP, WhatsApp) se usa notify("mail").
Los avisos se agrupan 150 ms para no inundar el canal cuando una sincronización escribe 50 pendientes."""
import asyncio
import contextvars
import logging

log = logging.getLogger("edi.live")

# tabla de SQLite → tipo de dato que entiende la interfaz (las demás, como usage o mail_seen, no avisan)
TABLE_KIND = {
    "tasks": "tasks", "notes": "notes", "sessions": "sessions", "messages": "messages", "drafts": "drafts",
    "settings": "settings", "providers": "providers", "connections": "connections", "accounts": "accounts",
    "devices": "devices", "satellites": "satellites", "file_edits": "file_edits",
}
DEBOUNCE = 0.15

origin: contextvars.ContextVar[str] = contextvars.ContextVar("edi_origin", default="")

_loop: asyncio.AbstractEventLoop | None = None
_publish = None
_pending: set[str] = set()
_origins: set[str] = set()
_scheduled = False


def bind(loop: asyncio.AbstractEventLoop, publish) -> None:
    """Lo llama main.startup: a partir de aquí los cambios se anuncian. publish(evento: dict) debe ser síncrono."""
    global _loop, _publish, _scheduled
    _loop, _publish = loop, publish
    _pending.clear(); _origins.clear(); _scheduled = False


def kinds_for_tables(tables) -> set[str]:
    return {TABLE_KIND[t] for t in tables if t in TABLE_KIND}


def notify(*kinds: str) -> None:
    """Seguro desde cualquier hilo. Sin servidor (pruebas, scripts) no hace nada."""
    ks = {k for k in kinds if k}
    if not ks or _loop is None or _loop.is_closed():
        return
    org = origin.get()
    try:
        _loop.call_soon_threadsafe(_queue, ks, org)
    except RuntimeError:
        pass


def _queue(ks: set[str], org: str) -> None:
    global _scheduled
    _pending.update(ks)
    _origins.add(org)
    if not _scheduled:
        _scheduled = True
        _loop.call_later(DEBOUNCE, _flush)


def _flush() -> None:
    global _scheduled
    _scheduled = False
    if not _pending:
        return
    kinds = sorted(_pending)
    org = next(iter(_origins)) if len(_origins) == 1 else ""
    _pending.clear(); _origins.clear()
    try:
        _publish({"type": "changed", "kinds": kinds, "kind": kinds[0], "origin": org})
    except Exception as e:  # nunca romper una escritura por un aviso
        log.warning("changed: %s", e)
