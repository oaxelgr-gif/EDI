"""Cliente del puente WhatsApp (contenedor edi-whatsapp, Baileys)."""
import atexit
import logging
import os
import re
import shutil
import subprocess
import tarfile
import threading
import unicodedata
from pathlib import Path

import httpx

from . import config

log = logging.getLogger("edi.whatsapp")

# Con Docker el puente es otro contenedor (EDI_WHATSAPP_URL). En modo nativo EDI lo arranca él mismo,
# sólo cuando lo usas: la primera vez descarga Node portátil (~45 MB) e instala Baileys.
MANAGED = not os.getenv("EDI_WHATSAPP_URL")
PORT = int(os.getenv("EDI_WA_PORT", "3917"))
BASE = os.getenv("EDI_WHATSAPP_URL") or f"http://127.0.0.1:{PORT}"
ROOT = Path(__file__).resolve().parents[2]
WA_DIR = ROOT / "whatsapp"
RUNTIME = ROOT / ".runtime"
NODE_VER = "v22.12.0"
AUTH = config.DATA_DIR / "whatsapp"
LOG = config.DATA_DIR / "whatsapp-bridge.log"

_proc: subprocess.Popen | None = None
_lock = threading.Lock()
_setup = {"busy": False, "msg": "", "error": ""}


def _node() -> str | None:
    local = RUNTIME / "node" / "bin" / "node"
    return str(local) if local.exists() else shutil.which("node")


def _download_node():
    import platform
    arch = "arm64" if platform.machine() == "arm64" else "x64"
    name = f"node-{NODE_VER}-darwin-{arch}"
    url = f"https://nodejs.org/dist/{NODE_VER}/{name}.tar.gz"
    RUNTIME.mkdir(exist_ok=True)
    tgz = RUNTIME / f"{name}.tar.gz"
    _setup["msg"] = "Descargando Node (sólo la primera vez, ~45 MB)…"
    with httpx.stream("GET", url, timeout=120, follow_redirects=True) as r:
        r.raise_for_status()
        with open(tgz, "wb") as f:
            for chunk in r.iter_bytes(1 << 16):
                f.write(chunk)
    _setup["msg"] = "Descomprimiendo Node…"
    with tarfile.open(tgz) as t:
        t.extractall(RUNTIME)
    shutil.rmtree(RUNTIME / "node", ignore_errors=True)
    (RUNTIME / name).rename(RUNTIME / "node")
    tgz.unlink(missing_ok=True)


def _install_and_start():
    global _proc
    try:
        node = _node()
        if not node:
            _download_node()
            node = _node()
        bindir = str(Path(node).parent)
        env = {**os.environ, "PATH": bindir + os.pathsep + os.environ.get("PATH", ""),
               "WA_AUTH_DIR": str(AUTH), "PORT": str(PORT)}
        if not (WA_DIR / "node_modules" / "@whiskeysockets").exists():
            _setup["msg"] = "Instalando el conector de WhatsApp (sólo la primera vez, 1–3 min)…"
            npm = shutil.which("npm", path=env["PATH"]) or str(Path(bindir) / "npm")
            with open(LOG, "ab") as lf:
                rc = subprocess.call([npm, "install", "--omit=dev", "--no-audit", "--no-fund"], cwd=WA_DIR, env=env,
                                     stdout=lf, stderr=subprocess.STDOUT)
            if rc:
                raise RuntimeError("npm install falló (revisa data/whatsapp-bridge.log)")
        AUTH.mkdir(parents=True, exist_ok=True)
        _setup["msg"] = "Arrancando WhatsApp…"
        lf = open(LOG, "ab")
        _proc = subprocess.Popen([node, "index.mjs"], cwd=WA_DIR, env=env, stdout=lf, stderr=subprocess.STDOUT)
        _setup["error"] = ""
    except Exception as e:
        log.exception("puente WhatsApp")
        _setup["error"] = f"No pude preparar WhatsApp: {e}"
    finally:
        _setup["busy"] = False


def linked_before() -> bool:
    return (AUTH / "creds.json").exists()


def ensure_running() -> None:
    """Arranca el puente si no está corriendo (modo nativo)."""
    if not MANAGED:
        return
    with _lock:
        if (_proc and _proc.poll() is None) or _setup["busy"]:
            return
        _setup.update(busy=True, msg="Preparando WhatsApp…", error="")
        threading.Thread(target=_install_and_start, daemon=True).start()


@atexit.register
def stop_bridge():
    if _proc and _proc.poll() is None:
        _proc.terminate()


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", (s or "").lower()) if unicodedata.category(c) != "Mn")


def _get(path: str, **params):
    r = httpx.get(BASE + path, params=params, timeout=8)
    r.raise_for_status()
    return r.json()


def _post(path: str, data: dict):
    r = httpx.post(BASE + path, json=data, timeout=25)
    j = r.json()
    if r.status_code >= 400:
        raise RuntimeError(j.get("error") or f"Error {r.status_code}")
    return j


def status(start: bool = False) -> dict:
    if MANAGED:
        if start or linked_before():
            ensure_running()
        if _setup["error"]:
            return {"state": "offline", "error": _setup["error"]}
        if _setup["busy"]:
            return {"state": "installing", "detail": _setup["msg"]}
        if not (_proc and _proc.poll() is None):
            return {"state": "off"}
    try:
        return _get("/status")
    except Exception as e:
        if MANAGED:
            return {"state": "starting", "detail": "Arrancando WhatsApp…"}
        return {"state": "offline", "error": f"El servicio de WhatsApp no responde ({e.__class__.__name__})."}


def chats(limit: int = 300) -> list:
    return _get("/chats", limit=limit)


def messages(jid: str, limit: int = 30) -> list:
    return _get("/messages", jid=jid, limit=limit)


def send(to: str, text: str) -> dict:
    return _post("/send", {"to": to, "text": text})


def read(jid: str) -> dict:
    return _post("/read", {"jid": jid})


def pair(phone: str) -> dict:
    r = httpx.post(BASE + "/pair", json={"phone": phone}, timeout=30)
    j = r.json()
    if r.status_code >= 400:
        raise RuntimeError(j.get("error") or f"Error {r.status_code}")
    return j


def logout() -> dict:
    return _post("/logout", {})


def contacts() -> list:
    return _get("/contacts")


def _norm(s: str) -> str:
    s = _fold(s)
    s = "".join(ch if ch.isalnum() or ch == " " else " " for ch in s)
    return " ".join(s.split())


_pool_cache = {"t": 0.0, "v": []}


def _pool() -> list:
    """Chats + contactos (caché de 30 s para no consultar el puente en cada intento)."""
    import time
    if time.time() - _pool_cache["t"] > 30:
        seen, pool = set(), []
        for c in chats(500) + contacts():
            if c["jid"] not in seen:
                seen.add(c["jid"])
                pool.append(c)
        _pool_cache.update(t=time.time(), v=pool)
    return _pool_cache["v"]


def find_contacts(name: str) -> list:
    """Busca por nombre aproximado en tu agenda de WhatsApp, chats y grupos ('mamá', 'mi jefa', 'Juan Pérez').
    Regresa los mejores candidatos (normalmente uno)."""
    import difflib
    q = _norm(name)
    q = re.sub(r"^(?:a\s+)?(?:mi|mis|el|la|los|las)\s+", "", q).strip() or q
    if not q:
        return []
    pool = _pool()
    scored = []
    for c in pool:
        n = _norm(c.get("name", ""))
        if not n:
            continue
        words = n.split()
        if n == q:
            sc = 5
        elif n.startswith(q + " ") or (len(q) >= 3 and n.startswith(q)):
            sc = 4
        elif all(any(w.startswith(x) for w in words) for x in q.split()):
            sc = 3
        elif q in n:
            sc = 2
        else:
            r = max([difflib.SequenceMatcher(None, q, n).ratio()] + [difflib.SequenceMatcher(None, q, w).ratio() for w in words])
            sc = 1.5 if r >= 0.7 else 0
        if sc:
            sc += 0.3 if c.get("saved") else 0
            sc += 0.2 if c.get("last") else 0
            sc -= 0.1 if c.get("group") else 0
            scored.append((sc, c))
    scored.sort(key=lambda x: -x[0])
    if not scored:
        return []
    # Misma persona repetida (contacto + chat): quedarse con la que tiene mensajes
    by_name = {}
    for sc, c in scored:
        by_name.setdefault(_norm(c.get("name", "")), []).append((sc, c))
    keep = []
    for group in by_name.values():
        with_chat = [x for x in group if x[1].get("last")]
        keep += with_chat[:1] if len(with_chat) == 1 else group
    scored = sorted(keep, key=lambda x: -x[0])
    top = scored[0][0]
    best = [c for sc, c in scored if sc >= top - 0.25]
    # Con coincidencia exacta o única, no preguntar
    return best[:1] if top >= 5 or len(best) == 1 else best[:4]


def suggest(name: str, k: int = 3) -> list:
    """Nombres parecidos (para '¿Quisiste decir…?') cuando no hubo coincidencia."""
    import difflib
    q = re.sub(r"^(?:a\s+)?(?:mi|mis|el|la|los|las)\s+", "", _norm(name)).strip()
    seen, out = set(), []
    for c in _pool():
        n = _norm(c.get("name", ""))
        if not n or c["jid"] in seen:
            continue
        seen.add(c["jid"])
        r = max([difflib.SequenceMatcher(None, q, n).ratio()] + [difflib.SequenceMatcher(None, q, w).ratio() for w in n.split()])
        if r >= 0.5:
            out.append((r, c))
    out.sort(key=lambda x: -x[0])
    return [c for _, c in out[:k]]


def find_chat(name: str) -> dict | None:
    found = find_contacts(name)
    return found[0] if found else None


def unread_summary() -> tuple[int, list]:
    cs = [c for c in chats(100) if c.get("unread")]
    return sum(c["unread"] for c in cs), cs
