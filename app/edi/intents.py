"""Detección de intenciones en español SIN IA (regex). Así la mayoría de las órdenes
cuestan 0 tokens y funcionan aunque no haya internet."""
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional


def fold(s: str) -> str:
    """minúsculas y sin acentos, conservando la longitud del texto (para cortar con índices)."""
    s = unicodedata.normalize("NFC", s)
    out = []
    for ch in s:
        base = unicodedata.normalize("NFD", ch)[0]
        out.append(base.lower() if len(base.lower()) == 1 else ch.lower())
    return "".join(out)


NUM = {"un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
       "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "quince": 15, "veinte": 20,
       "treinta": 30, "cuarenta": 40, "media": 0.5}
DAYS = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
          "octubre", "noviembre", "diciembre"]
NUMRX = r"(\d+|" + "|".join(NUM) + r")"


def _num(tok: str) -> float:
    return float(tok) if tok.isdigit() else NUM.get(tok, 1)


def parse_when(text: str, now: datetime) -> tuple[Optional[datetime], str]:
    """Extrae una fecha/hora en lenguaje natural. Regresa (fecha, texto_sin_la_fecha)."""
    f = fold(text)
    spans = []
    day: Optional[datetime] = None
    hour = minute = None

    m = re.search(rf"\b(?:en|dentro de)\s+{NUMRX}\s+(minutos?|min|horas?|hrs?|dias?|semanas?)\b", f) \
        or re.search(r"\b(?:en|dentro de)\s+(media)\s+(hora)\b", f)
    if m:
        n = _num(m.group(1))
        unit = m.group(2)
        delta = (timedelta(minutes=n) if unit.startswith("min") else
                 timedelta(hours=n) if unit.startswith("h") else
                 timedelta(days=n) if unit.startswith("d") else timedelta(weeks=n))
        spans.append(m.span())
        return now + delta, _cut(text, spans)

    if (m := re.search(r"\bpasado manana\b", f)):
        day, _ = now + timedelta(days=2), spans.append(m.span())
    elif (m := re.search(r"(?<!de la )(?<!en la )(?<!por la )\bmanana\b", f)):
        day, _ = now + timedelta(days=1), spans.append(m.span())
    elif (m := re.search(r"\b(hoy|esta (?:tarde|noche))\b", f)):
        day, _ = now, spans.append(m.span())
        if "tarde" in m.group(1):
            hour = 17
        elif "noche" in m.group(1):
            hour = 20

    if day is None and (m := re.search(r"\b(?:el |este |proximo )?(" + "|".join(DAYS) + r")\b", f)):
        target = DAYS.index(m.group(1))
        ahead = (target - now.weekday()) % 7 or 7
        day = now + timedelta(days=ahead)
        spans.append(m.span())

    if day is None and (m := re.search(r"\b(?:el )?(\d{1,2}) de (" + "|".join(MONTHS) + r")\b", f)):
        d, mo = int(m.group(1)), MONTHS.index(m.group(2)) + 1
        try:
            cand = now.replace(month=mo, day=d)
            if cand.date() < now.date():
                cand = cand.replace(year=now.year + 1)
            day = cand
            spans.append(m.span())
        except ValueError:
            pass

    if (m := re.search(r"\b(?:a las?|alas|a eso de las)\s+(\d{1,2}|" + "|".join(NUM) + r")(?:[:.](\d{2}))?"
                       r"(?:\s*(?:y\s+(media|cuarto)))?"
                       r"\s*(am|pm|a\.?\s?m\.?|p\.?\s?m\.?|de la manana|de la tarde|de la noche|hrs?|horas)?", f)):
        hour = int(_num(m.group(1)))
        minute = int(m.group(2) or 0)
        if m.group(3) == "media":
            minute = 30
        elif m.group(3) == "cuarto":
            minute = 15
        suf = (m.group(4) or "").replace(" ", "").replace(".", "")
        if suf in ("pm", "delatarde", "delanoche") and hour < 12:
            hour += 12
        elif suf in ("am", "delamanana") and hour == 12:
            hour = 0
        elif not suf and 1 <= hour <= 7:
            hour += 12  # "a las 5" casi siempre es de la tarde
        spans.append(m.span())
    elif (m := re.search(r"\bal mediodia\b", f)):
        hour, minute = 12, 0
        spans.append(m.span())
    elif (m := re.search(r"\b(?:en|por|de) la (manana|tarde|noche)\b", f)):
        hour, minute = {"manana": 9, "tarde": 17, "noche": 20}[m.group(1)], 0
        spans.append(m.span())

    if day is None and hour is None:
        return None, text
    base = day or now
    if hour is None:
        hour, minute = 9, 0
    result = base.replace(hour=hour, minute=minute or 0, second=0, microsecond=0)
    if day is None and result <= now:
        result += timedelta(days=1)
    return result, _cut(text, spans)


def _cut(text: str, spans) -> str:
    for a, b in sorted(spans, reverse=True):
        text = text[:a] + " " + text[b:]
    return re.sub(r"\s{2,}", " ", text).strip(" ,.")


@dataclass
class Intent:
    name: str
    text: str = ""
    when: Optional[datetime] = None
    ref: Optional[int] = None
    raw: str = field(default="", repr=False)


WAKE = re.compile(r"^\s*(oye\s+|hey\s+|ok\s+)?(edi|eddie|edy|eddy|heidi)\b[\s,.:!]*", re.I)

RULES = [
    ("repeat", r"^(repite|repitelo|otra vez|que dijiste|repetir|vuelve a decir)"),
    ("help", r"^(ayuda|que puedes hacer|que sabes hacer|comandos)"),
    ("time", r"\bque hora es\b"),
    ("date", r"\b(que dia es|que fecha es)"),
    ("briefing", r"^(resumen|dame (el|un|mi) resumen|que tengo (hoy|pendiente)|mis pendientes|pendientes|"
                 r"buenos dias|buenas tardes|buenas noches|reporte|informe)"),
    ("settings_mail", r"\b(agrega|agregar|registra|registrar|conecta|conectar|configura|configurar|anade|anadir|nueva|nuevo|otra|otro)\b.*\b(cuenta|correo|email|mail)\b"),
    ("settings_ai", r"\b(agrega|registra|configura|cambia|conecta)\w*\b.*\b(api ?key|llave|proveedor|modelo|omniroute|groq|openrouter|gemini)\b"),
    ("mail", r"\b(correos?|emails?|mails?|bandeja|inbox|mensajes nuevos)\b"),
    ("weather", r"\b(clima|temperatura|grados|pronostico|va a llover|llovera|hace (frio|calor))\b"),
    ("exchange", r"\b(precio|cotizacion|tipo de cambio|cuanto (esta|vale|cuesta)|a como esta)\b.*\b(dolar|dolares|euro|euros|libra|yen|yuan|bitcoin|peso colombiano|peso argentino|real)\b|\btipo de cambio\b"),
    ("complete", r"^(ya (hice|termine|acabe|complete)|completa(r)?|marca(r)? (como )?(hecha|lista|completada)|"
                 r"tacha(r)?|termine)\b"),
    ("delete_task", r"^(borra|elimina|quita|cancela)(r)? (la )?(tarea|recordatorio|pendiente)"),
    ("delete_note", r"^(borra|elimina|olvida)(r)? (la )?nota"),
    ("list_tasks", r"^(mis tareas|que tengo que hacer|lista de tareas|tareas|ver tareas|recordatorios)\b"),
    ("add_task", r"^((ok(ay)?|oye|bueno|y)\s*,?\s*)?((quiero|necesito) que )?(me recuerdes|recuerdame|no me dejes olvidar)|^(recuerdame|recordarme|recordar(me)? que|avisame|agrega(r)? (una )?(tarea|pendiente)|"
                 r"anota (una )?tarea|tengo que|nueva tarea|pon(me)? (un )?recordatorio)"),
    ("add_note", r"^(recuerda que|anota que|guarda que|no olvides que|apunta que|memoriza que|toma nota)"),
    ("recall", r"^(que te dije|que recuerdas|que sabes|que anote|que guarde|busca en (tu memoria|mis notas))"),
    ("list_notes", r"^(mis notas|que (cosas )?recuerdas$|que tienes guardado)"),
    ("search", r"^(busca(me|r)?|investiga(me)?|googlea|consulta|averigua|dime que dice internet)\b|\b(en (la )?(web|internet|google))\b|^(cual es el precio|cuanto cuesta|cuanto vale|quien gano|que paso (con|en)|noticias|ultimas noticias|resultado del)\b"),
    ("greet", r"^(hola|que tal|como estas|hey)\b"),
]

STRIP = {
    "add_task": r"^((ok(ay)?|oye|bueno|y)\s*,?\s*)?((quiero|necesito) que )?(me recuerdes|no me dejes olvidar)\s*(que|de|para)?\s*(el dia de )?|^(tengo que\s+|recuerdame|recordarme|recordar(me)? que|avisame|agrega(r)? (una )?(tarea|pendiente)|anota (una )?tarea|"
                r"nueva tarea|pon(me)? (un )?recordatorio)\s*(que|de|para|:)?\s*",
    "add_note": r"^(recuerda que|anota que|guarda que|no olvides que|apunta que|memoriza que|toma nota( de)?( que)?)\s*:?\s*",
    "search": r"^(busca(me|r)?|investiga(me)?|googlea|consulta|averigua|dime que dice internet)\s*(en (la )?(web|internet|google))?\s*(sobre|de|el|la|los|las|que|cual|cuanto)?\s*",
    "recall": r"^(que te dije|que recuerdas|que sabes|que anote|que guarde|busca en (tu memoria|mis notas))\s*(de|del|sobre|acerca de|con)?\s*",
    "complete": r"^(ya (hice|termine|acabe|complete)|completa(r)?|marca(r)? (como )?(hecha|lista|completada)|tacha(r)?|termine)\s*(la )?(tarea)?\s*(de |del |el |la )?",
}


def detect(text: str, now: datetime) -> Intent:
    text = WAKE.sub("", text.strip())
    f = fold(text).strip(" ¿?¡!.")
    f_clean = re.sub(r"^(por favor|porfa|oye)\s*,?\s*", "", f)
    offset = len(f) - len(f_clean)
    for name, rx in RULES:
        if re.search(rx, f_clean):
            body = text[offset:] if offset else text
            body = body.strip(" ¿?¡!.")
            if name in STRIP:
                m = re.match(STRIP[name], fold(body))
                if m:
                    body = body[m.end():]
            intent = Intent(name, body.strip(" ,.:"), raw=text)
            if name in ("add_task",):
                intent.when, intent.text = parse_when(intent.text, now)
                intent.text = re.sub(r"^(que|de|para)\s+", "", intent.text, flags=re.I)
                intent.text = re.sub(r"^tengo que\s+", "", intent.text, flags=re.I)
            if name in ("complete", "delete_task", "delete_note"):
                n = re.search(r"\b(\d+)\b", f_clean)
                intent.ref = int(n.group(1)) if n else None
            return intent
    if not f_clean:
        return Intent("greet", raw=text)
    return Intent("chat", text, raw=text)
