import asyncio

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
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


@router.post("/stt")
async def stt(audio: UploadFile = File(...)):
    try:
        from ..stt import transcribe
    except ImportError:
        raise HTTPException(501, "Whisper no está instalado; usa Chrome o Safari para dictar.")
    return {"text": await asyncio.to_thread(transcribe, await audio.read())}
