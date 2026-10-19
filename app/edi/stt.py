"""Voz -> texto 100% local con faster-whisper (opcional, ~150 MB extra).
Sólo se usa si construyes la imagen con WITH_WHISPER=true. Por defecto EDI usa el
reconocimiento de voz del navegador, que no consume nada en tu Mac."""
import io

from faster_whisper import WhisperModel  # noqa: F401  (si falla el import, main.py responde 501)

from . import config

_model = None


def transcribe(data: bytes) -> str:
    global _model
    if _model is None:
        _model = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8",
                              download_root=str(config.DATA_DIR / "whisper"))
    segments, _ = _model.transcribe(io.BytesIO(data), language="es", vad_filter=True, beam_size=1)
    return " ".join(s.text.strip() for s in segments).strip()
