# app/main.py
from __future__ import annotations

import sys
import json
import logging
import uuid
import asyncio
import subprocess
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from app.config import OUTPUTS_DIR

# ✅ Smart scenes planner
from app.services.scene_planner import plan_scenes

# اختياري: توليد سكربت
try:
    from app.services.script_service import generate_script
except Exception:
    generate_script = None

# Edge TTS (اختياري)
try:
    from app.services.tts_service import generate_audio_edge
except Exception:
    generate_audio_edge = None

# Google TTS fallback (اختياري)
try:
    from gtts import gTTS
except Exception:
    gTTS = None

# Pexels + terms (اختياري)
try:
    from app.services.pexels_video_service import download_stock_clips
except Exception:
    download_stock_clips = None

try:
    # هذه غالباً موجودة عندك وتطلع keywords
    from app.services.scene_planner import plan_search_terms
except Exception:
    plan_search_terms = None


# -------------------------------------------------------------------------
# Logging
# -------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# Paths
# -------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parents[1]  # backend/
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

OUTPUT_DIR = Path(OUTPUTS_DIR)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# -------------------------------------------------------------------------
# App
# -------------------------------------------------------------------------
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve outputs
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")
print("SERVING OUTPUTS FROM:", OUTPUTS_DIR)


class VideoRequest(BaseModel):
    topic: str = ""
    text: str = ""
    language: str = "ar"
    images_count: int = 0  # حالياً ما نستخدمها


def _audio_dur_sec(p: Path) -> float:
    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(p),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
    )
    try:
        return float((r.stdout or "0").strip())
    except:
        return 0.0


@app.post("/api/generate-video")
async def generate_video(request: VideoRequest):
    try:
        run_id = uuid.uuid4().hex
        run_dir = OUTPUT_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # -----------------------------
        # (A) النص
        # -----------------------------
        input_text = (request.text or "").strip()

        if not input_text and (request.topic or "").strip() and generate_script:
            logger.info("🧠 Generating script using Gemini...")
            input_text = (generate_script(request.topic) or "").strip()

        if not input_text:
            input_text = (request.topic or "").strip()

        if not input_text:
            raise HTTPException(status_code=422, detail="النص فارغ! الرجاء كتابة نص أو عنوان.")

        logger.info(f"📝 Processing Text: {input_text[:80]}...")

        script_path = run_dir / "script.txt"
        script_path.write_text(input_text, encoding="utf-8")

        # -----------------------------
        # (B) توليد الصوت
        # -----------------------------
        audio_path = run_dir / "voice.mp3"
        audio_generated = False

        if generate_audio_edge:
            try:
                logger.info("🎙️ Attempt 1: Edge TTS (Naayf)...")
                await generate_audio_edge(input_text, str(audio_path), voice="ar-SA-NaayfNeural")
                if audio_path.exists() and audio_path.stat().st_size > 0:
                    audio_generated = True
                    logger.info("✅ Edge TTS Success!")
            except Exception as e:
                logger.warning(f"⚠️ Edge TTS Failed: {e}")

        if not audio_generated and gTTS:
            try:
                logger.info("🎙️ Attempt 2: Google TTS...")
                await asyncio.to_thread(lambda: gTTS(text=input_text, lang="ar").save(str(audio_path)))
                if audio_path.exists() and audio_path.stat().st_size > 0:
                    audio_generated = True
                    logger.info("✅ Google TTS Success!")
            except Exception as e:
                logger.warning(f"⚠️ Google TTS Failed: {e}")

        if not audio_generated:
            raise HTTPException(status_code=500, detail="فشل توليد الصوت (Edge TTS + gTTS).")

        # -----------------------------
        # (B2) Smart Scenes + Clips
        # -----------------------------
        audio_dur = _audio_dur_sec(audio_path)
        if audio_dur <= 0:
            audio_dur = 15.0

        plan = plan_scenes(input_text, total_duration=audio_dur, language=request.language)
        scenes_path = run_dir / "scenes.json"
        scenes_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        
        logger.info(f"[SCENES] saved: {scenes_path}")

        logger.info(f"[SCENES] written: {scenes_path}  scenes={len(plan.get('scenes', []))}")

        # تنزيل clips لكل Scene
        if download_stock_clips and plan_search_terms:
            clips_root = run_dir / "clips"
            clips_root.mkdir(parents=True, exist_ok=True)

            for sc in plan.get("scenes", []):
                scene_id = int(sc.get("id", 1))
                scene_text = sc.get("text", "")

                scene_dir = clips_root / f"scene_{scene_id:02d}"
                scene_dir.mkdir(parents=True, exist_ok=True)

                try:
                    terms = plan_search_terms(scene_text, max_clips=3)
                    logger.info(f"🎞️ Scene {scene_id} terms: {terms}")
                    await asyncio.to_thread(download_stock_clips, terms, scene_dir, 3)
                except Exception as e:
                    logger.warning(f"⚠️ Scene {scene_id} clips skipped: {e}")

            clips_root = run_dir / "clips"
            has_any = any(clips_root.rglob("*.mp4")) if clips_root.exists() else False
            if not has_any:
                raise HTTPException(status_code=500, detail="No Pexels clips downloaded. Montage cannot run.")

        # -----------------------------
        # (C) Render via tools/render_shorts.py
        # -----------------------------
        out_video = run_dir / "shorts.mp4"
        tool_path = BASE_DIR / "tools" / "render_shorts.py"
        python_exec = sys.executable

        clips_dir = run_dir / "clips"
        cmd = [python_exec, str(tool_path), str(audio_path), str(script_path), str(out_video), str(run_dir / "clips")]

        logger.info("🎬 Rendering video (Calling render_shorts.py)...")
        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        if result.stdout:
            print(f"[RENDER LOG]\n{result.stdout[:2000]}")
        if result.stderr:
            print(f"[RENDER ERR]\n{result.stderr[:4000]}")

        if result.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Render Failed: {(result.stderr or '')[-320:]}")

        if not out_video.exists() or out_video.stat().st_size < 50_000:
            raise HTTPException(status_code=500, detail="Render failed: shorts.mp4 not created or too small")

        logger.info(f"✅ Video Created: {out_video}")

        return {
            "run_id": run_id,
            "video_url": f"/outputs/{run_id}/shorts.mp4",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Global Error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
