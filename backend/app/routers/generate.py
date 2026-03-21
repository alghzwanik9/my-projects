import importlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import OUTPUTS_DIR
from app.services.scene_planner import plan_scenes
from app.services.script_service import build_script_output

router = APIRouter()


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    duration: int = Field(ge=15, le=60)
    language: str = Field(pattern="^(ar|en)$")
    tone: str = Field(min_length=1)
    max_clips: int = Field(default=0, ge=0, le=12)


def _ffprobe_duration(audio_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    return float(result.stdout.strip())


def _optional_import(module_name: str):
    if importlib.util.find_spec(module_name) is None:
        return None
    return importlib.import_module(module_name)


def download_stock_clips(query: str, output_dir: Path, max_clips: int = 1) -> list[Path]:
    """
    Best-effort stock clip downloader.
    Uses Pexels if PEXELS_API_KEY is configured; otherwise returns empty list.
    """
    api_key = os.getenv("PEXELS_API_KEY")
    if not api_key:
        return []

    requests = _optional_import("requests")
    if requests is None:
        return []

    headers = {"Authorization": api_key}
    params = {"query": query, "per_page": max_clips, "orientation": "portrait"}
    try:
        response = requests.get("https://api.pexels.com/videos/search", headers=headers, params=params, timeout=30)
    except Exception:
        return []

    if not response.ok:
        return []

    data = response.json()
    output_dir.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []
    for idx, video in enumerate(data.get("videos", [])):
        files = video.get("video_files", [])
        if not files:
            continue
        file_url = max(files, key=lambda f: f.get("width", 0)).get("link")
        if not file_url:
            continue
        try:
            clip_resp = requests.get(file_url, timeout=60)
        except Exception:
            continue
        if not clip_resp.ok:
            continue
        out_path = output_dir / f"clip_{idx + 1:02d}.mp4"
        out_path.write_bytes(clip_resp.content)
        clips.append(out_path)
        if len(clips) >= max_clips:
            break

    return clips


@router.post("/generate")
def generate_video_script(payload: GenerateRequest) -> dict:
    try:
        result = build_script_output(
            prompt=payload.prompt,
            duration=payload.duration,
            language=payload.language,
            tone=payload.tone,
        )
        if payload.max_clips <= 0:
            return result

        run_id = uuid4().hex
        out_dir = OUTPUTS_DIR / run_id
        out_dir.mkdir(parents=True, exist_ok=True)

        text = result["script"]
        audio_path = out_dir / "voice.mp3"

        tts_module = _optional_import("app.services.tts_service")
        tts_success = False
        if tts_module is not None:
            try:
                tts_module.generate_speech_sync(text, audio_path)
                tts_success = True
            except Exception:
                tts_success = False

        if not tts_success:
            gtts_module = _optional_import("gtts")
            if gtts_module is not None:
                try:
                    gtts_module.gTTS(text=text, lang=payload.language).save(str(audio_path))
                    tts_success = True
                except Exception:
                    tts_success = False

        if not tts_success:
            raise HTTPException(status_code=500, detail="Failed to generate audio.")

        audio_dur = _ffprobe_duration(audio_path)
        scenes_payload = plan_scenes(text, audio_dur, max_scenes=payload.max_clips)

        scenes_path = out_dir / "scenes.json"
        scenes_path.write_text(json.dumps(scenes_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        clips_dir = out_dir / "clips"
        clips_dir.mkdir(parents=True, exist_ok=True)
        last_success: Path | None = None
        downloaded_any = False

        for scene in scenes_payload.get("scenes", []):
            scene_index = scene.get("i", 0)
            scene_folder = clips_dir / f"scene_{scene_index:02d}"
            scene_folder.mkdir(parents=True, exist_ok=True)
            query = scene.get("query", "")

            clips = download_stock_clips(query, scene_folder, max_clips=1)
            if clips:
                last_success = clips[0]
                downloaded_any = True
            elif last_success and last_success.exists():
                shutil.copy(last_success, scene_folder / last_success.name)

        if not downloaded_any:
            clips_dir = None

        result.update({
            "run_id": run_id,
            "audio_path": str(audio_path),
            "scenes_path": str(scenes_path),
            "clips_dir": str(clips_dir) if clips_dir else None,
        })
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
