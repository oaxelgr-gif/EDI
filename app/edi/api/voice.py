import asyncio

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from .. import tts

router = APIRouter(prefix="/api", tags=["voz"])


class Speak(BaseModel):
    text: str
    voice: str | None = None
    rate: str | None = None
    pitch: str | None = None


@router.get("/tts/voices")
def voices():
    return tts.VOICES


@router.post("/tts")
async def speak(body: Speak):
    if not body.text.strip():
        raise HTTPException(400, "No hay texto que leer.")
    try:
        audio = await asyncio.wait_for(tts.synth(body.text, body.voice, body.rate, body.pitch), timeout=20)
    except Exception as e:
        raise HTTPException(503, f"Voz en línea no disponible: {e}")
    return Response(audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


@router.post("/tts/start")
async def tts_start(body: Speak):
    jid = tts.start(body.text, body.voice, body.rate, body.pitch)
    if not jid:
        raise HTTPException(503, "Voz en línea no disponible.")
    return {"id": jid}


@router.get("/tts/stream/{jid}")
async def tts_stream(jid: str):
    """MP3 progresivo: el navegador empieza a reproducir con los primeros fragmentos."""
    if not tts.has_job(jid):
        raise HTTPException(404, "Ese audio ya caducó.")
    return StreamingResponse(tts.stream(jid), media_type="audio/mpeg",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@router.post("/stt")
async def stt(audio: UploadFile = File(...)):
    try:
        from ..stt import transcribe
    except ImportError:
        raise HTTPException(501, "Whisper no está instalado; usa Chrome o Safari para dictar.")
    return {"text": await asyncio.to_thread(transcribe, await audio.read())}
