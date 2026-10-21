"""Conectores de trabajo: registro, acceso y sincronización.

Agregar una herramienta nueva = crear un módulo con una clase Connector y registrarla en KINDS."""
import json
import logging

from .. import db
from .base import Connector, ConnectorError
from .github import GitHubConnector
from .jira import JiraConnector, find_key
from .slack import SlackConnector

log = logging.getLogger("edi.connectors")

KINDS: dict[str, type[Connector]] = {c.kind: c for c in (JiraConnector, GitHubConnector, SlackConnector)}
SECRET_MASK = "••••••••"


def schema() -> dict:
    return {k: {"label": c.label, "help": c.help, "help_url": c.help_url, "fields": c.FIELDS} for k, c in KINDS.items()}


def make(row: dict) -> Connector:
    cls = KINDS.get(row["kind"])
    if not cls:
        raise ConnectorError(f"Tipo de conexión desconocido: {row['kind']}")
    return cls(row)


def get(cid: int) -> Connector:
    row = db.get_connection(cid)
    if not row:
        raise ConnectorError("Esa conexión ya no existe.")
    return make(row)


def first(kind: str) -> Connector | None:
    rows = db.list_connections(kind, only_enabled=True)
    return make(rows[0]) if rows else None


def public(row: dict) -> dict:
    """Versión segura para la interfaz: sin secretos."""
    cfg = {k: v for k, v in json.loads(row.get("config") or "{}").items() if not k.startswith("_")}
    me = cfg.pop("me", None)
    return {"id": row["id"], "kind": row["kind"], "label": KINDS[row["kind"]].label if row["kind"] in KINDS else row["kind"],
            "name": row["name"], "base_url": row.get("base_url") or "", "username": row.get("username") or "",
            "has_secret": bool(row.get("secret")), "config": cfg, "enabled": row["enabled"], "me": (me or {}).get("display") or (me or {}).get("user") or (me or {}).get("login") or cfg.get("login"),
            "last_sync": row.get("last_sync"), "last_error": row.get("last_error"),
            "open_tasks": (db.one("SELECT COUNT(*) n FROM tasks WHERE conn_id=? AND done=0", (row["id"],)) or {}).get("n", 0)}


def save(data: dict, cid: int | None = None) -> int:
    """Crea o actualiza desde el formulario (campos según FIELDS)."""
    kind = data.get("kind") or (db.get_connection(cid) or {}).get("kind")
    cls = KINDS.get(kind)
    if not cls:
        raise ConnectorError("Elige el tipo de conexión.")
    cur = db.get_connection(cid) if cid else None
    cfg = json.loads(cur["config"]) if cur else {}
    cols = {}
    for f in cls.FIELDS:
        if f["key"] not in data:
            continue
        v = data[f["key"]]
        v = v.strip() if isinstance(v, str) else v
        if f["target"] == "config":
            cfg[f["key"]] = v
        elif f["target"] == "secret":
            if v and v != SECRET_MASK:
                cols["secret"] = v
        else:
            cols[f["target"]] = v
        if f.get("required") and not v and not (f["target"] == "secret" and cur and cur.get("secret")):
            raise ConnectorError(f"Falta: {f['label']}.")
    if cur and any(k in cols for k in ("base_url", "username", "secret")):
        cfg.pop("me", None)   # cambió la cuenta: vuelve a identificar al usuario
    name = (data.get("name") or "").strip() or (cur or {}).get("name") or cls.label
    if cur:
        db.update_connection(cid, name=name, config=json.dumps(cfg), **cols,
                             **({"enabled": int(bool(data["enabled"]))} if "enabled" in data else {}))
        return cid
    return db.add_connection(kind, name, cols.get("base_url", ""), cols.get("username", ""), cols.get("secret", ""), json.dumps(cfg))


def sync_one(cid: int) -> dict:
    c = get(cid)
    try:
        r = c.sync()
        db.update_connection(cid, last_sync=db.iso(), last_error="")
        return {"ok": True, **r}
    except Exception as e:
        msg = str(e) if isinstance(e, ConnectorError) else f"{e.__class__.__name__}: {e}"
        db.update_connection(cid, last_error=msg[:300])
        log.warning("sync %s: %s", c.row["name"], msg)
        return {"ok": False, "error": msg}


def sync_all() -> dict:
    out = {}
    for row in db.list_connections(only_enabled=True):
        out[row["id"]] = sync_one(row["id"])
    return out


def briefing() -> list[str]:
    parts = []
    for row in db.list_connections(only_enabled=True):
        try:
            t = make(row).briefing()
            if t:
                parts.append(t)
        except Exception as e:
            log.info("briefing %s: %s", row["name"], e)
    return parts


__all__ = ["KINDS", "Connector", "ConnectorError", "schema", "make", "get", "first", "public", "save", "sync_one", "sync_all",
           "briefing", "find_key", "SECRET_MASK"]
