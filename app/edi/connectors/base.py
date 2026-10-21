"""Base de los conectores de trabajo (Jira, GitHub, Slack).

Cada conector:
  · describe su formulario (FIELDS) para que la interfaz lo dibuje sola,
  · prueba la conexión (test),
  · sincroniza lo asignado a ti como pendientes de TRABAJO (sync),
  · y expone acciones propias (crear ticket, mover, enviar mensaje…).
Los secretos nunca salen del servidor: la API sólo devuelve si existen."""
import json
import logging

import httpx

from .. import db

log = logging.getLogger("edi.connectors")


class ConnectorError(RuntimeError):
    """Error con mensaje claro en español para mostrar al usuario."""


class Connector:
    kind = ""
    label = ""
    help = ""
    help_url = ""
    # Campos del formulario: key, label, type (text|url|password|select|textarea), placeholder, help, options, required, target
    #   target: "base_url" | "username" | "secret" | "config"  (dónde se guarda)
    FIELDS: list[dict] = []

    def __init__(self, row: dict):
        self.row = row
        self.id = row.get("id")
        self.cfg = json.loads(row.get("config") or "{}")

    # ---------- utilidades ----------
    @property
    def base(self) -> str:
        return (self.row.get("base_url") or "").rstrip("/")

    def save_cfg(self, **kv):
        self.cfg.update(kv)
        if self.id:
            db.update_connection(self.id, config=json.dumps(self.cfg))

    def http(self, method: str, url: str, *, headers=None, auth=None, timeout=20, **kw) -> httpx.Response:
        try:
            r = httpx.request(method, url, headers=headers, auth=auth, timeout=timeout, follow_redirects=True, **kw)
        except httpx.ConnectError:
            raise ConnectorError(f"No pude conectar con {url.split('/')[2] if '//' in url else url}. Revisa la dirección y tu internet/VPN.")
        except httpx.TimeoutException:
            raise ConnectorError("El servidor tardó demasiado en responder.")
        if r.status_code == 401:
            raise ConnectorError("Credenciales rechazadas (401): revisa el usuario/correo y el token.")
        if r.status_code == 403:
            raise ConnectorError("Sin permiso (403): tu token no tiene acceso a esto. Pide los permisos o usa otro token.")
        if r.status_code == 404:
            raise ConnectorError("No encontrado (404): revisa la dirección o la clave.")
        if r.status_code >= 400:
            try:
                j = r.json()
                msg = "; ".join(j.get("errorMessages") or []) or json.dumps(j.get("errors") or j)[:200] or j.get("message", "")
            except Exception:
                msg = r.text[:200]
            raise ConnectorError(f"Error {r.status_code}: {msg}")
        return r

    # ---------- interfaz común ----------
    def test(self) -> dict:
        raise NotImplementedError

    def sync(self) -> dict:
        return {"added": 0, "updated": 0, "done": 0}

    def briefing(self) -> str:
        return ""


# ---------- pendientes de trabajo a partir de elementos externos ----------
def upsert_task(conn: Connector, ext_key: str, *, text: str, due=None, notes: str = "", priority: str = "normal",
                link: str = "", ext_status: str = "", done: bool = False, source: str = "") -> str:
    """Crea o actualiza el pendiente espejo de un elemento externo. Regresa 'added' | 'updated' | 'same' | 'done'."""
    cur = db.task_by_ext(conn.id, ext_key)
    fields = {"text": text, "due": due, "notes": notes or "", "priority": priority, "link": link, "ext_status": ext_status}
    if cur:
        changes = {k: v for k, v in fields.items() if (cur.get(k) or "") != (v or "")}
        if done and not cur["done"]:
            changes["done"] = 1
        if not done and cur["done"] and not changes.get("done"):
            changes["done"] = 0   # se reabrió en la herramienta
        if changes:
            db.update_task(cur["id"], **changes)
            return "done" if changes.get("done") == 1 else "updated"
        return "same"
    if done:
        return "same"
    db.add_task(text, due, source=source or conn.kind, category="trabajo", ext_key=ext_key, conn_id=conn.id,
                notes=notes or "", priority=priority, link=link, ext_status=ext_status)
    return "added"


def tally(results: list[str]) -> dict:
    return {"added": results.count("added"), "updated": results.count("updated"), "done": results.count("done")}
