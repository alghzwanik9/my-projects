# app/main.py
from __future__ import annotations

import sys
import json
import logging
import uuid
import asyncio
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

from app.config import OUTPUTS_DIR

# ✅ Smart scenes planner
from app.services.scene_planner import plan_scenes

# توليد سكربت عبر Gemini
try:
    from app.services.ai_service import generate_script
except Exception:
    generate_script = None  # type: ignore

# Edge TTS (اختياري)
try:
    from app.services.tts_service import generate_audio_edge
except Exception:
    generate_audio_edge = None  # type: ignore

# Google TTS fallback (اختياري)
try:
    from gtts import gTTS  # type: ignore
except Exception:
    gTTS = None  # type: ignore

# Pexels + terms (اختياري)
try:
    from app.services.pexels_video_service import download_stock_clips
except Exception:
    download_stock_clips = None  # type: ignore

try:
    from app.services.scene_planner import plan_search_terms
except Exception:
    plan_search_terms = None  # type: ignore


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
app = FastAPI(
    title="AI Shorts Generator",
    version="2.0.0",
    description="توليد فيديوهات قصيرة احترافية من نص عربي بالذكاء الاصطناعي",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve outputs
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")
logger.info(f"SERVING OUTPUTS FROM: {OUTPUTS_DIR}")


# -------------------------------------------------------------------------
# Models
# -------------------------------------------------------------------------
class VideoRequest(BaseModel):
    topic: str = Field(default="", description="موضوع الفيديو (اختياري إذا وُجد text)")
    text: str = Field(default="", description="النص الكامل للفيديو")
    language: str = Field(default="ar", description="لغة الصوت: ar أو en")
    images_count: int = Field(default=0, ge=0, le=10)
    voice: Optional[str] = Field(default=None, description="اسم الصوت (edge-tts)")


class CleanupRequest(BaseModel):
    max_age_days: int = Field(default=7, ge=1, le=90)


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------
def _audio_dur_sec(p: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(p)],
        capture_output=True, text=True, encoding="utf-8", errors="ignore",
    )
    try:
        return float((r.stdout or "0").strip())
    except Exception:
        return 0.0


def _list_run_videos() -> list[dict]:
    """يرجع قائمة بجميع الفيديوهات الموجودة مع معلوماتها."""
    videos = []
    for run_dir in sorted(OUTPUT_DIR.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        video = run_dir / "shorts.mp4"
        script = run_dir / "script.txt"
        if video.exists() and video.stat().st_size > 50_000:
            try:
                text_preview = script.read_text(encoding="utf-8")[:120] if script.exists() else ""
                stat = video.stat()
                videos.append({
                    "run_id": run_dir.name,
                    "video_url": f"/outputs/{run_dir.name}/shorts.mp4",
                    "size_mb": round(stat.st_size / 1_048_576, 2),
                    "created_at": stat.st_ctime,
                    "text_preview": text_preview,
                })
            except Exception:
                pass
    return videos


def cleanup_old_outputs(max_age_days: int = 7) -> dict:
    """حذف مجلدات outputs الأقدم من max_age_days أيام"""
    import time, shutil
    deleted = 0
    errors = []
    cutoff = time.time() - (max_age_days * 86400)
    for run_dir in OUTPUT_DIR.iterdir():
        if not run_dir.is_dir():
            continue
        try:
            if run_dir.stat().st_mtime < cutoff:
                shutil.rmtree(run_dir)
                deleted += 1
                logger.info(f"🗑️ Deleted old run: {run_dir.name}")
        except Exception as e:
            errors.append(str(e))
            logger.warning(f"⚠️ Could not delete {run_dir}: {e}")
    return {"deleted": deleted, "errors": errors}


# -------------------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------------------
@app.get("/api/health")
def health_check():
    """فحص حالة الخدمة"""
    return {
        "status": "ok",
        "version": "2.0.0",
        "service": "AI Shorts Generator",
        "outputs_dir": str(OUTPUTS_DIR),
        "video_count": sum(1 for d in OUTPUT_DIR.iterdir() if d.is_dir() and (d / "shorts.mp4").exists()),
    }


@app.get("/api/videos")
def list_videos(limit: int = Query(default=20, ge=1, le=100)):
    """قائمة بالفيديوهات المولّدة السابقة"""
    videos = _list_run_videos()
    return {"videos": videos[:limit], "total": len(videos)}


@app.post("/api/cleanup")
def cleanup_endpoint(request: CleanupRequest):
    result = cleanup_old_outputs(request.max_age_days)
    return {"message": f"Cleanup done: {result['deleted']} directories removed", **result}


@app.delete("/api/videos/{run_id}")
def delete_video(run_id: str):
    """حذف فيديو محدد"""
    import shutil
    run_dir = OUTPUT_DIR / run_id
    if not run_dir.exists() or not run_dir.is_dir():
        raise HTTPException(status_code=404, detail="الفيديو غير موجود")
    try:
        shutil.rmtree(run_dir)
        return {"message": f"Deleted run {run_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/generate-video")
async def generate_video(request: VideoRequest):
    """
    توليد فيديو قصير من نص بالعربي أو الإنجليزي.
    Pipeline: نص → صوت → مشاهد Gemini → كليبات Pexels → FFmpeg render
    """
    try:
        run_id = uuid.uuid4().hex
        run_dir = OUTPUT_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # ─── (A) النص ───────────────────────────────────────────────
        input_text = (request.text or "").strip()

        if not input_text and (request.topic or "").strip() and generate_script:
            logger.info(f"🧠 Generating FULL script using Gemini for topic: {request.topic}...")
            input_text = (generate_script(request.topic, request.language or "ar") or "").strip()

        if not input_text:
            input_text = (request.topic or "").strip()

        if not input_text:
            raise HTTPException(status_code=422, detail="النص فارغ! الرجاء كتابة نص أو عنوان.")

        if len(input_text) > 5000:
            raise HTTPException(status_code=422, detail="النص طويل جداً (الحد الأقصى 5000 حرف).")

        logger.info(f"📝 Processing Text ({len(input_text)} chars): {input_text[:80]}...")

        script_path = run_dir / "script.txt"
        script_path.write_text(input_text, encoding="utf-8")

        # ─── (B) توليد الصوت ─────────────────────────────────────
        audio_path = run_dir / "voice.mp3"
        try:
            from app.services.tts_service import tts_generate
            await asyncio.to_thread(
                tts_generate,
                input_text,
                audio_path,
                request.language or "ar",
                request.voice,
            )
            logger.info(f"✅ Audio generated: {audio_path.stat().st_size / 1024:.1f}KB")
        except Exception as e:
            logger.error(f"❌ TTS failed: {e}")
            raise HTTPException(status_code=500, detail=f"فشل توليد الصوت: {e}")

        # ─── (B2) Smart Scenes + Clips ──────────────────────────
        audio_dur = _audio_dur_sec(audio_path)
        if audio_dur <= 0:
            audio_dur = 15.0
        logger.info(f"🎵 Audio duration: {audio_dur:.2f}s")

        plan = plan_scenes(script_text_ar=input_text, audio_duration_sec=audio_dur, max_scenes=6)
        scenes_path = run_dir / "scenes.json"
        scenes_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"[SCENES] {len(plan.get('scenes', []))} scenes planned")

        # تحميل متوازي للكليبات
        if download_stock_clips and plan_search_terms:
            logger.info("🚀 Starting parallel clip downloads...")
            clips_root = run_dir / "clips"
            clips_root.mkdir(parents=True, exist_ok=True)

            async def download_scene(sc):
                scene_id = int(sc.get("i", sc.get("id", 1)))
                scene_text = sc.get("text", "")
                scene_dir = clips_root / f"scene_{scene_id:02d}"
                scene_dir.mkdir(parents=True, exist_ok=True)
                try:
                    terms = plan_search_terms(scene_text, max_clips=3)
                    logger.info(f"🎞️ Scene {scene_id} terms: {terms}")
                    await asyncio.to_thread(download_stock_clips, terms, scene_dir, 3)
                except Exception as e:
                    logger.warning(f"⚠️ Scene {scene_id} clips failed: {e}")

            tasks = [download_scene(sc) for sc in plan.get("scenes", [])]
            if tasks:
                await asyncio.gather(*tasks)

            has_any = any(clips_root.rglob("*.mp4")) if clips_root.exists() else False
            if not has_any:
                logger.warning("⚠️ No Pexels clips — will use animated gradient background.")

        # ─── (C) Render via tools/render_shorts.py ──────────────
        out_video = run_dir / "shorts.mp4"
        tool_path = BASE_DIR / "tools" / "render_shorts.py"
        python_exec = sys.executable

        cmd = [
            python_exec, str(tool_path),
            str(audio_path),
            str(script_path),
            str(out_video),
            str(run_dir / "clips"),
        ]

        logger.info("🎬 Rendering video...")
        result = await asyncio.to_thread(
            subprocess.run, cmd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
        )

        if result.stdout:
            logger.info(f"[RENDER LOG]\n{result.stdout[:2000]}")
        if result.stderr:
            logger.warning(f"[RENDER ERR]\n{result.stderr[:4000]}")

        if result.returncode != 0:
            raise HTTPException(
                status_code=500,
                detail=f"Render Failed: {(result.stderr or '')[-500:]}",
            )

        if not out_video.exists() or out_video.stat().st_size < 50_000:
            raise HTTPException(
                status_code=500,
                detail="Render failed: shorts.mp4 not created or too small",
            )

        size_mb = round(out_video.stat().st_size / 1_048_576, 2)
        logger.info(f"✅ Video Created: {out_video} ({size_mb}MB)")

        # ─── (D) التنظيف الذكي ───────────────────────────────────
        try:
            import shutil
            # حذف مجلد الكليبات الخام (الأكثر استهلاكاً للمساحة)
            if (run_dir / "clips").exists():
                shutil.rmtree(run_dir / "clips")
            # حذف الملفات المؤقتة الأخرى
            for temp_file in ["voice.mp3", "montage_temp.mp4", "scenes.json", "captions.srt"]:
                path = run_dir / temp_file
                if path.exists():
                    path.unlink()
            logger.info(f"🧹 Smart cleanup done for run {run_id}. Final video preserved.")
        except Exception as e:
            logger.warning(f"⚠️ Cleanup failed: {e}")

        return {
            "run_id": run_id,
            "video_url": f"/outputs/{run_id}/shorts.mp4",
            "size_mb": size_mb,
            "audio_duration": round(audio_dur, 2),
            "scenes_count": len(plan.get("scenes", [])),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Global Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
