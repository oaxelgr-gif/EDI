"""Jira — funciona con Jira Cloud (empresa.atlassian.net) y con Jira Server / Data Center de la empresa.

Cloud:   correo + API token (https://id.atlassian.com/manage-profile/security/api-tokens) · REST v3 para buscar.
Server:  token personal (PAT, Jira 8.14+) o usuario + contraseña · REST v2.
Lo que tienes asignado se vuelve pendiente de TRABAJO en EDI; lo que se cierra en Jira se marca hecho."""
import re
import unicodedata
from datetime import datetime

from .base import Connector, ConnectorError, tally, upsert_task

ACTIVE_JQL = "assignee = currentUser() AND statusCategory != Done ORDER BY duedate ASC, priority DESC"
DONE_JQL = "assignee = currentUser() AND statusCategory = Done AND updated >= -14d"
FIELDS = ["summary", "status", "duedate", "priority", "description", "project", "issuetype", "updated"]


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if unicodedata.category(c) != "Mn")


def adf_to_text(node) -> str:
    """Convierte el formato de documento de Atlassian (ADF, Cloud v3) a texto plano."""
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(adf_to_text(n) for n in node)
    t = node.get("type")
    if t == "text":
        return node.get("text", "")
    if t in ("hardBreak",):
        return "\n"
    if t == "mention":
        return node.get("attrs", {}).get("text", "")
    inner = adf_to_text(node.get("content"))
    if t in ("paragraph", "heading", "blockquote", "codeBlock"):
        return inner.strip() + "\n"
    if t == "listItem":
        return "• " + inner.strip() + "\n"
    return inner


PRIORITY = {"highest": "alta", "high": "alta", "alta": "alta", "muy alta": "alta", "critical": "alta", "blocker": "alta",
            "low": "baja", "lowest": "baja", "baja": "baja", "muy baja": "baja", "minor": "baja", "trivial": "baja"}

# Palabras con las que pides un estado → categoría de estado de Jira
TARGETS = {
    "done": ["terminado", "terminada", "hecho", "hecha", "listo", "lista", "finalizado", "cerrado", "completado", "resuelto",
             "done", "closed", "resolved", "finalizar", "terminar", "cerrar"],
    "indeterminate": ["en curso", "en progreso", "progreso", "haciendo", "trabajando", "in progress", "iniciar", "empezar",
                      "en desarrollo", "desarrollo", "revision", "en revision", "review"],
    "new": ["por hacer", "pendiente", "to do", "todo", "abierto", "backlog", "reabrir"],
}


class JiraConnector(Connector):
    kind = "jira"
    label = "Jira"
    help = ("Cloud: tu correo y un API token. Server/Data Center: un token personal (PAT) o usuario y contraseña. "
            "EDI trae lo que tienes asignado como pendientes de trabajo y puede crear, mover y comentar tickets.")
    help_url = "https://id.atlassian.com/manage-profile/security/api-tokens"
    FIELDS = [
        {"key": "base_url", "label": "Dirección de Jira", "type": "url", "placeholder": "https://empresa.atlassian.net o https://jira.empresa.com",
         "required": True, "target": "base_url"},
        {"key": "flavor", "label": "Tipo", "type": "select", "options": [["auto", "Detectar automáticamente"], ["cloud", "Jira Cloud"],
                                                                        ["server", "Jira Server / Data Center"]], "target": "config"},
        {"key": "username", "label": "Correo (Cloud) o usuario (Server)", "type": "text", "placeholder": "tu@empresa.com",
         "help": "En Server con token personal (PAT) déjalo vacío.", "target": "username"},
        {"key": "secret", "label": "API token / token personal / contraseña", "type": "password", "target": "secret"},
        {"key": "project", "label": "Proyecto para tickets nuevos (clave)", "type": "text", "placeholder": "EDI", "target": "config",
         "help": "Cuando digas «crea un ticket…» sin decir proyecto."},
        {"key": "issuetype", "label": "Tipo de ticket por defecto", "type": "text", "placeholder": "Tarea", "target": "config"},
        {"key": "jql", "label": "Filtro (JQL) de tus pendientes", "type": "textarea", "placeholder": ACTIVE_JQL, "target": "config",
         "help": "Opcional. Por defecto: todo lo asignado a ti que no está terminado."},
    ]

    # ---------- conexión ----------
    @property
    def cloud(self) -> bool:
        fl = self.cfg.get("flavor") or "auto"
        if fl == "auto":
            return self.cfg.get("detected") == "cloud" or ".atlassian.net" in self.base or ".jira.com" in self.base
        return fl == "cloud"

    def _auth(self):
        user, secret = self.row.get("username") or "", self.row.get("secret") or ""
        if not secret:
            raise ConnectorError("Falta el token de Jira.")
        if self.cloud:
            if not user:
                raise ConnectorError("Jira Cloud necesita tu correo además del API token.")
            return {"auth": (user, secret), "headers": {"Accept": "application/json"}}
        if user:
            return {"auth": (user, secret), "headers": {"Accept": "application/json"}}
        return {"auth": None, "headers": {"Accept": "application/json", "Authorization": f"Bearer {secret}"}}

    def req(self, method: str, path: str, **kw):
        a = self._auth()
        r = self.http(method, self.base + path, auth=a["auth"], headers=a["headers"], **kw)
        return r.json() if r.content and "json" in r.headers.get("content-type", "") else {}

    def me(self) -> dict:
        if not self.cfg.get("me"):
            m = self.req("GET", "/rest/api/2/myself")
            self.save_cfg(me={"accountId": m.get("accountId"), "name": m.get("name") or m.get("key"),
                              "display": m.get("displayName") or m.get("name") or ""})
        return self.cfg["me"]

    def test(self) -> dict:
        if not self.base.startswith("http"):
            raise ConnectorError("La dirección debe empezar con https://")
        try:
            info = self.req("GET", "/rest/api/2/serverInfo")
            dep = (info.get("deploymentType") or "").lower()
            self.save_cfg(detected="cloud" if dep == "cloud" else "server", version=info.get("version", ""))
        except ConnectorError:
            pass
        self.cfg.pop("me", None)
        m = self.me()
        n = len(self.search(self.cfg.get("jql") or ACTIVE_JQL, limit=50))
        kind = "Jira Cloud" if self.cloud else "Jira Server/Data Center"
        return {"ok": True, "message": f"Conectado a {kind} como {m['display']}. Tienes {n} ticket{'s' if n != 1 else ''} abiertos asignados."}

    # ---------- lectura ----------
    def search(self, jql: str, limit: int = 300, fields=None) -> list[dict]:
        fields = fields or FIELDS
        out = []
        if self.cloud:   # Cloud: endpoint nuevo /search/jql con paginación por token
            token = None
            while len(out) < limit:
                body = {"jql": jql, "fields": fields, "maxResults": min(100, limit - len(out))}
                if token:
                    body["nextPageToken"] = token
                j = self.req("POST", "/rest/api/3/search/jql", json=body)
                out += j.get("issues", [])
                token = j.get("nextPageToken")
                if not token or j.get("isLast"):
                    break
        else:
            start = 0
            while len(out) < limit:
                j = self.req("POST", "/rest/api/2/search", json={"jql": jql, "fields": fields, "startAt": start,
                                                                "maxResults": min(100, limit - len(out))})
                issues = j.get("issues", [])
                out += issues
                start += len(issues)
                if not issues or start >= j.get("total", 0):
                    break
        return out

    def _task_fields(self, it: dict) -> dict:
        f = it.get("fields", {})
        desc = f.get("description")
        desc = adf_to_text(desc) if isinstance(desc, (dict, list)) else (desc or "")
        due = f"{f['duedate']}T09:00" if f.get("duedate") else None
        prio = PRIORITY.get(_fold((f.get("priority") or {}).get("name", "")), "normal")
        status = (f.get("status") or {}).get("name", "")
        return {"text": f"{it['key']} · {f.get('summary', '')}", "due": due, "notes": desc.strip()[:2000], "priority": prio,
                "link": f"{self.base}/browse/{it['key']}", "ext_status": status}

    def sync(self) -> dict:
        res = []
        active = self.search(self.cfg.get("jql") or ACTIVE_JQL)
        keys = set()
        for it in active:
            keys.add(it["key"])
            res.append(upsert_task(self, it["key"], **self._task_fields(it), source="jira"))
        for it in self.search(DONE_JQL, limit=100):
            if it["key"] not in keys:
                res.append(upsert_task(self, it["key"], **self._task_fields(it), done=True, source="jira"))
        return tally(res)

    def briefing(self) -> str:
        return ""

    def projects(self) -> list[dict]:
        j = self.req("GET", "/rest/api/2/project")
        return [{"key": p["key"], "name": p["name"]} for p in (j if isinstance(j, list) else [])]

    # ---------- acciones ----------
    def _issuetype(self, project: str) -> dict:
        p = self.req("GET", f"/rest/api/2/project/{project}")
        types = [t for t in p.get("issueTypes", []) if not t.get("subtask")]
        if not types:
            raise ConnectorError(f"El proyecto {project} no tiene tipos de ticket disponibles.")
        want = _fold(self.cfg.get("issuetype") or "")
        for t in types:
            if want and _fold(t["name"]) == want:
                return {"id": t["id"]}
        for t in types:
            if _fold(t["name"]) in ("tarea", "task"):
                return {"id": t["id"]}
        return {"id": types[0]["id"]}

    def create_issue(self, summary: str, description: str = "", due: datetime | None = None, project: str = "") -> dict:
        project = (project or self.cfg.get("project") or "").upper().strip()
        if not project:
            raise ConnectorError("No sé en qué proyecto crearlo. Pon un proyecto por defecto en Ajustes → Conexiones → Jira.")
        fields = {"project": {"key": project}, "summary": summary[:250], "issuetype": self._issuetype(project)}
        if description:
            fields["description"] = description
        if due:
            fields["duedate"] = due.strftime("%Y-%m-%d")
        me = self.me()
        assignee = {"accountId": me["accountId"]} if self.cloud and me.get("accountId") else {"name": me.get("name")}
        try:
            j = self.req("POST", "/rest/api/2/issue", json={"fields": {**fields, "assignee": assignee}})
        except ConnectorError as e:
            if "assignee" not in str(e).lower():
                raise
            j = self.req("POST", "/rest/api/2/issue", json={"fields": fields})   # sin permiso para asignar: créalo igual
        key = j["key"]
        return {"key": key, "link": f"{self.base}/browse/{key}"}

    def transitions(self, key: str) -> list[dict]:
        j = self.req("GET", f"/rest/api/2/issue/{key}/transitions")
        return [{"id": t["id"], "name": t["name"], "to": t.get("to", {}).get("name", ""),
                 "category": t.get("to", {}).get("statusCategory", {}).get("key", "")} for t in j.get("transitions", [])]

    def pick_transition(self, key: str, target: str) -> dict:
        ts = self.transitions(key)
        if not ts:
            raise ConnectorError(f"{key} no tiene cambios de estado disponibles para ti.")
        q = _fold(target).strip()
        for t in ts:   # nombre exacto del estado o de la transición
            if q in (_fold(t["name"]), _fold(t["to"])):
                return t
        for cat, words in TARGETS.items():
            if any(w in q for w in words):
                hit = [t for t in ts if t["category"] == cat]
                if hit:
                    return hit[0]
        for t in ts:
            if q and (q in _fold(t["name"]) or q in _fold(t["to"])):
                return t
        raise ConnectorError(f"No encontré el estado «{target}». Opciones para {key}: " + ", ".join(t["to"] or t["name"] for t in ts) + ".")

    def transition(self, key: str, transition_id: str) -> None:
        self.req("POST", f"/rest/api/2/issue/{key}/transitions", json={"transition": {"id": transition_id}})

    def comment(self, key: str, text: str) -> None:
        self.req("POST", f"/rest/api/2/issue/{key}/comment", json={"body": text})

    def update(self, key: str, summary: str | None = None, due: str | None = "keep", description: str | None = None) -> None:
        fields = {}
        if summary:
            fields["summary"] = summary[:250]
        if due != "keep":
            fields["duedate"] = due[:10] if due else None
        if description is not None:
            fields["description"] = description
        if fields:
            self.req("PUT", f"/rest/api/2/issue/{key}", json={"fields": fields})

    def issue(self, key: str) -> dict:
        it = self.req("GET", f"/rest/api/2/issue/{key}", params={"fields": ",".join(FIELDS)})
        return {"key": it["key"], **self._task_fields(it)}


KEY_RX = re.compile(r"\b([A-Z][A-Z0-9_]{1,9})[-\s]?(\d{1,6})\b", re.I)


def find_key(text: str) -> str | None:
    """'edi 12', 'EDI-12', 'e d i guion 12' → 'EDI-12'."""
    t = re.sub(r"\bguion\b", "-", text, flags=re.I)
    m = KEY_RX.search(t)
    return f"{m.group(1).upper()}-{m.group(2)}" if m else None
