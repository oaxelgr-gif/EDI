"""Comandos de voz de trabajo: Jira, GitHub y Slack.

Todo lo que cambia algo afuera (crear/mover/comentar ticket, mandar Slack) se prepara como BORRADOR
y sólo se ejecuta cuando dices «envíalo / créalo / sí» o tocas el botón. Las consultas responden directo."""
import json
import logging
import re
from datetime import datetime

from . import connectors, db, work
from .connectors import ConnectorError, find_key

log = logging.getLogger("edi.work_voice")

TICKET = r"(?:ticket|tiket|tarea|issue|historia|bug|incidencia|actividad|subtarea)"
SAY = r"(?:diciendole|diciendo|que diga|que dice|con el mensaje|para decirle que|y dile que|de que|que)"

P_CREATE = re.compile(rf"^(?:crea|crear|creame|abre|abreme|abrir|genera|generar|levanta|levantar|registra|registrar|agrega|agregar|haz|hazme|"
                      rf"sube|subir|mete|nuevo|nueva)\s+(?:un|una|el|la)?\s*(?:nuevo|nueva)?\s*{TICKET}"
                      rf"(?:\s+(?:en|a|de)\s+jira)?(?:\s+(?:en el|del|al)?\s*proyecto\s+(?P<proj>[a-z][a-z0-9_]{{1,9}}))?"
                      rf"[\s:,.-]*(?:(?:que se llame|llamad[oa]|titulad[oa]|que diga|para|de|sobre|con)\s+)?(?P<what>.*)$")
P_CREATE_JIRA = re.compile(rf"^(?:en jira|jira)[\s,:]+(?:crea|abre|genera|levanta|registra|agrega)\s+(?:un|una)?\s*{TICKET}?\s*(?P<what>.*)$")
P_MOVE = re.compile(r"^(?:mueve|muevelo|mover|pasa|pasar|cambia|cambiar|manda|marca|marcar|pon|poner|deja|dejar)\s+(?:el\s+|la\s+)?(?:ticket\s+|tarea\s+|issue\s+)?"
                    r"(?P<key>[a-z][a-z0-9_]{1,9}[\s-]?(?:guion\s)?\d{1,6})\s+(?:a|como|en|al estado)\s+(?P<target>.+)$")
P_FINISH = re.compile(r"^(?:termina|terminar|cierra|cerrar|finaliza|finalizar|completa|completar|resuelve|resolver|inicia|iniciar|empieza|empezar|reabre|reabrir)"
                      r"\s+(?:el\s+|la\s+)?(?:ticket\s+|tarea\s+|issue\s+)?(?P<key>[a-z][a-z0-9_]{1,9}[\s-]?(?:guion\s)?\d{1,6})$")
P_COMMENT = re.compile(rf"^(?:comenta|comentar|agrega un comentario|agregale un comentario|escribe un comentario|deja un comentario|pon un comentario)"
                       rf"\s+(?:en|a|al)\s+(?:el\s+|la\s+)?(?:ticket\s+|tarea\s+|issue\s+)?(?P<key>[a-z][a-z0-9_]{{1,9}}[\s-]?(?:guion\s)?\d{{1,6}})[\s,:]+(?:{SAY}\s+)?(?P<msg>.+)$")
P_TICKETS = re.compile(r"^(?:que|cuales|cuantos|dime|dame|lee(?:me)?|mis|ver)?\s*(?:son\s+)?(?:mis\s+)?(?:tickets|issues|pendientes de trabajo|tareas de trabajo|"
                       r"pendientes del trabajo|actividades|asignaciones)(?:\s+(?:tengo|hay|de jira|en jira|abiertos|asignados|pendientes))*$|"
                       r"^que tengo (?:en jira|de trabajo|del trabajo|asignado)$")
P_TICKET_INFO = re.compile(r"^(?:que (?:es|dice|onda con|pasa con)|de que (?:es|trata)|lee(?:me)?|dime|como va|como esta|en que va|estado de(?:l)?)\s+"
                           r"(?:el\s+)?(?:ticket\s+)?(?P<key>[a-z][a-z0-9_]{1,9}[\s-]?(?:guion\s)?\d{1,6})$")
P_SYNC = re.compile(r"^(?:sincroniza|sincronizar|actualiza|actualizar|refresca|revisa)\s+(?:jira|github|slack|mis tickets|los tickets|el trabajo|"
                    r"mis pendientes de trabajo|las conexiones|todo)$")
P_PRS = re.compile(r"\b(?:prs?|pull requests?|revisiones|code reviews?|reviews?)\b.*\b(?:tengo|hay|pendientes|por revisar|abiertos|mios)\b|"
                   r"^(?:mis|que|cuales)\s+(?:prs?|pull requests?|revisiones)\b")
P_BUILD = re.compile(r"\b(?:build|compilacion|pipeline|deploy|despliegue|ci|actions)\b.*?(?:\bde\s+(?P<repo>[\w./-]+))?$")
P_SLACK_SEND = re.compile(rf"^(?:manda|envia|escribe|mandar|enviar|escribir)(?:le|me)?\s+(?:un\s+)?(?:slack|mensaje\s+(?:por|en)\s+slack|mensaje de slack)"
                          rf"\s+(?:a|al|para)\s+(?P<who>.+?)(?:\s+{SAY}\s+(?P<msg>.+))?$|"
                          rf"^(?:escribe|escribele|dile|manda|mandale)\s+(?:en|por)\s+slack\s+(?:a|al)\s+(?P<who2>.+?)\s+{SAY}\s+(?P<msg2>.+)$|"
                          rf"^(?:escribe|publica|manda)\s+en\s+(?:el\s+)?canal\s+(?P<chan>#?[\w-]+)(?:\s+de\s+slack)?\s+{SAY}?\s*(?P<msg3>.+)$")
P_SLACK_READ = re.compile(r"\bslack\b.*\b(?:mensajes|menciones|nuevo|novedades|pendiente|tengo|hay)\b|^(?:que hay|que dicen|novedades) en slack$|"
                          r"^(?:tengo|hay)\s+(?:mensajes|menciones)\s+(?:en|de)\s+slack$")
P_WORK_TASK = re.compile(r"\b(?:de|del|para el)\s+trabajo\b|^trabajo\b[\s:,]*|\blaboral\b|\bde la oficina\b")


def _draft(session_id: int, channel: str, prefix: str, **f) -> dict:
    did = db.add_draft(session_id, channel, **f)
    return {"reply": prefix + " ¿Lo hago? Di «sí» o «cancela».", "data": {"draft": db.get_draft(did)}, "intent": "draft"}


def _need(kind: str) -> dict | None:
    if not connectors.first(kind):
        label = {"jira": "Jira", "github": "GitHub", "slack": "Slack"}[kind]
        return {"reply": f"Primero conecta {label} en Ajustes → Conexiones. Te abro la sección.", "data": {}, "intent": "connect",
                "action": {"open": "settings", "tab": "connections"}}
    return None


def handle(t: str, f: str, session_id: int) -> dict | None:
    """t: texto original (sin «EDI»), f: doblado (minúsculas sin acentos), alineado con t."""
    from .intents import parse_when
    try:
        # ---------- Jira: crear ticket ----------
        m = P_CREATE.match(f) or P_CREATE_JIRA.match(f)
        # "tarea"/"actividad" sólo cuentan como Jira si lo dices ("en Jira"); si no, es un pendiente normal
        if m and re.search(r"\b(?:ticket|tiket|issue|historia|bug|incidencia|jira)\b", f):
            if (r := _need("jira")):
                return r
            what = t[m.start("what"):].strip(" .,:") if m.group("what") else ""
            if not what:
                return {"reply": "¿Cómo se llama el ticket? Dime, por ejemplo: «crea un ticket arreglar el login para el viernes».",
                        "data": {}, "intent": "jira_create"}
            due, summary = parse_when(what, db.now())
            summary = re.sub(r"^(?:que|de|para|sobre)\s+", "", summary.strip(" .,:"), flags=re.I)
            summary = re.sub(r"(?:\s+(?:para|el|la|de|del|a las|a la|antes del?|hasta el))+$", "", summary, flags=re.I).strip(" .,:")
            summary = summary[:1].upper() + summary[1:]
            proj = (m.groupdict().get("proj") or "").upper() or connectors.first("jira").cfg.get("project", "")
            extra = json.dumps({"due": due.strftime("%Y-%m-%dT%H:%M") if due else ""})
            when = f", para {due.strftime('%d/%m')}" if due else ""
            return _draft(session_id, "jira_create", f"Ticket en {proj or 'Jira'}: «{summary}»{when}.",
                          to_name=proj, subject=summary, body="", extra=extra)

        # ---------- Jira: mover / terminar ----------
        m = P_MOVE.match(f) or P_FINISH.match(f)
        if m and (key := find_key(m.group("key"))):
            if (r := _need("jira")):
                return r
            if m.re is P_FINISH:
                verb = f.split()[0]
                target = "en curso" if verb.startswith(("inicia", "empieza")) else "por hacer" if verb.startswith("reabre") else "terminado"
            else:
                target = t[m.start("target"):].strip(" .")
            tr = connectors.first("jira").pick_transition(key, target)
            return _draft(session_id, "jira_move", f"Mover {key} a «{tr['to'] or tr['name']}».", to_addr=key,
                          subject=tr["to"] or tr["name"], extra=json.dumps({"transition_id": tr["id"], "category": tr["category"]}))

        # ---------- Jira: comentar ----------
        m = P_COMMENT.match(f)
        if m and (key := find_key(m.group("key"))):
            if (r := _need("jira")):
                return r
            msg = t[m.start("msg"):].strip()
            msg = msg[:1].upper() + msg[1:]
            return _draft(session_id, "jira_comment", f"Comentario en {key}: «{msg}».", to_addr=key, body=msg)

        # ---------- Jira: info de un ticket ----------
        m = P_TICKET_INFO.match(f)
        if m and (key := find_key(m.group("key"))) and connectors.first("jira"):
            it = connectors.first("jira").issue(key)
            desc = (it["notes"] or "").split("\n")[0][:220]
            due = f" Vence el {it['due'][8:10]}/{it['due'][5:7]}." if it.get("due") else ""
            return {"reply": f"{it['text']}. Estado: {it['ext_status']}.{due}" + (f" {desc}" if desc else ""), "data": {}, "intent": "jira_info"}

        # ---------- consultas ----------
        if P_TICKETS.match(f):
            return {"reply": work.work_summary(), "data": {"tasks": db.list_tasks()}, "intent": "work_tasks"}
        if P_SYNC.match(f):
            if not db.list_connections(only_enabled=True):
                return _need("jira")
            res = connectors.sync_all()
            ok = [r for r in res.values() if r.get("ok")]
            bad = [r for r in res.values() if not r.get("ok")]
            added = sum(r.get("added", 0) for r in ok)
            done = sum(r.get("done", 0) for r in ok)
            msg = f"Sincronizado. {added} nuevo{'s' if added != 1 else ''} y {done} cerrado{'s' if done != 1 else ''}."
            if bad:
                msg += f" Hubo un problema: {bad[0]['error']}"
            return {"reply": msg, "data": {"tasks": db.list_tasks()}, "intent": "sync"}
        if P_PRS.search(f) and connectors.first("github"):
            gh = connectors.first("github")
            rv, mine = gh.reviews(), gh.my_prs()
            parts = []
            parts.append(f"{len(rv)} PR esperando tu revisión" + (": " + "; ".join(p["title"] for p in rv[:3]) if rv else ""))
            parts.append(f"tienes {len(mine)} PR abierto{'s' if len(mine) != 1 else ''}" + (": " + "; ".join(p["title"] for p in mine[:3]) if mine else ""))
            return {"reply": ". ".join(parts) + ".", "data": {}, "intent": "github_prs"}
        m = P_BUILD.search(f)
        if m and connectors.first("github") and re.search(r"\b(?:paso|pasa|fallo|falla|como va|como esta|estado|ultimo|revisa)\b", f):
            gh = connectors.first("github")
            repos = gh.repos()
            want = (m.group("repo") or "").lower()
            pick = [r for r in repos if want and want in r.lower()] or repos
            if not pick:
                return {"reply": "Dime qué repos vigilar en Ajustes → Conexiones → GitHub.", "data": {}, "intent": "github_build"}
            out = []
            for r in pick[:3]:
                b = gh.last_build(r)
                if b:
                    st = {"success": "pasó", "failure": "falló", "cancelled": "se canceló"}.get(b["conclusion"], "sigue corriendo" if b["status"] != "completed" else b["conclusion"])
                    out.append(f"El último build de {r.split('/')[-1]} ({b['branch']}) {st}")
            return {"reply": (". ".join(out) or "No encontré builds recientes") + ".", "data": {}, "intent": "github_build"}

        # ---------- Slack ----------
        m = P_SLACK_SEND.match(f)
        if m:
            if (r := _need("slack")):
                return r
            g = m.groupdict()
            who = g.get("who") or g.get("who2") or (("#" + g["chan"].lstrip("#")) if g.get("chan") else "")
            grp = "msg" if g.get("msg") else "msg2" if g.get("msg2") else "msg3" if g.get("msg3") else None
            msg = t[m.start(grp):].strip() if grp else ""
            whos = "who" if g.get("who") else "who2" if g.get("who2") else None
            if whos:
                who = t[m.start(whos):m.end(whos)].strip()
            if not msg:
                return {"reply": f"¿Qué le escribo a {who} en Slack? Dímelo así: «mándale un Slack a {who} diciendo …».", "data": {}, "intent": "slack_ask"}
            target = connectors.first("slack").find_target(who)
            msg = re.sub(r"^(?:que|de que)\s+", "", msg, flags=re.I)
            msg = msg[:1].upper() + msg[1:]
            return _draft(session_id, "slack", f"Slack para {target['name']}: «{msg}».", to_addr=target["channel"], to_name=target["name"], body=msg)
        if P_SLACK_READ.search(f) and connectors.first("slack"):
            sl = connectors.first("slack")
            men, dms = sl.mentions(5), sl.direct_messages(4)
            parts = []
            if dms:
                parts.append("Mensajes directos: " + "; ".join(f"{d['from']}: {d['text'][:120]}" for d in dms[:3]))
            if men:
                parts.append("Menciones: " + "; ".join(f"{d['from']} en #{d['channel']}: {d['text'][:120]}" for d in men[:3]))
            return {"reply": (". ".join(parts) or "No tienes mensajes nuevos en Slack") + ".", "data": {}, "intent": "slack_read"}
    except ConnectorError as e:
        return {"reply": str(e), "data": {}, "intent": "connector_error"}
    return None


def send(d: dict) -> dict:
    """Ejecuta un borrador de trabajo ya confirmado."""
    extra = json.loads(d.get("extra") or "{}")
    ch = d["channel"]
    if ch == "jira_create":
        due = datetime.fromisoformat(extra["due"]) if extra.get("due") else None
        r = work.create_ticket(d["subject"], d.get("body") or "", due, d.get("to_name") or "")
        return {"ok": True, "message": f"Listo, creé {r['key']} en Jira y lo agregué a tus pendientes de trabajo.", "link": r["link"]}
    if ch == "jira_move":
        j = connectors.first("jira")
        tid = extra.get("transition_id")
        if not tid:
            return {"ok": True, "message": work.move(d["to_addr"], d["subject"])}
        j.transition(d["to_addr"], tid)
        task = db.task_by_ext(j.id, d["to_addr"])
        if task:
            db.update_task(task["id"], ext_status=d["subject"], done=int(extra.get("category") == "done"))
        return {"ok": True, "message": f"Listo, {d['to_addr']} ahora está en «{d['subject']}»."}
    if ch == "jira_comment":
        return {"ok": True, "message": work.comment(d["to_addr"], d["body"])}
    if ch == "slack":
        connectors.first("slack").send(d["to_addr"], d["body"])
        return {"ok": True, "message": f"Listo, le escribí a {d['to_name']} en Slack."}
    raise RuntimeError("Canal desconocido")


def category_from(text: str) -> tuple[str, str]:
    """'agrega un pendiente de trabajo revisar X' → ('trabajo', 'revisar X')."""
    from .intents import fold
    f = fold(text)
    m = P_WORK_TASK.search(f)
    if m:
        return "trabajo", (text[:m.start()] + text[m.end():]).strip(" ,.:")
    m = re.search(r"^personal\b[\s:,]*|\b(?:personal|de la casa|de casa)\b", f)
    if m:
        return "personal", (text[:m.start()] + text[m.end():]).strip(" ,.:")
    return "", text
