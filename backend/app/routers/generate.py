from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.script_service import build_script_output

router = APIRouter()


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    duration: int = Field(ge=15, le=60)
    language: str = Field(pattern="^(ar|en)$")
    tone: str = Field(min_length=1)


@router.post("/generate")
def generate_video_script(payload: GenerateRequest) -> dict:
    try:
        return build_script_output(
            prompt=payload.prompt,
            duration=payload.duration,
            language=payload.language,
            tone=payload.tone,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
