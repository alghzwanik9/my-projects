import os
from uuid import uuid4
from pathlib import Path

import requests
from fastapi import HTTPException

from app.config import OUTPUTS_DIR


def synthesize_to_mp3(text: str, voice_id: str | None = None) -> dict:
    text = (text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is required.")

    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise HTTPException(status_code=400, detail="Missing ELEVENLABS_API_KEY.")

    resolved_voice_id = (voice_id or os.getenv("ELEVENLABS_VOICE_ID") or "").strip()
    if not resolved_voice_id:
        raise HTTPException(status_code=400, detail="Missing ELEVENLABS_VOICE_ID.")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{resolved_voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"ElevenLabs request failed: {e}")

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=resp.text)

    run_id = uuid4().hex
    out_dir = Path(OUTPUTS_DIR) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    out_file = out_dir / "voice.mp3"
    out_file.write_bytes(resp.content)

    return {
        "run_id": run_id,
        "audio_path": f"outputs/{run_id}/voice.mp3",
        "url": f"/outputs/{run_id}/voice.mp3",
    }
