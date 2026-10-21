"""Lógica de trabajo compartida por la interfaz y la voz: pendientes ↔ Jira/GitHub/Slack.

Regla: Jira manda en los tickets. Si editas o terminas en EDI un pendiente que viene de Jira,
EDI aplica el cambio también en Jira (título, fecha, descripción, estado)."""
import logging
import re
from datetime import datetime

from . import connectors, db
from .connectors import ConnectorError

log = logging.getLogger("edi.work")
PREFIX = re.compile(r"^[A-Z][A-Z0-9_]+-\d+\s+·\s+")


def jira_for(task: dict):
    if task and task.get("conn_id"):
        row = db.get_connection(task["conn_id"])
        if row and row["kind"] == "jira" and row["enabled"]:
            return connectors.make(row)
    return None


def strip_key(text: str) -> str:
    return PREFIX.sub("", text or "")


def push_edit(task: dict, changes: dict) -> str:
    """Refleja en Jira lo editado en EDI. Regresa un aviso ('' si todo bien)."""
    j = jira_for(task)
    if not j or not task.get("ext_key"):
        return ""
    try:
        kw = {}
        if "text" in changes:
            kw["summary"] = strip_key(changes["text"])
        if "due" in changes:
            kw["due"] = changes["due"] or ""
        if "notes" in changes:
            kw["description"] = changes["notes"]
        if kw:
            j.update(task["ext_key"], **kw)
        return ""
    except ConnectorError as e:
        return f"Se guardó en EDI, pero Jira no aceptó el cambio: {e}"


def set_done(task: dict, done: bool) -> str:
    """Marca hecho/pendiente; si es de Jira, mueve el ticket a Terminado (o lo reabre)."""
    db.update_task(task["id"], done=int(done))
    j = jira_for(task)
    if not j or not task.get("ext_key"):
        return ""
    try:
        t = j.pick_transition(task["ext_key"], "terminado" if done else "por hacer")
        j.transition(task["ext_key"], t["id"])
        db.update_task(task["id"], ext_status=t["to"] or t["name"])
        return f"{task['ext_key']} pasó a «{t['to'] or t['name']}» en Jira."
    except ConnectorError as e:
        return f"Lo marqué en EDI, pero no pude moverlo en Jira: {e}"


def to_jira(task: dict, project: str = "") -> dict:
    """Sube un pendiente de EDI como ticket de Jira y los deja enlazados."""
    j = connectors.first("jira")
    if not j:
        raise ConnectorError("Primero conecta Jira en Ajustes → Conexiones.")
    if task.get("ext_key"):
        raise ConnectorError(f"Este pendiente ya está enlazado a {task['ext_key']}.")
    due = datetime.fromisoformat(task["due"]) if task.get("due") else None
    r = j.create_issue(task["text"], task.get("notes") or "", due, project)
    db.update_task(task["id"], conn_id=j.id, ext_key=r["key"], link=r["link"], category="trabajo",
                   text=f"{r['key']} · {task['text']}", ext_status="Por hacer", source="jira")
    return r


def create_ticket(summary: str, description: str = "", due: datetime | None = None, project: str = "") -> dict:
    """Crea el ticket en Jira y su pendiente espejo en EDI."""
    j = connectors.first("jira")
    if not j:
        raise ConnectorError("Primero conecta Jira en Ajustes → Conexiones.")
    r = j.create_issue(summary, description, due, project)
    db.add_task(f"{r['key']} · {summary}", due, source="jira", category="trabajo", conn_id=j.id, ext_key=r["key"],
                link=r["link"], notes=description, ext_status="Por hacer")
    return r


def move(key: str, target: str) -> str:
    j = connectors.first("jira")
    if not j:
        raise ConnectorError("Primero conecta Jira en Ajustes → Conexiones.")
    t = j.pick_transition(key, target)
    j.transition(key, t["id"])
    st = t["to"] or t["name"]
    task = db.task_by_ext(j.id, key)
    if task:
        db.update_task(task["id"], ext_status=st, done=int(t["category"] == "done"))
    return f"Listo, {key} ahora está en «{st}»."


def comment(key: str, text: str) -> str:
    j = connectors.first("jira")
    if not j:
        raise ConnectorError("Primero conecta Jira en Ajustes → Conexiones.")
    j.comment(key, text)
    return f"Comenté en {key}."


def work_summary() -> str:
    """Resumen de pendientes de trabajo para voz."""
    tasks = db.list_tasks(category="trabajo")
    if not tasks:
        has = db.list_connections(only_enabled=True)
        return "No tienes pendientes de trabajo." + ("" if has else " Conecta Jira o GitHub en Ajustes → Conexiones para traerlos solos.")
    now = db.now()
    late = [t for t in tasks if t["due"] and datetime.fromisoformat(t["due"]) < now]
    today = [t for t in tasks if t["due"] and datetime.fromisoformat(t["due"]).date() == now.date() and t not in late]
    parts = [f"Tienes {len(tasks)} pendiente{'s' if len(tasks) != 1 else ''} de trabajo"]
    if late:
        parts.append(f"{len(late)} atrasado{'s' if len(late) != 1 else ''}")
    if today:
        parts.append(f"{len(today)} para hoy")
    head = ", ".join(parts) + "."
    top = (late + today + [t for t in tasks if t not in late and t not in today])[:4]
    return head + " Los primeros: " + "; ".join(t["text"] + (f" ({t['ext_status']})" if t.get("ext_status") else "") for t in top) + "."
