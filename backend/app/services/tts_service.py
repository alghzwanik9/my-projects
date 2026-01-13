"""
خدمة تحويل النص إلى كلام باستخدام Edge TTS (Microsoft)
يوفر أصوات طبيعية جداً مقارنة بـ gTTS
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# صوت ذكوري عربي طبيعي من Microsoft Edge TTS
ARABIC_MALE_VOICE = "ar-SA-HamedNeural"  # صوت ذكوري سعودي طبيعي جداً


async def generate_speech_edge(text: str, output_path: Path, voice: str = ARABIC_MALE_VOICE) -> Path:
    """
    إنشاء ملف صوتي باستخدام Edge TTS
    
    Args:
        text: النص المراد تحويله
        output_path: مسار ملف الصوت الناتج
        voice: معرف الصوت (افتراضي: صوت ذكوري عربي)
    
    Returns:
        مسار الملف الصوتي المُنشأ
    
    Raises:
        ImportError: إذا كانت المكتبة غير مثبتة
        ConnectionError: إذا فشل الاتصال
        Exception: أي أخطاء أخرى
    """
    try:
        import edge_tts
        import asyncio
        
        # إنشاء الملف الصوتي مع timeout
        communicate = edge_tts.Communicate(text, voice)
        
        # محاولة الحفظ مع timeout (30 ثانية)
        try:
            await asyncio.wait_for(communicate.save(str(output_path)), timeout=30.0)
        except asyncio.TimeoutError:
            logger.error("Edge TTS timeout - connection took too long")
            raise ConnectionError("Edge TTS connection timeout")
        
        logger.info(f"Edge TTS audio generated: {output_path} (voice: {voice})")
        return output_path
        
    except ImportError:
        logger.warning("edge-tts not installed, falling back to gTTS")
        raise ImportError("edge-tts library not installed. Install with: pip install edge-tts")
    except (ConnectionError, OSError, TimeoutError) as e:
        # أخطاء الاتصال - نرفعها للتعامل معها في main.py
        logger.error(f"Edge TTS connection error: {e}")
        raise
    except Exception as e:
        logger.error(f"Edge TTS failed: {e}", exc_info=True)
        raise


def generate_speech_sync(text: str, output_path: Path, voice: str = ARABIC_MALE_VOICE) -> Path:
    """
    نسخة متزامنة من generate_speech_edge
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(generate_speech_edge(text, output_path, voice))


def get_available_voices(language: str = "ar") -> list[dict]:
    """
    الحصول على قائمة الأصوات المتاحة للغة معينة
    
    Returns:
        قائمة من القواميس تحتوي على معلومات الأصوات
    """
    try:
        import edge_tts
        
        async def _get_voices():
            voices = await edge_tts.list_voices()
            return [v for v in voices if language in v.get("Locale", "").lower()]
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(_get_voices())
    except ImportError:
        return []
    except Exception as e:
        logger.error(f"Failed to get voices: {e}")
        return []
