from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

# =========================
# Logging Setup
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Short Video MVP", version="0.1.0")

# CORS (مفيد لو بتفتح الواجهة من 5500، لكن بعد ما نخدمها من 8000 يصير مو ضروري)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Paths (مضبوطة على هيكل مشروعك)
# =========================
# main.py موجود في: backend/app/main.py
BACKEND_DIR = Path(__file__).resolve().parents[1]   # => backend/
ROOT_DIR = BACKEND_DIR.parent                       # => project root/

OUTPUTS_DIR = BACKEND_DIR / "outputs"               # => backend/outputs
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

TOOLS_DIR = BACKEND_DIR / "tools"                   # => backend/tools
RENDER_PY = TOOLS_DIR / "render_shorts.py"

FRONTEND_DIR = ROOT_DIR / "frontend"                # => root/frontend
FRONTEND_DIST = FRONTEND_DIR / "dist"                # => frontend/dist (بعد البناء)

# =========================
# Static mounts
# =========================
# عرض الملفات: /outputs/<run_id>/shorts.mp4
app.mount("/outputs", StaticFiles(directory=str(OUTPUTS_DIR)), name="outputs")

# خدمة الفرونت إند React (بعد البناء)
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
else:
    @app.get("/")
    def home():
        return {
            "message": "Frontend not built. Run 'cd frontend && npm run build' first.",
            "api_docs": "/docs",
            "health": "/api/health"
        }


# =========================
# Models
# =========================
class GenerateVideoRequest(BaseModel):
    text: str = Field(..., min_length=10, max_length=2000, description="النص المراد تحويله إلى فيديو")
    
    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        text = v.strip()
        if len(text) < 10:
            raise ValueError("النص قصير جداً (يجب أن يكون 10 أحرف على الأقل)")
        if len(text) > 2000:
            raise ValueError("النص طويل جداً (الحد الأقصى 2000 حرف)")
        return text


# =========================
# Helpers
# =========================
def run(cmd: list[str], cwd: Path | None = None) -> str:
    p = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if p.returncode != 0:
        raise RuntimeError(f"Command failed:\n{' '.join(cmd)}\n\nSTDERR:\n{p.stderr}")
    return (p.stdout or "").strip()


def cleanup_old_outputs(max_age_days: int = 7) -> dict:
    """حذف الملفات القديمة من مجلد outputs"""
    if not OUTPUTS_DIR.exists():
        return {"deleted": 0, "errors": []}
    
    cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
    deleted_count = 0
    errors = []
    
    try:
        for item in OUTPUTS_DIR.iterdir():
            if item.is_dir():
                try:
                    # حذف المجلد إذا كان أقدم من max_age_days
                    if item.stat().st_mtime < cutoff_time:
                        shutil.rmtree(item)
                        deleted_count += 1
                        logger.info(f"Deleted old output directory: {item}")
                except Exception as e:
                    error_msg = f"Failed to delete {item}: {e}"
                    logger.error(error_msg)
                    errors.append(error_msg)
    except Exception as e:
        logger.error(f"Error during cleanup: {e}", exc_info=True)
        errors.append(str(e))
    
    return {"deleted": deleted_count, "errors": errors}


# =========================
# Routes
# =========================
@app.get("/api/health")
def health():
    """Health check endpoint"""
    logger.info("Health check requested")
    return {"ok": True, "status": "healthy"}


@app.post("/api/cleanup")
def cleanup_outputs(max_age_days: int = 7):
    """تنظيف الملفات القديمة (اختياري: max_age_days)"""
    logger.info(f"Cleanup requested for files older than {max_age_days} days")
    result = cleanup_old_outputs(max_age_days)
    logger.info(f"Cleanup completed: {result['deleted']} directories deleted")
    return {
        "success": True,
        "deleted_count": result["deleted"],
        "errors": result["errors"],
        "max_age_days": max_age_days
    }


@app.post("/api/generate-video")
def generate_video(req: GenerateVideoRequest):
    """إنشاء فيديو قصير من النص"""
    text = req.text
    run_id = None
    
    try:
        logger.info(f"Starting video generation for text length: {len(text)}")
        
        # 1) run_id + output folder
        run_id = uuid.uuid4().hex
        out_dir = OUTPUTS_DIR / run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created output directory: {out_dir}")

        # 2) TTS (Edge TTS - صوت ذكوري طبيعي)
        audio_path = out_dir / "voice.mp3"
        tts_success = False
        
        # محاولة Edge TTS أولاً
        try:
            from app.services.tts_service import generate_speech_sync
            logger.info("Generating TTS audio with Edge TTS (natural male voice)...")
            generate_speech_sync(text, audio_path)
            logger.info(f"Edge TTS audio saved: {audio_path}")
            tts_success = True
        except ImportError as e:
            logger.warning(f"Edge TTS not installed, will use gTTS: {e}")
        except (ConnectionError, OSError, TimeoutError, Exception) as e:
            # أخطاء الاتصال أو SSL - ننتقل إلى gTTS
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in ["connection", "ssl", "host", "network", "timeout", "forcibly closed"]):
                logger.warning(f"Edge TTS connection failed ({e}), falling back to gTTS")
            else:
                logger.warning(f"Edge TTS error ({e}), falling back to gTTS")
        
        # Fallback إلى gTTS إذا Edge TTS فشل
        if not tts_success:
            try:
                from gtts import gTTS
                logger.info("Using gTTS as fallback...")
                gTTS(text=text, lang="ar").save(str(audio_path))
                logger.info(f"gTTS audio saved: {audio_path}")
                tts_success = True
            except ImportError:
                logger.error("Neither edge-tts nor gtts libraries are installed")
                raise HTTPException(
                    status_code=500, 
                    detail="مكتبة gtts غير مثبتة. قم بتثبيتها: pip install gtts"
                )
            except Exception as e:
                logger.error(f"gTTS also failed: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500, 
                    detail=f"فشل تحويل النص إلى صوت. حاول مرة أخرى أو تحقق من الاتصال بالإنترنت."
                )
        
        if not tts_success:
            raise HTTPException(status_code=500, detail="فشل تحويل النص إلى صوت")

        # 3) Render
        if not RENDER_PY.exists():
            logger.error(f"render_shorts.py not found at {RENDER_PY}")
            raise HTTPException(
                status_code=500, 
                detail=f"ملف render_shorts.py غير موجود: {RENDER_PY}"
            )

        try:
            logger.info("Rendering video...")
            out_mp4 = out_dir / "shorts.mp4"
            stdout = run(
                ["python", str(RENDER_PY), str(audio_path), text, str(out_mp4)],
                cwd=BACKEND_DIR,
            )
            info = json.loads(stdout) if stdout else {}
            logger.info(f"Video rendered successfully: {out_mp4}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse render output: {e}")
            info = {}
        except Exception as e:
            logger.error(f"Video rendering failed: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, 
                detail=f"فشل إنشاء الفيديو: {str(e)}"
            )

        logger.info(f"Video generation completed successfully. Run ID: {run_id}")
        return {
            "run_id": run_id,
            "video_url": f"/outputs/{run_id}/shorts.mp4",
            "audio_url": f"/outputs/{run_id}/voice.mp3",
            "debug": info,
        }
    
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Unexpected error during video generation: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"حدث خطأ غير متوقع: {str(e)}"
        )
