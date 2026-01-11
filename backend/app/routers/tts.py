from fastapi import APIRouter
from pydantic import BaseModel

from app.services.tts_service import synthesize_to_mp3

router = APIRouter(tags=["tts"])


class TTSRequest(BaseModel):
    text: str
    voice_id: str | None = None


@router.post("/tts")
def tts(req: TTSRequest) -> dict:
    return synthesize_to_mp3(req.text, req.voice_id)
