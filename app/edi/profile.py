"""v0.8: EDI te conoce. Entrevista corta la primera vez (quién eres, a qué te dedicas, qué proyectos
llevas) y, de ahí en adelante, va aprendiendo solo de lo que dices en la plática — sin que tengas que
decirle "recuerda que...". Todo queda editable/visible en /api/profile."""
import json
import logging
import re

from . import db, providers

log = logging.getLogger("edi.profile")

QUESTIONS = [
    ("nombre", "¿Cómo te llamas, o cómo quieres que te diga?"),
    ("ocupacion", "¿A qué te dedicas? Por ejemplo tu carrera o tu trabajo."),
    ("proyectos", "¿Qué proyectos tienes en este momento, aunque sea por encimita?"),
]

# zero-tokens: frases con "soy/trabajo en/mi proyecto es..." se guardan directo, sin pasar por la IA
_HINTS = {
    "ocupacion": re.compile(r"\b(?:soy|trabajo (?:de|como|en)|me dedico a|estudio)\s+(?P<v>.+)", re.I),
    "proyectos": re.compile(r"\b(?:mi proyecto es|mis proyectos son|estoy haciendo|ando en|llevo)\s+(?P<v>.+)", re.I),
}


def needs_onboarding() -> bool:
    return db.profile_is_empty()


def onboarding_step(session_id: int) -> dict | None:
    """Si falta algún dato básico, regresa la siguiente pregunta de la entrevista; si no, None."""
    have = db.get_profile()
    for key, q in QUESTIONS:
        if key not in have:
            return {"reply": q, "data": {"onboarding": key}, "intent": "onboarding"}
    return None


def save_onboarding_answer(key: str, text: str):
    if key in dict(QUESTIONS) or key == "notas_perfil":
        db.set_profile(key, text.strip())


def learn_from_text(text: str) -> str | None:
    """0 tokens: si la frase trae pistas directas de ocupación/proyecto, las guarda sin pasar por la IA.
    Regresa la llave que guardó, o None."""
    for key, rx in _HINTS.items():
        m = rx.search(text)
        if m:
            v = m.group("v").strip(" .,")
            if v and len(v) < 200:
                db.set_profile(key, v)
                return key
    return None


def context_snippet() -> str:
    """Lo que EDI sabe de ti, para meterlo al contexto de la plática (como lo haría alguien que te conoce)."""
    p = db.get_profile()
    if not p:
        return ""
    parts = []
    if p.get("nombre"):
        parts.append(f"Se llama {p['nombre']}")
    if p.get("ocupacion"):
        parts.append(f"se dedica a {p['ocupacion']}")
    if p.get("proyectos"):
        parts.append(f"sus proyectos actuales: {p['proyectos']}")
    if p.get("notas_perfil"):
        parts.append(p["notas_perfil"])
    return "Sobre el usuario: " + "; ".join(parts) + "." if parts else ""
