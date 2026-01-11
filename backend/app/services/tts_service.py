import os
from pathlib import Path
from uuid import uuid4

import requests
from fastapi import HTTPException

from app.config import OUTPUTS_DIR

def synthesize_to_mp3(text: str, voice_id: str | None = None) -> dict:
    if not text.strip():
        raise HTTPException(status_code=400, detail="Text is required.")

    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="Missing ELEVENLABS_API_KEY.")

    resolved_voice_id = voice_id or os.getenv("ELEVENLABS_VOICE_ID")
    if not resolved_voice_id:
        raise HTTPException(status_code=400, detail="Missing ELEVENLABS_VOICE_ID.")

    run_id = uuid4().hex
    run_dir = Path(OUTPUTS_DIR) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    output_path = run_dir / "voice.mp3"

    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
    }
    headers = {
        "xi-api-key": api_key,
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
    }

    response = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{resolved_voice_id}",
        json=payload,
        headers=headers,
        timeout=60,
    )

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=response.text)

    output_path.write_bytes(response.content)
    return {
        "run_id": run_id,
        "audio_path": f"outputs/{run_id}/voice.mp3",
        "url": f"/outputs/{run_id}/voice.mp3",
    }
