import sys
from pathlib import Path
import logging
import uuid
import shutil
import asyncio
import subprocess

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

# -------------------------------------------------------------------------
# 1) إعداد المسارات
# -------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent  # backend/
sys.path.append(str(BASE_DIR))

OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

# -------------------------------------------------------------------------
# 2) استيراد الخدمات (مع التعامل مع الأخطاء)
# -------------------------------------------------------------------------

# (A) خدمة السكربت (اختياري)
try:
    from app.services.script_service import generate_script
except ImportError:
    generate_script = None

# (B) خدمة الصوت الاحترافي (Edge TTS)
try:
    from app.services.tts_service import generate_audio_edge
except ImportError:
    generate_audio_edge = None
    print("⚠️ Warning: tts_service.py not found in app/services/")

# (C) مكتبات الصوت الاحتياطية
try:
    from gtts import gTTS
except ImportError:
    gTTS = None



# (D) خدمة الصور (Pollinations / AI Images) - اختياري
try:
    from app.services.image_service import generate_images_for_text
except ImportError:
    generate_images_for_text = None
    print("⚠️ Warning: image_service.py or generate_images_for_text not found in app/services/")

# -------------------------------------------------------------------------
# 3) إعداد التطبيق
# -------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# عرض الملفات: /outputs/<run_id>/shorts.mp4
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")


class VideoRequest(BaseModel):
    topic: str = ""
    text: str = ""
    language: str = "ar"
    # اختياري: عدد الصور
    images_count: int = 3





# -------------------------------------------------------------------------
# 4) Endpoint
# -------------------------------------------------------------------------
@app.post("/api/generate-video")
async def generate_video(request: VideoRequest):
    try:
        request_id = uuid.uuid4().hex
        request_dir = OUTPUT_DIR / request_id
        request_dir.mkdir(exist_ok=True)

        # -----------------------------
        # (A) تجهيز النص
        # -----------------------------
        input_text = (request.text or "").strip()

        # لو النص فاضي، جرب توليد سكربت من topic
        if not input_text and (request.topic or "").strip() and generate_script:
            logger.info("🧠 Generating script using Gemini...")
            input_text = (generate_script(request.topic) or "").strip()

        # لو ما زال فاضي: استخدم topic نفسه
        if not input_text:
            input_text = (request.topic or "").strip()

        if not input_text:
            raise HTTPException(status_code=422, detail="النص فارغ! الرجاء كتابة نص أو عنوان.")

        logger.info(f"📝 Processing Text: {input_text[:60]}...")

        # حفظ السكربت
        script_path = request_dir / "script.txt"
        script_path.write_text(input_text, encoding="utf-8")

        # -----------------------------
        # (A0) توليد صور متوافقة مع النص (اختياري)
        # -----------------------------
        if generate_images_for_text:
            try:
                images_dir = request_dir / "images"
                images_count = max(0, min(8, int(request.images_count or 3)))
                if images_count > 0:
                    logger.info(f"🖼️ Generating {images_count} background images...")
                    await asyncio.to_thread(generate_images_for_text, input_text, images_dir, images_count)
                    logger.info("✅ Images generated.")
            except Exception as e:
                logger.warning(f"⚠️ Image generation skipped: {e}")

        # -----------------------------
        # (B) توليد الصوت
        # -----------------------------
        audio_path = request_dir / "voice.mp3"
        audio_generated = False

        # 1) Edge TTS
        if generate_audio_edge:
            try:
                logger.info("🎙️ Attempt 1: Edge TTS (Naayf)...")
                await generate_audio_edge(input_text, str(audio_path), voice="ar-SA-NaayfNeural")
                if audio_path.exists() and audio_path.stat().st_size > 0:
                    audio_generated = True
                    logger.info("✅ Edge TTS Success!")
            except Exception as e:
                logger.warning(f"⚠️ Edge TTS Failed: {e}")

        # 2) Google TTS
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
            raise HTTPException(status_code=500, detail="فشل توليد الصوت بجميع الطرق.")

        # -----------------------------
        # (C) رندر الفيديو عبر render_shorts.py
        # -----------------------------
        output_video = request_dir / "shorts.mp4"
        tool_path = BASE_DIR / "tools" / "render_shorts.py"
        python_exec = sys.executable

        cmd = [python_exec, str(tool_path), str(audio_path), str(script_path), str(output_video)]

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
            print(f"[RENDER LOG] {result.stdout[:600]}...")
        if result.stderr:
            print(f"[RENDER ERR] {result.stderr[:600]}...")

        if result.returncode != 0:
            logger.error(f"Render Error: {result.stderr}")
            raise HTTPException(status_code=500, detail=f"Render Failed: {result.stderr[-220:]}")

        logger.info(f"✅ Video Created: {output_video}")
        return {"video_url": f"/outputs/{request_id}/shorts.mp4"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Global Error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
