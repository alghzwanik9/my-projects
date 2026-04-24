# المسار: backend/app/routers/generate.py
import importlib
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# تأكد أن هذا الملف موجود: backend/app/config.py
from app.config import OUTPUTS_DIR
from app.services.scene_planner import plan_scenes
from app.services.script_service import build_script_output

router = APIRouter()
logger = logging.getLogger("shorts")

# --- Helper Classes ---
class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    duration: int = Field(ge=15, le=60)
    language: str = Field(pattern="^(ar|en)$")
    tone: str = Field(min_length=1)
    max_clips: int = Field(default=0, ge=0, le=12)
    enable_auto_montage: bool = True

# --- Helper Functions ---

def _optional_import(module_name: str):
    if importlib.util.find_spec(module_name) is None:
        return None
    return importlib.import_module(module_name)

def _ffprobe_duration(audio_path: Path) -> float:
    try:
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
            return 0.0
        return float(result.stdout.strip())
    except Exception:
        return 0.0

def _dedupe_terms(terms: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for term in terms:
        if not term: continue
        term = term.strip()
        if not term or term in seen: continue
        seen.add(term)
        cleaned.append(term)
    return cleaned

def download_stock_clips(terms: str | list[str], output_dir: Path, max_clips: int = 1) -> list[Path]:
    """ تحميل فيديوهات عالية الجودة مع تفضيل الفيديوهات العمودية """
    api_key = os.getenv("pXJwXJnHtlKyazOWj0dIcG7E7szx7BhqHekDvwVCu5I5GBwZXu88K7Mc")
    if not api_key:
        return []

    requests = _optional_import("requests")
    if requests is None:
        return []

    term_list = _dedupe_terms([terms] if isinstance(terms, str) else list(terms))
    if not term_list:
        return []

    headers = {"Authorization": api_key}
    output_dir.mkdir(parents=True, exist_ok=True)

    # إضافة كلمات لتحسين البحث عن فيديوهات عمودية
    final_terms = []
    for t in term_list:
        final_terms.append(t)
        if "vertical" not in t.lower():
            final_terms.append(t + " vertical")

    for term in final_terms:
        params = {"query": term, "per_page": max_clips + 2, "orientation": "portrait", "size": "medium"} 
        try:
            response = requests.get("https://api.pexels.com/videos/search", headers=headers, params=params, timeout=10)
        except Exception:
            continue

        if not response.ok:
            continue

        data = response.json()
        clips: list[Path] = []
        
        for idx, video in enumerate(data.get("videos", [])):
            video_files = video.get("video_files", [])
            if not video_files: continue
            
            # البحث عن أفضل جودة (تفضيل HD وتجنب 4K الثقيل)
            best_file = None
            candidates = [
                f for f in video_files 
                if (f.get("height", 0) >= 1080 or f.get("width", 0) >= 1080)
                and f.get("quality") != "uhd"
            ]
            
            if candidates:
                best_file = max(candidates, key=lambda x: x.get("width", 0) * x.get("height", 0))
            else:
                best_file = max(video_files, key=lambda x: x.get("width", 0) * x.get("height", 0))

            file_url = best_file.get("link")
            if not file_url: continue

            try:
                clip_resp = requests.get(file_url, stream=True, timeout=60) 
                if not clip_resp.ok: continue
                
                out_path = output_dir / f"clip_{uuid4().hex[:8]}.mp4"
                with open(out_path, 'wb') as f:
                    for chunk in clip_resp.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                if out_path.stat().st_size > 50000:
                    clips.append(out_path)
            except Exception as e:
                print(f"Download error: {e}")
                continue

            if len(clips) >= max_clips:
                break
        
        if clips:
            return clips
    return []

# --- Main Endpoint ---

@router.post("/generate")
def generate_video_script(payload: GenerateRequest) -> dict:
    try:
        # 1. Generate Script
        result = build_script_output(
            prompt=payload.prompt,
            duration=payload.duration,
            language=payload.language,
            tone=payload.tone,
        )
        
        # إذا لم يطلب مونتاج، أعد النص فقط
        if payload.max_clips <= 0:
            return result

        run_id = uuid4().hex
        out_dir = OUTPUTS_DIR / run_id
        out_dir.mkdir(parents=True, exist_ok=True)

        text = result["script"]
        audio_path = out_dir / "voice.mp3"

        # 2. TTS Generation
        tts_module = _optional_import("app.services.tts_service")
        tts_success = False
        
        if tts_module is not None:
            try:
                tts_module.generate_speech_sync(text, audio_path)
                tts_success = True
            except Exception:
                tts_success = False

        # Fallback to gTTS
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

        # Get Audio Duration
        audio_dur = _ffprobe_duration(audio_path)
        if audio_dur <= 0:
            audio_dur = float(payload.duration)

        scenes_path: Path | None = None
        clips_dir: Path | None = None

        # 3. Auto Montage Logic
        if payload.enable_auto_montage and payload.max_clips > 0:
            scenes_payload = plan_scenes(text, audio_dur, max_scenes=payload.max_clips)
            
            scenes_path = out_dir / "scenes.json"
            scenes_path.write_text(json.dumps(scenes_payload, ensure_ascii=False, indent=2), encoding="utf-8")

            clips_dir = out_dir / "clips"
            clips_dir.mkdir(parents=True, exist_ok=True)
            
            last_success: Path | None = None
            downloaded_any = False

            for scene in scenes_payload.get("scenes", []):
                scene_index = int(scene.get("i", 0) or 0)
                scene_folder = clips_dir / f"scene_{scene_index:02d}"
                scene_folder.mkdir(parents=True, exist_ok=True)
                
                query = scene.get("query", "")
                terms = _dedupe_terms([query, payload.prompt])
                
                download_stock_clips(terms, scene_folder, max_clips=1)
                
                scene_clips = sorted(scene_folder.rglob("*.mp4"))
                if scene_clips:
                    last_success = scene_clips[0]
                    downloaded_any = True
                elif last_success and last_success.exists():
                    copied = scene_folder / last_success.name
                    shutil.copy(last_success, copied)
                    scene_clips = [copied]

            if not downloaded_any:
                clips_dir = None

        result.update({
            "run_id": run_id,
            "audio_path": str(audio_path),
            "scenes_path": str(scenes_path) if scenes_path else None,
            "clips_dir": str(clips_dir) if clips_dir else None,
        })
        return result

    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))