from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from uuid import uuid4
from pathlib import Path
import asyncio
import traceback

from gtts import gTTS

router = APIRouter()

# outputs داخل backend دائمًا
OUTPUTS_DIR = Path(__file__).resolve().parents[2] / "outputs"

class TTSRequest(BaseModel):
    text: str

@router.post("/api/tts")
async def tts(req: TTSRequest):
    try:
        if not req.text or not req.text.strip():
            raise HTTPException(status_code=400, detail="text is required")

        run_id = uuid4().hex
        out_dir = OUTPUTS_DIR / run_id
        out_dir.mkdir(parents=True, exist_ok=True)

        out_path = out_dir / "voice.mp3"

        def _save():
            t = gTTS(text=req.text, lang="ar")
            t.save(str(out_path))

        await asyncio.to_thread(_save)

        return {
            "run_id": run_id,
            "audio_path": str(out_path),
            "url": f"/outputs/{run_id}/voice.mp3",
            "engine": "gTTS",
        }

    except HTTPException:
        raise
    except Exception as e:
        print("[TTS] ERROR:", repr(e))
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"TTS exception: {type(e).__name__}: {e}")

