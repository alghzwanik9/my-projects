from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

VOICE_AR_DEFAULT = "ar-SA-HamedNeural"   # ذكوري سعودي طبيعي
VOICE_EN_DEFAULT = "en-US-GuyNeural"

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "").strip()


# ──────────────────────────────────────────────
# ElevenLabs  (الأفضل جودةً — يُستدعى أولاً)
# ──────────────────────────────────────────────
def generate_audio_elevenlabs(text: str, out_path: str) -> bool:
    """
    يولّد صوتاً عبر ElevenLabs ويحفظه في out_path.
    يرجع True إذا نجح، False إذا فشل.
    """
    if not ELEVENLABS_API_KEY or not ELEVENLABS_VOICE_ID:
        logger.warning("⚠️ ELEVENLABS_API_KEY or ELEVENLABS_VOICE_ID missing.")
        return False
    try:
        from elevenlabs import ElevenLabs
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        audio = client.text_to_speech.convert(
            text=text,
            voice_id=ELEVENLABS_VOICE_ID,
            model_id="eleven_multilingual_v2", # أفضل موديل للعربية والإنجليزي
            output_format="mp3_44100_128",
            voice_settings={
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True
            }
        )
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "wb") as f:
            if hasattr(audio, "__iter__"):
                for chunk in audio:
                    if chunk:
                        f.write(chunk)
            else:
                f.write(audio)

        if out.exists() and out.stat().st_size > 1000:
            logger.info("✅ ElevenLabs TTS success.")
            return True
        logger.warning("⚠️ ElevenLabs returned empty file.")
        return False
    except Exception as e:
        logger.warning(f"⚠️ ElevenLabs failed: {e}")
        return False


# ──────────────────────────────────────────────
# Edge TTS  (fallback جيد — مجاني)
# ──────────────────────────────────────────────
async def generate_audio_edge(text: str, output_file: str, voice: str) -> None:
    """يولّد صوتاً بـ Edge TTS (async). يرمي Exception عند الفشل."""
    import edge_tts
    text = (text or "").strip()
    if not text:
        raise ValueError("TTS text is empty")
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)


def pick_voice(language: str | None) -> str:
    lang = (language or "").strip().lower()
    if lang == "en":
        return VOICE_EN_DEFAULT
    return VOICE_AR_DEFAULT


def _run_edge_tts_sync(text: str, output_file: str, voice: str) -> None:
    """تشغيل Edge TTS بشكل sync مع معالجة صحيحة للـ event loop."""
    try:
        # إذا كان هناك event loop يعمل (نحن داخل asyncio.to_thread)
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # نحن داخل thread منفصل — نستخدم event loop جديد
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    _run_in_new_loop,
                    generate_audio_edge(text, output_file, voice)
                )
                future.result(timeout=120)
        else:
            loop.run_until_complete(generate_audio_edge(text, output_file, voice))
    except RuntimeError:
        _run_in_new_loop_sync(text, output_file, voice)


def _run_in_new_loop_sync(text: str, output_file: str, voice: str) -> None:
    """تشغيل في event loop جديد تماماً."""
    import nest_asyncio
    try:
        nest_asyncio.apply()
        asyncio.get_event_loop().run_until_complete(
            generate_audio_edge(text, output_file, voice)
        )
    except ImportError:
        # nest_asyncio غير متاح — نستخدم asyncio.run مع loop جديد
        asyncio.run(generate_audio_edge(text, output_file, voice))


def _run_in_new_loop(coro):
    """تشغيل coroutine في event loop جديد (للاستخدام في ThreadPoolExecutor)."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def tts_generate(
    text: str,
    out_path: Path | str,
    language: str | None = "ar",
    voice: str | None = None,
) -> Path:
    """
    دالة Sync واحدة للاستخدام في FastAPI (asyncio.to_thread):
    1. يجرب ElevenLabs أولاً (إذا المفاتيح موجودة)
    2. يرجع لـ Edge TTS كـ fallback
    3. يرجع لـ gTTS كـ fallback أخير
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # 1) ElevenLabs
    if generate_audio_elevenlabs(text, str(out)):
        return out

    # 2) Edge TTS
    try:
        chosen_voice = (voice or "").strip() or pick_voice(language)
        # استخدام asyncio.run في thread منفصل
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(
                generate_audio_edge(text=text, output_file=str(out), voice=chosen_voice)
            )
        finally:
            loop.close()

        if out.exists() and out.stat().st_size > 0:
            logger.info("✅ Edge TTS success.")
            return out
    except Exception as e:
        logger.warning(f"⚠️ Edge TTS failed: {e}")

    # 3) gTTS fallback أخير
    try:
        from gtts import gTTS
        lang_gtts = "ar" if (language or "ar").startswith("ar") else "en"
        tts = gTTS(text=text, lang=lang_gtts, slow=False)
        tts.save(str(out))
        if out.exists() and out.stat().st_size > 0:
            logger.info("✅ gTTS fallback success.")
            return out
    except Exception as e:
        logger.warning(f"⚠️ gTTS also failed: {e}")

    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError("All TTS providers failed. Audio file is missing/empty.")

    return out
