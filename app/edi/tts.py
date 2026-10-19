"""Voz de EDI: síntesis neural gratuita en línea con edge-tts (https://github.com/rany2/edge-tts).
El servidor genera MP3 y el navegador lo reproduce: no depende de las voces instaladas en la Mac.
Se guarda en caché (data/tts) para que repetir no vuelva a descargar."""
import hashlib
import logging

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

    voice = voice or db.get_setting("tts_voice") or "es-MX-DaliaNeural"
    rate = rate or db.get_setting("tts_rate") or "+0%"
    pitch = pitch or db.get_setting("tts_pitch") or "+0Hz"
    text = text.strip()[:2500]
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


def _prune(keep: int = 300):
    files = sorted(config.TTS_CACHE.glob("*.mp3"), key=lambda p: p.stat().st_mtime)
    for p in files[:-keep]:
        p.unlink(missing_ok=True)
