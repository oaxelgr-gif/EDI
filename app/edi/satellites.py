"""v0.9 (frente 8): EDI puede leer, resumir, programar y correr comandos aprobados también en OTROS
dispositivos (p. ej. tu Mac), aunque el cerebro/la IA corran centralizados en el server (p. ej. Windows).

Cada dispositivo adicional corre `satellite/edi_satellite.py` (un programa chiquito, sin dependencias
pesadas) que expone una API muy pequeña, protegida con una clave secreta, y que SÓLO puede tocar UNA
carpeta autorizada que tú elegiste ahí — el mismo principio que files.py ya usa en el server. El server
nunca sabe ni le importa dónde vive esa carpeta; sólo habla con el satélite por HTTP.

Seguridad, igual de estricta que con los archivos locales:
- Nunca se escribe nada de verdad sin tu confirmación (reutiliza la tabla file_edits y el mismo flujo
  de "¿lo guardo?" que ya usas con archivos locales y correo/WhatsApp).
- Los comandos que puede correr un satélite están en una lista blanca QUE VIVE EN EL SATÉLITE, no aquí:
  aunque el modelo de IA alucine un nombre de comando, el satélite lo rechaza si no está en su lista.
- Si el satélite está apagado o no contesta, EDI te lo dice claro — nunca finge que lo hizo.
"""
import difflib
import logging
from pathlib import Path

import httpx

from . import db, providers

log = logging.getLogger("edi.satellites")

TIMEOUT = 12.0
RUN_TIMEOUT = 70.0
CODE_EXT = {".py", ".js", ".ts", ".java", ".c", ".cpp", ".go", ".rb", ".php", ".sh", ".sql"}


class SatelliteError(Exception):
    """Mensaje ya listo para decirle al usuario (sin tecnicismos)."""


def _headers(sat: dict) -> dict:
    return {"X-EDI-Secret": sat["secret"]}


def _url(sat: dict, path: str) -> str:
    return f"{sat['url'].rstrip('/')}{path}"


def ping(sat: dict) -> tuple[bool, str]:
    try:
        r = httpx.get(_url(sat, "/health"), headers=_headers(sat), timeout=6.0)
        if r.status_code == 401:
            return False, "La clave secreta no coincide con la del satélite."
        r.raise_for_status()
        j = r.json()
        return True, f"Conectado · carpeta: {j.get('folder_label') or j.get('folder') or 'desconocida'}"
    except httpx.TimeoutException:
        return False, "No contestó a tiempo (¿está prendido el satélite y en esa red?)."
    except httpx.ConnectError:
        return False, "No pude conectar (¿está prendido el satélite y en esa red?)."
    except Exception as e:
        return False, f"{e.__class__.__name__}: {e}"


# ---------------- elegir el dispositivo que mencionó el usuario ----------------
_DEVICE_BAD = {"servidor", "server", "aqui", "local", "este", "esta", "equipo", "maquina", "pc", "computadora",
               "dispositivo", "nada", "ninguno"}


def _clean_device_hint(raw: str) -> str:
    w = (raw or "").strip(" .,:;¿?¡!").lower()
    if not w or len(w.split()) > 5 or w in _DEVICE_BAD:
        return ""
    return w


def find_device(hint: str) -> dict | None:
    """Busca por nombre aproximado entre los satélites registrados ('mi mac', 'la mac', 'laptop')."""
    h = _clean_device_hint(hint)
    if not h:
        return None
    sats = db.list_satellites(only_enabled=True)
    if not sats:
        return None
    for s in sats:  # exacto o contiene
        n = s["name"].lower()
        if h == n or h in n or n in h:
            return s
    scored = sorted(sats, key=lambda s: -difflib.SequenceMatcher(None, h, s["name"].lower()).ratio())
    best = scored[0]
    return best if difflib.SequenceMatcher(None, h, best["name"].lower()).ratio() >= 0.6 else None


def device_names() -> str:
    sats = db.list_satellites(only_enabled=True)
    return ", ".join(s["name"] for s in sats) if sats else ""


# ---------------- archivos remotos ----------------
def list_remote(sat: dict) -> list[dict]:
    r = httpx.get(_url(sat, "/files"), headers=_headers(sat), timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get("entries", [])


def find_remote(sat: dict, name: str) -> list[dict]:
    """Busca por nombre aproximado en la carpeta autorizada de ese satélite (igual que files.find local)."""
    import re
    q = re.sub(r"[^\w\s.]", " ", name.lower()).strip()
    q_words = [w for w in q.split() if len(w) > 1]
    scored = []
    try:
        entries = [e for e in list_remote(sat) if not e.get("is_dir")]
    except Exception:
        return []
    for f in entries:
        n = f["name"].lower()
        if q == n or q == Path(n).stem:
            sc = 5
        elif q_words and all(w in n for w in q_words):
            sc = 3
        else:
            sc = 2 if difflib.SequenceMatcher(None, q, n).ratio() >= 0.6 else 0
        if sc:
            scored.append((sc, f))
    scored.sort(key=lambda x: -x[0])
    return [f for _, f in scored[:5]]


def read_remote(sat: dict, rel: str, limit: int = 20000) -> str:
    r = httpx.get(_url(sat, "/read"), params={"path": rel}, headers=_headers(sat), timeout=TIMEOUT)
    if r.status_code == 401:
        raise SatelliteError(f"La clave de «{sat['name']}» ya no coincide; revísala en Ajustes → Dispositivos.")
    if r.status_code == 404:
        raise SatelliteError(f"No encontré {rel} en «{sat['name']}».")
    if r.status_code == 400:
        raise SatelliteError(r.json().get("error", "Esa ruta no está permitida."))
    r.raise_for_status()
    return (r.json().get("content") or "")[:limit]


def write_remote(sat: dict, rel: str, content: str) -> None:
    r = httpx.post(_url(sat, "/write"), json={"path": rel, "content": content}, headers=_headers(sat), timeout=TIMEOUT)
    if r.status_code == 401:
        raise SatelliteError(f"La clave de «{sat['name']}» ya no coincide; revísala en Ajustes → Dispositivos.")
    if r.status_code == 400:
        raise SatelliteError(r.json().get("error", "Esa ruta no está permitida."))
    r.raise_for_status()


def _sibling_edi_name(rel: str) -> str:
    p = Path(rel)
    return str(p.with_name(f"{p.stem}_EDI{p.suffix}"))


def summarize(sat: dict, rel: str, session_id: int | None, pregunta: str = "") -> tuple[str | None, str | None]:
    try:
        text = read_remote(sat, rel)
    except SatelliteError as e:
        return str(e), None
    except Exception as e:
        return f"No pude conectar con «{sat['name']}» para leer {rel}: {e}", None
    if not text.strip():
        return f"El archivo {rel} en «{sat['name']}» está vacío o no pude leerle texto.", None
    ask = pregunta or "Resume de qué trata en 3 o 4 frases y dime si parece que piden alguna acción o entrega."
    out, prov = providers.chat(f"{ask}\n\nContenido del archivo «{Path(rel).name}» (en {sat['name']}):\n{text[:8000]}",
                                max_tokens=280)
    return out, prov


def propose_edit(sat: dict, rel: str, instruction: str, session_id: int | None) -> dict:
    """Igual que files.propose_edit, pero leyendo/escribiendo en un dispositivo satélite. Nunca escribe nada
    todavía: guarda el borrador pendiente (misma tabla file_edits) y espera tu «sí»/«cancela»."""
    try:
        current = read_remote(sat, rel)
    except SatelliteError as e:
        return {"reply": str(e), "data": {}, "intent": "file_edit"}
    except Exception as e:
        return {"reply": f"No pude conectar con «{sat['name']}» para leer {rel}: {e}", "data": {}, "intent": "file_edit"}
    ext = Path(rel).suffix.lower()
    tag = "code" if ext in CODE_EXT else "chat"
    prompt = (f"Este es el contenido actual de «{Path(rel).name}» (en el dispositivo {sat['name']}):\n{current[:8000]}\n\n"
              f"Instrucción del usuario: {instruction}\n\n"
              "Responde ÚNICAMENTE con el contenido completo del archivo ya corregido/actualizado, "
              "sin explicaciones antes ni después, sin comillas ni ``` alrededor.")
    out, prov = providers.chat(prompt, max_tokens=1800, tag=tag,
                                system="Eres un asistente de programación/edición de documentos preciso y conservador. "
                                       "Cambias sólo lo que se te pide y mantienes el resto igual.")
    if not out:
        return {"reply": "No logré conectar con ningún proveedor de IA para hacer el cambio.", "data": {}, "intent": "file_edit"}
    preview = "\n".join(difflib.unified_diff(current.splitlines(), out.splitlines(),
                                             fromfile=rel, tofile=_sibling_edi_name(rel), lineterm=""))[:3000]
    eid = db.add_file_edit(session_id or 0, rel, "write", instruction, preview or "(sin cambios detectados)", out,
                           satellite_id=sat["id"])
    lines = len(preview.splitlines())
    return {"reply": f"Ya tengo el cambio listo para {Path(rel).name} en «{sat['name']}» ({lines} líneas de diferencia). "
                     f"¿Lo guardo como {Path(_sibling_edi_name(rel)).name} ahí? Dime «sí» o «cancela».",
            "data": {"file_edit_id": eid, "diff": preview}, "intent": "file_edit", "provider": prov}


def apply_edit(e: dict) -> dict:
    """Aplica un file_edits pendiente que apunta a un satélite (e['satellite_id'] ya viene con valor).
    Llamado desde files.apply_edit, que decide si el edit es local o de satélite."""
    sat = db.get_satellite(e["satellite_id"])
    if not sat or not sat["enabled"]:
        return {"reply": "Ese dispositivo ya no está registrado o está desactivado.", "data": {}, "intent": "file_edit"}
    new_rel = _sibling_edi_name(e["path"])
    try:
        write_remote(sat, new_rel, e["new_content"])
    except SatelliteError as ex:
        return {"reply": str(ex), "data": {}, "intent": "file_edit"}
    except Exception as ex:
        return {"reply": f"No pude guardar el archivo en «{sat['name']}»: {ex}", "data": {}, "intent": "file_edit"}
    db.set_file_edit_status(e["id"], "applied")
    return {"reply": f"Listo, guardé el cambio en {Path(new_rel).name}, junto al original en «{sat['name']}».",
            "data": {"path": new_rel}, "intent": "file_edit"}


# ---------------- comandos de una lista blanca (definida EN el satélite, no aquí) ----------------
def run_remote(sat: dict, cmd: str) -> dict:
    """Pide al satélite correr un comando de SU lista blanca. Nunca inventa que funcionó: regresa
    exactamente lo que el satélite contestó, truncado para que quepa en una respuesta hablada/leída."""
    try:
        r = httpx.post(_url(sat, "/run"), json={"cmd": cmd}, headers=_headers(sat), timeout=RUN_TIMEOUT)
    except httpx.TimeoutException:
        return {"reply": f"«{cmd}» tardó demasiado en «{sat['name']}» y lo corté.", "intent": "device_run"}
    except Exception as e:
        return {"reply": f"No pude conectar con «{sat['name']}»: {e}", "intent": "device_run"}
    if r.status_code == 401:
        return {"reply": f"La clave de «{sat['name']}» ya no coincide; revísala en Ajustes → Dispositivos.", "intent": "device_run"}
    if r.status_code == 403:
        names = r.json().get("allowed") or []
        extra = f" Los comandos permitidos ahí son: {', '.join(names)}." if names else ""
        return {"reply": f"«{cmd}» no está en la lista de comandos aprobados de «{sat['name']}».{extra}",
                "intent": "device_run"}
    try:
        j = r.json()
    except Exception:
        return {"reply": f"«{sat['name']}» contestó algo que no entendí.", "intent": "device_run"}
    out = (j.get("output") or "").strip()[:1200]
    if j.get("ok"):
        return {"reply": f"Listo, corrí «{cmd}» en «{sat['name']}». " + (f"Esto salió: {out}" if out else "Sin salida."),
                "intent": "device_run", "data": {"output": out, "code": j.get("code")}}
    return {"reply": f"«{cmd}» falló en «{sat['name']}» (código {j.get('code')}). " + (out or "Sin más detalle."),
            "intent": "device_run", "data": {"output": out, "code": j.get("code")}}
