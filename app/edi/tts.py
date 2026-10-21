"""Voz de EDI: síntesis neural gratuita en línea con edge-tts (https://github.com/rany2/edge-tts).
El servidor genera MP3 y el navegador lo reproduce: no depende de las voces instaladas en la Mac.
Se guarda en caché (data/tts) para que repetir no vuelva a descargar."""
import asyncio
import hashlib
import logging
import re
import time
import uuid

from . import config, db

log = logging.getLogger("edi.tts")

VOICES = [
    {"id": "es-MX-DaliaNeural", "label": "Dalia · México"},
    {"id": "es-MX-JorgeNeural", "label": "Jorge · México"},
    {"id": "es-US-PalomaNeural", "label": "Paloma · EE. UU."},
    {"id": "es-US-AlonsoNeural", "label": "Alonso · EE. UU."},
    {"id": "es-ES-ElviraNeural", "label": "Elvira · España"},
    {"id": "es-ES-AlvaroNeural", "label": "Álvaro · España"},
    {"id": "es-CO-SalomeNeural", "label": "Salomé · Colombia"},
    {"id": "es-AR-ElenaNeural", "label": "Elena · Argentina"},
    {"id": "en-US-AvaMultilingualNeural", "label": "Ava · multilingüe, muy expresiva"},
    {"id": "en-US-EmmaMultilingualNeural", "label": "Emma · multilingüe, cálida"},
    {"id": "fr-FR-VivienneMultilingualNeural", "label": "Vivienne · multilingüe, suave"},
    {"id": "en-US-AndrewMultilingualNeural", "label": "Andrew · multilingüe, masculina"},
]


async def synth(text: str, voice: str | None = None, rate: str | None = None, pitch: str | None = None) -> bytes:
    import edge_tts  # import tardío: si falta, la interfaz usa la voz del navegador

    voice, rate, pitch = _params(voice, rate, pitch)
    text = speakable(text)[:2500]
    key = hashlib.sha1(f"{voice}|{rate}|{pitch}|{text}".encode()).hexdigest()
    config.TTS_CACHE.mkdir(parents=True, exist_ok=True)
    path = config.TTS_CACHE / f"{key}.mp3"
    if path.exists():
        return path.read_bytes()
    audio = bytearray()
    async for chunk in edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).stream():
        if chunk["type"] == "audio":
            audio.extend(chunk["data"])
    if not audio:
        raise RuntimeError("edge-tts no devolvió audio")
    path.write_bytes(audio)
    _prune()
    return bytes(audio)


# ---------------- streaming: la voz empieza a sonar mientras se genera ----------------
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200D]")


def speakable(text: str) -> str:
    """Quita emojis, enlaces y comillas decorativas que no se deben leer en voz alta."""
    t = _EMOJI.sub("", text or "")
    t = re.sub(r"https?://\S+", "", t)
    t = t.replace("«", "").replace("»", "").replace("*", "")
    return re.sub(r"\s{2,}", " ", t).strip()


class _Job:
    """Una frase en síntesis. Una respuesta = varias frases que se generan EN PARALELO y suenan en orden."""
    __slots__ = ("chunks", "done", "error", "event", "created", "first_ms")

    def __init__(self):
        self.chunks: list[bytes] = []
        self.done = False
        self.error = None
        self.event = asyncio.Event()
        self.created = time.time()
        self.first_ms = None


_jobs: dict[str, list] = {}      # id → [partes (_Job)] ; meta en _meta
_meta: dict[str, dict] = {}


def _params(voice, rate, pitch):
    return (voice or db.get_setting("tts_voice") or "es-MX-DaliaNeural", rate or db.get_setting("tts_rate") or "+0%",
            pitch or db.get_setting("tts_pitch") or "+0Hz")


def _split(text: str) -> list[str]:
    """Primera frase sola (suena rapidísimo) y el resto en bloques; todo se sintetiza a la vez."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?…;:])\s+", text) if p.strip()]
    if len(parts) <= 1:
        return [text]
    first = parts[0]
    # si la primera frase es larguísima, córtala en la primera coma para que empiece a sonar antes
    if len(first) > 140 and "," in first[40:]:
        i = first.index(",", 40) + 1
        parts = [first[:i], first[i:].strip()] + parts[1:]
    out, cur = [parts[0]], ""
    for p in parts[1:]:
        if len(cur) + len(p) > 260 and cur:
            out.append(cur)
            cur = p
        else:
            cur = (cur + " " + p).strip()
    if cur:
        out.append(cur)
    return out[:8]


async def _run(job: _Job, text: str, voice: str, rate: str, pitch: str):
    import edge_tts
    t0 = time.perf_counter()
    try:
        async for chunk in edge_tts.Communicate(text, voice, rate=rate, pitch=pitch).stream():
            if chunk["type"] == "audio":
                if job.first_ms is None:
                    job.first_ms = int((time.perf_counter() - t0) * 1000)
                job.chunks.append(chunk["data"])
                job.event.set()
        if not job.chunks:
            job.error = "sin audio"
    except Exception as e:
        log.warning("tts stream: %s", e)
        job.error = str(e)
    finally:
        job.done = True
        job.event.set()


async def _finish(jid: str, parts: list, path):
    """Cuando todas las partes terminan: guarda en caché y registra tiempos."""
    for p in parts:
        while not p.done:
            await asyncio.sleep(0.05)
    if all(p.chunks and not p.error for p in parts):
        path.write_bytes(b"".join(b"".join(p.chunks) for p in parts))
        _prune()
    m = _meta.get(jid, {})
    log.info("voz %s: %d partes · primer audio %s ms · lista en %d ms · el navegador pidió a los %s ms",
             jid[:6], len(parts), parts[0].first_ms, int((time.time() - m.get("t", time.time())) * 1000), m.get("req_ms"))


def start(text: str, voice: str | None = None, rate: str | None = None, pitch: str | None = None) -> str | None:
    """Empieza a generar la voz en segundo plano y regresa un id para escucharla en /api/tts/stream/{id}.
    Debe llamarse desde el event loop."""
    text = speakable(text)[:2500]
    if not text:
        return None
    if (db.get_setting("tts_engine") or "edge") != "edge":
        return None
    voice, rate, pitch = _params(voice, rate, pitch)
    now = time.time()
    for k in [k for k, m in _meta.items() if now - m["t"] > 180]:
        _jobs.pop(k, None)
        _meta.pop(k, None)
    key = hashlib.sha1(f"{voice}|{rate}|{pitch}|{text}".encode()).hexdigest()
    config.TTS_CACHE.mkdir(parents=True, exist_ok=True)
    path = config.TTS_CACHE / f"{key}.mp3"
    jid = uuid.uuid4().hex[:16]
    _meta[jid] = {"t": now}
    if path.exists():
        j = _Job()
        j.chunks.append(path.read_bytes())
        j.done = True
        j.event.set()
        _jobs[jid] = [j]
        return jid
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        _meta.pop(jid, None)
        return None
    loop = asyncio.get_running_loop()
    parts = []
    for piece in _split(text):
        j = _Job()
        parts.append(j)
        loop.create_task(_run(j, piece, voice, rate, pitch))
    _jobs[jid] = parts
    loop.create_task(_finish(jid, parts, path))
    return jid


async def stream(jid: str):
    parts = _jobs.get(jid)
    if not parts:
        return
    m = _meta.get(jid)
    if m is not None and m.get("req_ms") is None:
        m["req_ms"] = int((time.time() - m["t"]) * 1000)
    for job in parts:
        i = 0
        while True:
            while i < len(job.chunks):
                yield job.chunks[i]
                i += 1
            if job.done:
                break
            job.event.clear()
            if i < len(job.chunks) or job.done:
                continue
            try:
                await asyncio.wait_for(job.event.wait(), timeout=15)
            except asyncio.TimeoutError:
                return


def has_job(jid: str) -> bool:
    return jid in _jobs


def _prune(keep: int = 300):
    files = sorted(config.TTS_CACHE.glob("*.mp3"), key=lambda p: p.stat().st_mtime)
    for p in files[:-keep]:
        p.unlink(missing_ok=True)
