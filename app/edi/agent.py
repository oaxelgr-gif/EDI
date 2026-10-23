"""Cerebro de EDI. Primero reglas locales (0 tokens); la IA sólo para resumir y conversar.
Cada respuesta puede incluir una `action` para la interfaz (p. ej. abrir el formulario de correo)."""
import logging
import re
import time
from datetime import datetime

import json

from . import db, drafts, files, mail, phrasing, profile, providers, web, whatsapp
from .drafts import P_CANCEL, P_CONFIRM
from .intents import fold
from .intents import detect

log = logging.getLogger("edi.agent")

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]

_mail_cache = {"t": 0.0, "data": None}
_last_reply: dict[int, str] = {}


def human_time(dt: datetime) -> str:
    h = dt.strftime("%-I") if dt.minute == 0 else dt.strftime("%-I:%M")
    periodo = ("de la madrugada" if dt.hour < 6 else "de la mañana" if dt.hour < 12 else
               "del mediodía" if dt.hour < 13 else "de la tarde" if dt.hour < 19 else "de la noche")
    return f"{h} {periodo}"


def human_dt(dt: datetime) -> str:
    today = db.now().date()
    delta = (dt.date() - today).days
    hora = human_time(dt)
    if delta == 0:
        return f"hoy a las {hora}"
    if delta == 1:
        return f"mañana a las {hora}"
    if 0 < delta < 7:
        return f"el {DIAS[dt.weekday()]} a las {hora}"
    return f"el {dt.day} de {MESES[dt.month - 1]} a las {hora}"


def get_mail(force: bool = False) -> dict:
    if force or not _mail_cache["data"] or time.time() - _mail_cache["t"] > 120:
        _mail_cache["data"] = mail.fetch_unread()
        _mail_cache["t"] = time.time()
    return _mail_cache["data"]


def invalidate_mail():
    _mail_cache["data"] = None


def tasks_text(tasks) -> str:
    if not tasks:
        return "No tienes pendientes."
    parts = []
    for t in tasks[:6]:
        due = f", {human_dt(datetime.fromisoformat(t['due']))}" if t["due"] else ""
        parts.append(f"{t['text']}{due}")
    extra = f", y {len(tasks) - 6} más" if len(tasks) > 6 else ""
    n = len(tasks)
    return f"Tienes {n} pendiente{'s' if n != 1 else ''}: " + "; ".join(parts) + extra + "."


# ---------------- pendientes y memoria: seguimiento y respaldo con IA ----------------
TIME_WORDS = re.compile(r"\b(recordatorio|recuerdame|recuerdes|avisame|agenda\w*|programa\w*|alarma|aviso)\b")
MEMO_HINT = re.compile(r"\b(recordatorio|recuerd\w*|record\w*|agend\w*|pendiente|tarea|memoria|acuerd\w*|anot\w*|apunt\w*|olvid\w*|guard\w*|memoriz\w*)\b")
NO_DATE = re.compile(r"^(sin (fecha|hora|dia)|nada|no|ninguna?|asi (esta )?bien|solo (anotalo|apuntalo|guardalo)|cuando sea|no importa|da igual)\b")


def _save_task(text: str, when, category: str = "") -> str:
    from .work_voice import category_from
    cat, text = (category, text) if category else category_from(text)
    cat = cat or "personal"
    due = when.strftime("%Y-%m-%dT%H:%M") if when else None
    when_txt = human_dt(when) if when else ""
    dup = next((t for t in db.list_tasks() if fold(t["text"]) == fold(text) and (t["due"] or None) == due), None)
    if dup:
        tail = f", {when_txt}." if when else "."
        return phrasing.pick_for(None, "task_dup", phrasing.TASK_DUP).format(text=text, when=tail)
    db.add_task(text, when, category=cat)
    where = "pendientes de trabajo" if cat == "trabajo" else "tus pendientes"
    tail = phrasing.pick_for(None, "task_reminder", phrasing.TASK_SAVED_REMINDER).format(when=when_txt) if when else "."
    base = phrasing.pick_for(None, "task_saved", phrasing.TASK_SAVED).format(where=where, text=text, when="")
    return base.rstrip(".") + tail


def _set_task_await(session_id: int, text: str):
    import json
    from .work_voice import category_from
    cat, text = category_from(text)
    db.run("INSERT INTO settings(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
           (f"_await_task_{session_id}", json.dumps({"text": text, "cat": cat, "at": db.iso(), "tries": 0})))


def _task_followup(text: str, intent, session_id: int, now) -> dict | None:
    """Respuesta a «¿Para cuándo te lo recuerdo?»."""
    import json
    from datetime import timedelta
    from .intents import parse_when
    if not session_id:
        return None
    key = f"_await_task_{session_id}"
    r = db.one("SELECT value FROM settings WHERE key=?", (key,))
    if not r:
        return None
    d = json.loads(r["value"])
    if now - datetime.fromisoformat(d["at"]) > timedelta(minutes=10):
        db.run("DELETE FROM settings WHERE key=?", (key,))
        return None
    f = fold(text).strip(" ¿?¡!.")
    if re.match(r"^(cancela\w*|olvidalo|mejor no|no lo (agendes|anotes))\b", f):
        db.run("DELETE FROM settings WHERE key=?", (key,))
        return {"reply": phrasing.pick_for(session_id, "task_when_cancel", phrasing.TASK_WHEN_CANCEL)}
    when, _rest = parse_when(text, now)
    if when:
        db.run("DELETE FROM settings WHERE key=?", (key,))
        return {"reply": _save_task(d["text"], when, d.get("cat") or "personal")}
    if NO_DATE.match(f):
        db.run("DELETE FROM settings WHERE key=?", (key,))
        return {"reply": _save_task(d["text"], None, d.get("cat") or "personal")}
    if intent.name != "chat" or d.get("tries", 0) >= 1:   # cambió de tema: lo guardo sin fecha para no perderlo
        db.run("DELETE FROM settings WHERE key=?", (key,))
        db.add_task(d["text"], None, category=d.get("cat") or "personal")
        return None
    d["tries"] = 1
    db.run("UPDATE settings SET value=? WHERE key=?", (json.dumps(d), key))
    return {"reply": phrasing.pick_for(session_id, "task_when_bad", phrasing.TASK_WHEN_BAD)}


BRAIN_PROMPT = (
    "Eres el router de EDI, un asistente personal en español de México. El usuario te habla de forma coloquial, "
    "sin frases exactas; tu trabajo es entender QUÉ quiere y, si pide algo chato puedes resolverlo tú mismo con una "
    "respuesta conversacional. Responde SIEMPRE con SOLO un JSON, sin texto antes ni después:\n"
    '{"action": "add_task|add_note|complete_task|delete_task|wa_read|wa_summary|image|file_summary|file_edit|chat", '
    '"text": "lo esencial (qué anotar/completar/buscar/dibujar), corto, sin fecha", '
    '"when": "fecha/hora tal como la dijo, o vacío", '
    '"who": "a quién (persona de WhatsApp) si aplica, o vacío", '
    '"filename": "nombre o pista del archivo si pide leer/resumir/corregir uno, o vacío", '
    '"reply": "SÓLO si action es \'chat\': tu respuesta normal, como seguirías la plática"}\n'
    "Guía: add_task = algo que hacer o que le recuerden. add_note = un dato suelto para recordar. "
    "complete_task/delete_task = terminar o quitar un pendiente que ya existe (usa 'text' para identificarlo). "
    "wa_read = quiere leer/ver mensajes de WhatsApp de alguien ('who'). wa_summary = quiere que le resumas esa "
    "conversación de WhatsApp. image = pide que le generes/dibujes/crees una imagen (pon la descripción en 'text'). "
    "file_summary = pide que le resumas/leas/digas qué dice un archivo/PDF/Word suyo. "
    "file_edit = pide que corrijas, programes o escribas algo DENTRO de un archivo suyo. "
    "Si nada de eso aplica y sólo es plática, pregunta o comentario: chat, y contesta de verdad en 'reply' "
    "siguiendo tu personalidad de siempre y los datos disponibles."
)


# v0.8.1: el modelo gratis (chico, rápido) a veces no logra aislar bien el campo "who" en frases sueltas
# y mete ahí pedazos de la frase entera o del propio prompt ("leer mensajes", "qué tal los mensajes de...").
# En vez de dejar que eso llegue a buscar contactos (y te conteste con nombres absurdos), se descarta y EDI
# pregunta — más confiable que forzar al modelo chico a acertar siempre a la primera.
_WHO_BAD = {"mensaje", "mensajes", "whatsapp", "wasap", "guasap", "chat", "conversacion", "queria", "quiero",
            "ver", "que", "tal", "onda", "dijiste", "dijo", "escribio", "leer", "lee", "leeme", "resumen",
            "resume", "ultimos", "ultimo", "nuevos", "tengo", "tenia"}


def _clean_who(raw: str) -> str:
    w = (raw or "").strip(" .,:;¿?¡!")
    if not w:
        return ""
    words = fold(w).split()
    if not words or len(words) > 4 or any(x in _WHO_BAD for x in words):
        return ""
    return w


def _brain(text: str, session_id: int, now) -> dict | None:
    """El cerebro de EDI (v0.8): en vez de reglas fijas, la IA entiende la frase con todo el contexto
    (pendientes, notas, apodos, perfil, plática reciente) y decide qué hacer — y si sólo es plática,
    responde ella misma en la misma llamada (no gasta dos)."""
    from .intents import parse_when
    hist = db.session_messages(session_id, 10)[:-1] if session_id else []
    ctx_hist = "\n".join(f"{'Usuario' if h['role'] == 'user' else 'EDI'}: {h['text'][:200]}" for h in hist[-8:])
    notes = db.search_notes(text, 3)
    tasks = db.list_tasks()[:6]
    nick = db.list_nicknames()
    nick_txt = "; ".join(f"{n['alias']}={n['real_name']}" for n in nick)
    ctx = (profile.context_snippet() + "\n"
           + (f"Pendientes: {'; '.join(t['text'] for t in tasks)}\n" if tasks else "")
           + (f"Notas relevantes: {'; '.join(x['text'] for x in notes)}\n" if notes else "")
           + (f"Apodos conocidos: {nick_txt}\n" if nick else "")
           + f"Conversación reciente:\n{ctx_hist}")
    out, prov = providers.chat(text, context=ctx, system=BRAIN_PROMPT, max_tokens=320)
    if not out:
        return None
    try:
        j = json.loads(out[out.index("{"): out.rindex("}") + 1])
    except Exception:
        return None
    act = j.get("action") or "chat"
    what = (j.get("text") or "").strip(" .")

    if act == "chat":
        reply = (j.get("reply") or "").strip()
        return {"reply": reply, "intent": "chat", "provider": prov} if reply else None

    if act == "add_note":
        if not what:
            return None
        if any(fold(x["text"]) == fold(what) for x in db.list_notes(50)):
            return {"reply": phrasing.pick_for(session_id, "note_dup", phrasing.NOTE_DUP).format(text=what), "intent": "add_note"}
        db.add_note(what)
        return {"reply": phrasing.pick_for(session_id, "note_saved", phrasing.NOTE_SAVED).format(text=what), "intent": "add_note"}

    if act == "add_task":
        if not what:
            return None
        when, _ = parse_when(j.get("when") or "", now) if j.get("when") else (None, "")
        if not when and TIME_WORDS.search(fold(text + " " + what)):
            _set_task_await(session_id, what)
            return {"reply": phrasing.pick_for(session_id, "task_when_q", phrasing.TASK_WHEN_Q).format(text=what), "intent": "add_task"}
        return {"reply": _save_task(what, when), "intent": "add_task"}

    if act == "complete_task":
        t = db.find_task(what) if what else None
        reply = phrasing.pick_for(session_id, "task_complete", phrasing.TASK_COMPLETE).format(text=t["text"]) \
            if t and db.complete_task(t["id"]) else \
            phrasing.pick_for(session_id, "task_complete_fail", phrasing.TASK_COMPLETE_FAIL)
        return {"reply": reply, "intent": "complete"}

    if act == "delete_task":
        t = db.find_task(what) if what else None
        ok = t and db.delete_task(t["id"])
        reply = phrasing.pick_for(session_id, "task_deleted", phrasing.TASK_DELETED) if ok else \
            phrasing.pick_for(session_id, "task_delete_fail", phrasing.TASK_DELETE_FAIL)
        return {"reply": reply, "intent": "delete_task"}

    if act in ("wa_read", "wa_summary"):
        who = _clean_who(j.get("who") or "")
        if not who:
            return drafts.ask_who_read(session_id, 5, act == "wa_summary")
        return drafts.read_chat(session_id, who, 5, summary=(act == "wa_summary"))

    if act == "image":
        if not what:
            return None
        return _generate_image(what, session_id)

    if act in ("file_summary", "file_edit"):
        name = (j.get("filename") or what or "").strip()
        if not name:
            return {"reply": "¿De cuál archivo? Dime el nombre tal como lo tienes guardado.", "intent": "file_summary"}
        cands = files.find(name)
        if not cands:
            return {"reply": f"No encontré ningún archivo que se llame {name} en tu carpeta de EDI.", "intent": "file_summary"}
        if len(cands) > 1:
            return {"reply": "Encontré varios: " + ", ".join(c["name"] for c in cands) + ". ¿Cuál?", "intent": "file_summary"}
        rel = cands[0]["rel"]
        if act == "file_summary":
            out, prov2 = files.summarize(rel, session_id, what if what != name else "")
            return {"reply": out or f"No pude leer {rel}.", "intent": "file_summary", "provider": prov2}
        return files.propose_edit(rel, what or text, session_id)

    return None


def _generate_image(prompt: str, session_id: int) -> dict:
    """v0.8: 'genérame una imagen de...' -> Gemini (Nano Banana) la crea y EDI la manda directo al chat."""
    png, err = providers.generate_image(prompt)
    if err == "sin_llave_gemini":
        return {"reply": "Para generar imágenes necesito una llave de Gemini activa. Te abro Ajustes → Inteligencia.",
                "intent": "image", "action": {"open": "settings", "tab": "ai"}}
    if not png:
        log.warning("generate_image: %s", err)
        if err and "503" in err:
            reply = "Gemini está saturado ahorita con la generación de imágenes; dale otra vez en un rato."
        elif err and "429" in err:
            reply = "Se acabó la cuota gratis de imágenes de Gemini por hoy; vuelve a intentar mañana."
        else:
            reply = "No pude generar la imagen ahora; intenta de nuevo en un rato."
        return {"reply": reply, "intent": "image"}
    name = f"{db.iso().replace(':', '-')}.png"
    from . import config
    (config.IMAGES_DIR / name).write_bytes(png)
    db.add_image(session_id or 0, prompt, name)
    return {"reply": f"Aquí tienes: {prompt}.", "intent": "image", "data": {"image_url": f"/api/images/{name}"}}


SKIP_ONBOARD = re.compile(r"^(?:no|paso|salta(?:lo)?|despues|luego|ahorita no|al rato|otro dia|otro rato)\b")


def _onboard_pending(session_id: int) -> str | None:
    r = db.one("SELECT value FROM settings WHERE key=?", (f"_onboard_{session_id}",))
    return r["value"] if r else None


def _onboard_set(session_id: int, key: str | None):
    k = f"_onboard_{session_id}"
    if key:
        db.run("INSERT INTO settings(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, key))
    else:
        db.run("DELETE FROM settings WHERE key=?", (k,))


def _onboard_followup(text: str, session_id: int) -> dict | None:
    """v0.8: entrevista inicial de EDI (quién eres, a qué te dedicas, qué proyectos llevas). Se hace una
    sola vez; si no la respondes, EDI no vuelve a insistir sola. También la arranca si el perfil está vacío."""
    if not session_id:
        return None
    key = _onboard_pending(session_id)
    if key:
        if not SKIP_ONBOARD.match(fold(text).strip()):
            profile.save_onboarding_answer(key, text)
        else:
            profile.save_onboarding_answer(key, "")  # queda "contestada" (vacía) para no insistir con lo mismo
        nxt = profile.onboarding_step(session_id)
        if nxt:
            _onboard_set(session_id, nxt["data"]["onboarding"])
            return nxt
        _onboard_set(session_id, None)
        return {"reply": "Listo, ya te ubico mejor. Conforme platiquemos voy aprendiendo el resto solo.",
                "intent": "onboarding"}
    if profile.needs_onboarding() and not db.one("SELECT 1 FROM settings WHERE key=?", (f"_onboard_done_{session_id}",)):
        step = profile.onboarding_step(session_id)
        if step:
            _onboard_set(session_id, step["data"]["onboarding"])
            db.run("INSERT INTO settings(key, value) VALUES(?,'1') ON CONFLICT(key) DO NOTHING",
                   (f"_onboard_done_{session_id}",))
            step["reply"] = ("Para ubicarte mejor, déjame hacerte unas preguntas rápidas (puedes decir «paso» "
                             "si no quieres ahorita). " + step["reply"])
            return step
    return None


def _file_edit_followup(text: str, session_id: int) -> dict | None:
    """Confirmación de un cambio de archivo que EDI ya propuso ('¿lo guardo?')."""
    if not session_id:
        return None
    pend = db.pending_file_edit(session_id)
    if not pend:
        return None
    f = fold(text).strip()
    if P_CONFIRM.match(f):
        return files.apply_edit(pend["id"])
    if P_CANCEL.match(f):
        return files.discard_edit(pend["id"])
    return None


def agenda_text(f: str, now) -> str:
    """«¿Qué tengo mañana?», «mi agenda de esta semana», «¿qué tengo el viernes?»."""
    from datetime import timedelta
    from .intents import parse_when
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if "semana" in f or f in ("mi agenda", "agenda"):
        start, end = (today + timedelta(days=7 - today.weekday()), today + timedelta(days=14 - today.weekday())) if "proxima" in f \
            else (today, today + timedelta(days=7))
        label = "la próxima semana" if "proxima" in f else "los próximos 7 días"
    elif "fin de semana" in f or "este fin" in f:
        start = today + timedelta(days=(5 - today.weekday()) % 7)
        end, label = start + timedelta(days=2), "el fin de semana"
    else:
        when, _ = parse_when(f, now)
        start = (when or now).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        label = "hoy" if start == today else "mañana" if start == today + timedelta(days=1) else \
            f"el {DIAS[start.weekday()]} {start.day}"
    items = [t for t in db.list_tasks() if t["due"] and start <= datetime.fromisoformat(t["due"]) < end]
    items.sort(key=lambda t: t["due"])
    if not items:
        return f"No tienes nada agendado para {label}."
    multi = (end - start).days > 1
    parts = [f"{t['text']}, " + (human_dt(datetime.fromisoformat(t["due"])) if multi else
             human_time(datetime.fromisoformat(t["due"]))) for t in items[:8]]
    return f"Para {label} tienes {len(items)}: " + "; ".join(parts) + "."


def _saludo(now) -> str:
    return "Buenas noches" if now.hour < 5 else "Buenos días" if now.hour < 12 else "Buenas tardes" if now.hour < 19 else "Buenas noches"


def greeting() -> dict:
    """Al abrir EDI: el primer saludo del día trae el resumen (clima, pendientes, correo, WhatsApp);
    los demás son un saludo corto."""
    now = db.now()
    s = db.all_settings()
    user = s["user_name"]
    today = now.date().isoformat()
    last = db.one("SELECT value FROM settings WHERE key='_last_brief'")
    if last and last["value"] == today:
        return {"reply": f"{_saludo(now)}, {user}. ¿En qué puedo ayudarlo?", "intent": "greet_short", "data": {}}
    db.run("INSERT INTO settings(key, value) VALUES('_last_brief', ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (today,))
    parts, data = [f"{_saludo(now)}, {user}."], {}
    city = s.get("home_city") or ""
    if city:
        try:
            w = web.weather_brief(city)
            if w:
                parts.append(w)
        except Exception as e:
            log.warning("clima del saludo: %s", e)
    tasks = db.list_tasks()
    data["tasks"] = tasks
    hoy = [t for t in tasks if t["due"] and datetime.fromisoformat(t["due"]).date() <= now.date() and t.get("category") != "trabajo"]
    if hoy:
        parts.append(f"Para hoy tiene {len(hoy)} pendiente{'s' if len(hoy) != 1 else ''}: " +
                     "; ".join(f"{t['text']}, {human_dt(datetime.fromisoformat(t['due']))}" for t in hoy[:3]) + ".")
    elif tasks:
        parts.append(f"Tiene {len(tasks)} pendiente{'s' if len(tasks) != 1 else ''}, ninguno para hoy.")
    extras = []
    if mail.list_accounts(only_enabled=True):
        try:
            m = get_mail()
            data["mail"] = m
            if m.get("total"):
                extras.append(f"{m['total']} correo{'s' if m['total'] != 1 else ''} sin leer")
        except Exception as e:
            log.warning("correo del saludo: %s", e)
    try:
        if whatsapp.status().get("state") == "open":
            total, cs = whatsapp.unread_summary()
            if total:
                extras.append(f"mensajes nuevos en {len(cs)} chat{'s' if len(cs) != 1 else ''} de WhatsApp")
    except Exception:
        pass
    if extras:
        parts.append("Tiene " + " y ".join(extras) + ".")
    try:
        from . import connectors
        work_today = [t for t in tasks if t.get("category") == "trabajo" and t["due"] and datetime.fromisoformat(t["due"]).date() <= now.date()]
        if work_today:
            parts.append(f"En el trabajo vencen hoy {len(work_today)}: " + "; ".join(t["text"] for t in work_today[:3]) + ".")
        b = connectors.briefing()
        if b:
            parts.append("Además, " + " y ".join(b) + ".")
    except Exception as e:
        log.info("trabajo en el saludo: %s", e)
    parts.append("¿En qué puedo ayudarlo?")
    return {"reply": " ".join(parts), "intent": "greet_daily", "data": data}


def mail_text(data: dict, summarize: bool = True) -> tuple[str, str | None]:
    accounts = data["accounts"]
    if not accounts:
        return "Todavía no tengo cuentas de correo. Te abro el formulario para que registres una.", None
    total = data["total"]
    errors = [a["name"] for a in accounts if a["error"]]
    per = ", ".join(f"{a['unread_total']} en {a['name']}" for a in accounts if not a["error"])
    msg = f"Tienes {total} correo{'s' if total != 1 else ''} sin leer" + (f": {per}." if per else ".")
    if errors:
        msg += f" No pude entrar a {', '.join(errors)}."
    if total and summarize and providers.active():
        resumen, prov = providers.chat("Resume en máximo 3 frases qué correos parecen importantes o urgentes y cuáles "
                                       "son promociones.", context=mail.compact_for_llm(data), max_tokens=200)
        if resumen:
            return msg + " " + resumen, prov
    if total:
        top = [it for a in accounts for it in a["items"]][:3]
        msg += " Lo más reciente: " + "; ".join(f"{it['from']}, {it['subject']}" for it in top) + "."
    return msg, None


def handle(text: str, session_id: int, log_it: bool = True) -> dict:
    now = db.now()
    s = db.all_settings()
    user = s["user_name"]
    intent = detect(text, now)
    n = intent.name
    log.info("intent=%s text=%r", n, intent.text)
    if log_it:
        db.log_message(session_id, "user", text)
    data, action, prov = {}, None, None

    # v0.8: seguimientos con prioridad (apodo nuevo de WhatsApp aparte, en drafts) - estos dos van primero
    # porque la siguiente frase del usuario suele ser literalmente la respuesta a lo que EDI preguntó.
    fe = _file_edit_followup(text, session_id)
    if fe:
        if log_it:
            db.log_message(session_id, "edi", fe["reply"])
        _last_reply[session_id] = fe["reply"]
        fe.setdefault("data", {}); fe.setdefault("action", None); fe.setdefault("provider", None)
        return fe
    if n not in ("repeat",):
        ob = _onboard_followup(text, session_id)
        if ob:
            if log_it:
                db.log_message(session_id, "edi", ob["reply"])
            _last_reply[session_id] = ob["reply"]
            ob.setdefault("action", None); ob.setdefault("provider", None)
            return ob

    pend_task = _task_followup(text, intent, session_id, now)
    if pend_task:
        if log_it:
            db.log_message(session_id, "edi", pend_task["reply"])
        _last_reply[session_id] = pend_task["reply"]
        return {"intent": "add_task", "data": {"tasks": db.list_tasks()}, "action": None, "provider": None, **pend_task}

    # 0 tokens: si la frase trae pistas directas de ocupación/proyecto, las aprende sin pasar por la IA
    if n == "chat":
        profile.learn_from_text(text)

    comms = drafts.handle(text, session_id) if n not in ("repeat",) else None
    if comms is None and n == "chat":
        brain = _brain(text, session_id, now)
        if brain:
            if log_it:
                db.log_message(session_id, "edi", brain["reply"], brain.get("provider") or "")
            _last_reply[session_id] = brain["reply"]
            brain.setdefault("data", {}); brain.setdefault("action", None); brain.setdefault("provider", None)
            brain["data"].setdefault("tasks", db.list_tasks())
            return brain
    if comms is None and (n == "chat" or (n == "search" and drafts.COMMS_HINT.search(fold(text)))
                          or (n in ("greet", "mail", "search", "weather") and drafts.has_context(session_id))):
        comms = drafts.fallback(text, session_id)
    if comms:
        _last_reply[session_id] = comms["reply"]
        if log_it:
            db.log_message(session_id, "edi", comms["reply"])
        comms.setdefault("action", None)
        comms.setdefault("provider", None)
        return comms

    if n == "repeat":
        return {"reply": _last_reply.get(session_id) or "Todavía no he dicho nada.", "intent": n, "data": {},
                "repeat": True}

    if n == "help":
        reply = ("Puedo darte tu resumen del día, revisar todas tus cuentas de correo, guardar pendientes con aviso, "
                 "por ejemplo: recuérdame pagar la luz mañana a las 5. También recuerdo lo que me digas con "
                 "'recuerda que', y lo busco con 'qué te dije de'. Para agregar un correo o una llave de IA, pídemelo.")
    elif n == "time":
        reply = f"{'Es la' if now.strftime('%-I') == '1' else 'Son las'} {human_time(now)}."
    elif n == "date":
        reply = f"Hoy es {DIAS[now.weekday()]} {now.day} de {MESES[now.month - 1]} de {now.year}."
    elif n == "greet":
        g = greeting()
        reply, data = g["reply"], g["data"]
    elif n == "briefing":
        saludo = "Buenos días" if now.hour < 12 else "Buenas tardes" if now.hour < 19 else "Buenas noches"
        tasks = db.list_tasks()
        data["tasks"] = tasks
        parts = [f"{saludo}, {user}.", tasks_text(tasks)]
        if mail.list_accounts(only_enabled=True):
            try:
                m = get_mail()
                data["mail"] = m
                t, prov = mail_text(m, summarize=(n == "briefing"))
                parts.append(t)
            except Exception as e:
                parts.append(f"No pude revisar el correo: {e}")
        reply = " ".join(parts)
    elif n == "exchange":
        code = web.find_currency(text) or "USD"
        try:
            reply = web.exchange(code)
        except Exception as e:
            log.warning("exchange: %s", e)
            reply = "No pude consultar el tipo de cambio en este momento. Revisa la conexión a internet."
    elif n == "weather":
        city = web.find_city(intent.text) or s.get("home_city") or ""
        if not city:
            reply = "¿De qué ciudad quieres el clima? Puedes fijar tu ciudad en Ajustes."
        else:
            try:
                reply = web.weather(city, tomorrow="manana" in fold(text) and "en la manana" not in fold(text))
            except Exception as e:
                log.warning("weather: %s", e)
                reply = "No pude consultar el clima ahora. Revisa la conexión a internet."
    elif n == "search":
        query = intent.text or text
        ctx, sources = web.research(query)
        data["sources"] = sources
        if not sources:
            reply = "No encontré resultados en la web para eso, o no hay conexión a internet."
        else:
            ans, prov = providers.chat(
                f"Con base en estos resultados de búsqueda de hoy ({now:%d/%m/%Y}), responde a: {query}. "
                "Da el dato concreto primero, en 1 a 3 frases. Si los resultados no lo dicen, dilo.",
                context=ctx, max_tokens=220)
            reply = ans or f"Esto encontré: {sources[0]['title']}. {sources[0]['snippet']}"
    elif n == "settings_mail":
        reply = "Claro. Te abro el registro de correos: elige el proveedor, escribe tu correo y la contraseña de aplicación."
        action = {"open": "settings", "tab": "mail", "new": True}
    elif n == "settings_ai":
        reply = "Te abro la sección de inteligencia. Ahí puedes agregar OmniRoute u otra llave y ordenar las prioridades."
        action = {"open": "settings", "tab": "ai", "new": True}
    elif n == "mail":
        if not mail.list_accounts(only_enabled=True):
            reply = "Todavía no tengo cuentas de correo. Te abro el formulario para que registres una."
            action = {"open": "settings", "tab": "mail", "new": True}
        else:
            m = get_mail(force=True)
            data["mail"] = m
            reply, prov = mail_text(m)
    elif n == "add_task":
        if not intent.text:
            reply = "¿Qué quieres que te recuerde?"
        elif not intent.when and TIME_WORDS.search(fold(text)):
            _set_task_await(session_id, intent.text)
            from .work_voice import category_from
            reply = phrasing.pick_for(session_id, "task_when_q", phrasing.TASK_WHEN_Q).format(text=category_from(intent.text)[1])
        else:
            reply = _save_task(intent.text, intent.when)
            data["tasks"] = db.list_tasks()
    elif n == "agenda":
        reply = agenda_text(fold(text), now)
        data["tasks"] = db.list_tasks()
    elif n == "list_tasks":
        data["tasks"] = db.list_tasks()
        reply = tasks_text(data["tasks"])
    elif n == "complete":
        t = None
        if intent.ref:
            t = next((x for x in db.list_tasks() if x["id"] == intent.ref), None)
        elif intent.text:
            t = db.find_task(intent.text)
        reply = phrasing.pick_for(session_id, "task_complete", phrasing.TASK_COMPLETE).format(text=t["text"]) \
            if t and db.complete_task(t["id"]) else \
            phrasing.pick_for(session_id, "task_complete_fail", phrasing.TASK_COMPLETE_FAIL)
        data["tasks"] = db.list_tasks()
    elif n == "delete_task":
        ok = intent.ref and db.delete_task(intent.ref)
        reply = phrasing.pick_for(session_id, "task_deleted", phrasing.TASK_DELETED) if ok else \
            phrasing.pick_for(session_id, "task_delete_fail", phrasing.TASK_DELETE_FAIL)
        data["tasks"] = db.list_tasks()
    elif n == "add_note":
        if intent.text and any(fold(x["text"]) == fold(intent.text) for x in db.list_notes(50)):
            reply = phrasing.pick_for(session_id, "note_dup", phrasing.NOTE_DUP).format(text=intent.text)
        elif intent.text:
            db.add_note(intent.text)
            reply = phrasing.pick_for(session_id, "note_saved", phrasing.NOTE_SAVED).format(text=intent.text)
        else:
            reply = "¿Qué quieres que recuerde?"
    elif n == "delete_note":
        ok = intent.ref and db.delete_note(intent.ref)
        reply = phrasing.pick_for(session_id, "note_forgot", phrasing.NOTE_FORGOT) if ok else \
            phrasing.pick_for(session_id, "note_forgot_fail", phrasing.NOTE_FORGOT_FAIL)
    elif n == "list_notes" or (n == "recall" and not intent.text):
        notes = db.list_notes(8)
        reply = ("Lo último que me pediste recordar: " + "; ".join(x["text"] for x in notes) + "."
                 if notes else "Aún no tengo nada guardado. Dime 'recuerda que…' y lo anoto.")
    elif n == "recall":
        notes = db.search_notes(intent.text)
        if not notes:
            reply = f"No tengo nada guardado sobre {intent.text}."
        elif len(notes) == 1 or not providers.active():
            reply = "Me dijiste: " + "; ".join(x["text"] for x in notes[:3]) + "."
        else:
            ans, prov = providers.chat(f"¿Qué me dijiste sobre {intent.text}?", max_tokens=150,
                                       context="\n".join(f"- ({x['created'][:10]}) {x['text']}" for x in notes))
            reply = ans or ("Me dijiste: " + notes[0]["text"])
    else:
        notes = db.search_notes(intent.text, 3)
        tasks = db.list_tasks()[:5]
        ctx = (f"Fecha y hora: {now:%Y-%m-%d %H:%M}\n"
               + ("Notas relevantes:\n" + "\n".join("- " + x["text"] for x in notes) + "\n" if notes else "")
               + ("Pendientes:\n" + "\n".join("- " + x["text"] for x in tasks) if tasks else ""))
        history = db.session_messages(session_id, 12)[:-1] if session_id else []
        if re.search(r"\b(hoy|actual|actualmente|ultim[oa]s?|precio|cuanto cuesta|noticias?|202\d|esta semana)\b", fold(intent.text)):
            web_ctx, sources = web.research(intent.text)   # datos frescos para preguntas de actualidad
            if sources:
                ctx += "\nResultados web de hoy:\n" + web_ctx
                data["sources"] = sources
        ans, prov = providers.chat(intent.text, context=ctx, history=history)
        if ans:
            reply = ans
        elif not providers.active():
            reply = "No tengo ningún proveedor de IA activo. Te abro Ajustes para agregar uno."
            action = {"open": "settings", "tab": "ai"}
        else:
            reply = phrasing.pick_for(session_id, "no_providers", phrasing.NO_PROVIDERS)

    _last_reply[session_id] = reply
    if log_it:
        db.log_message(session_id, "edi", reply, prov or "")
    return {"reply": reply, "intent": n, "data": data, "action": action, "provider": prov}
