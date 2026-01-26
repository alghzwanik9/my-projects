from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from pathlib import Path
import uuid

from app.services.script_service import build_script_output
from app.services.tts_service import tts_generate
from app.services.pexels_video_service import download_stock_clips
from tools.render_shorts import render
from app.config import OUTPUTS_DIR

router = APIRouter()


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    duration: int = Field(ge=15, le=60)
    language: str = Field(pattern="^(ar|en)$")
    tone: str = Field(min_length=1)
    max_clips: int = Field(default=2, ge=0, le=6)  # اختياري


@router.post("/generate")
def generate_video(payload: GenerateRequest) -> dict:
    try:
        run_id = uuid.uuid4().hex[:12]
        run_dir = Path(OUTPUTS_DIR) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # 1) Script (Gemini)
        script_out = build_script_output(
            prompt=payload.prompt,
            duration=payload.duration,
            language=payload.language,
            tone=payload.tone,
        )

        # النص النهائي
        text = (script_out.get("script") or script_out.get("text") or "").strip()
        if not text:
            raise ValueError("Script text is empty")

        # 2) حفظ السكربت لأن render_shorts يعتمد على script.txt
        script_path = run_dir / "script.txt"
        script_path.write_text(text, encoding="utf-8")

        # 3) TTS -> voice.mp3
        audio_path = run_dir / "voice.mp3"
        tts_generate(text, audio_path, language=payload.language)

        # 4) Pexels clips (اختياري)
        if payload.max_clips > 0:
            clips_dir = run_dir / "clips"
            clips_dir.mkdir(parents=True, exist_ok=True)
            terms = [payload.prompt, text[:60]]
            download_stock_clips(terms, clips_dir, max_clips=payload.max_clips)

        # 5) Render -> short.mp4
        out_video = run_dir / "short.mp4"
        render(audio_path, script_path, out_video)

        return {
            "run_id": run_id,
            "video_url": f"/outputs/{run_id}/short.mp4",
            "script": script_out,
        }

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
