from __future__ import annotations

import asyncio
from pathlib import Path
import edge_tts

# الصوت السعودي الذكوري (نايف)
VOICE_AR_DEFAULT = "ar-SA-NaayfNeural"

# أمثلة أصوات:
# "ar-EG-ShakirNeural" -> مصري ذكوري
# "ar-YE-SalehNeural"  -> يمني ذكوري
# "en-US-GuyNeural"    -> إنجليزي ذكوري
# "en-US-JennyNeural"  -> إنجليزي أنثوي

def pick_voice(language: str | None) -> str:
    """
    اختَر صوت افتراضي حسب اللغة
    """
    lang = (language or "").strip().lower()
    if lang == "en":
        return "en-US-GuyNeural"
    return VOICE_AR_DEFAULT


async def generate_audio_edge(text: str, output_file: str, voice: str) -> None:
    """
    توليد صوت باستخدام Edge TTS (async)
    يرمي Exception إذا فشل.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("TTS text is empty")

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_file)


def tts_generate(text: str, out_path: Path | str, language: str | None = "ar", voice: str | None = None) -> Path:
    """
    دالة Sync للاستخدام داخل FastAPI:
    - تولّد mp3 في out_path
    - ترجع Path النهائي
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    chosen_voice = (voice or "").strip() or pick_voice(language)

    # مهم: uvicorn غالبًا يشغلك بدون event loop هنا، فـ asyncio.run تمام.
    # لو واجهت خطأ "asyncio.run() cannot be called..." قلّي وبعطيك نسخة run_in_thread.
    asyncio.run(generate_audio_edge(text=text, output_file=str(out), voice=chosen_voice))

    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError("TTS generated file is missing/empty")

    return out
