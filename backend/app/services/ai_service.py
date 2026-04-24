"""
خدمة AI لتوليد خطط المشاهد البصرية باستخدام Gemini.
"""
from __future__ import annotations

import logging
from app.services.gemini_client import generate_json

logger = logging.getLogger(__name__)


def generate_script(topic: str, language: str = "ar") -> str:
    """
    توليد سكربت مشوق للفيديو القصير بناءً على الموضوع.
    """
    prompt = f"""
    You are a professional YouTube Shorts Scriptwriter for highly engaging, viral content.
    TASK: Create a script for a video about: "{topic}".
    LANGUAGE: {language}.
    DURATION: 40-55 seconds.

    STRUCTURE (CRITICAL):
    1. HOOK (First 3 seconds): Start with a shocking fact, a question, or a bold statement to stop the scroll.
    2. THE STORY/BODY: Deliver high-value information or a story. Keep sentences short and punchy.
    3. THE TWIST/VALUE: Add something unexpected or a key takeaway.
    4. CALL TO ACTION (Final 5 seconds): A quick "Subscribe for more" or "Like if you agree".

    TONE: Exciting, fast-paced, and cinematic.
    FORMAT: Output ONLY the narration text. No brackets, no labels like [Hook], no titles. Just the raw Arabic text to be spoken.
    """.strip()

    try:
        from app.services.gemini_client import generate_text
        text = generate_text(prompt, temperature=0.7)
        if text:
            logger.info(f"✅ Gemini Response Received: {text[:100]}...")
            return text.strip()
        else:
            logger.warning("⚠️ Gemini returned EMPTY text.")
        return topic # Fallback
    except Exception as e:
        logger.error(f"❌ Script Generation Error: {e}")
        return topic



def generate_visual_plan(script_text: str) -> list[dict]:
    """
    يرجّع قائمة مشاهد بصيغة:
    [
      {
        "text_ar": "...",
        "search_term": "english keywords",
        "visual_prompt": "english cinematic description",
        "shot": "wide|medium|close-up|aerial",
        "motion": "slow push-in|pan|tilt|handheld|parallax"
      },
      ...
    ]
    """
    if not script_text or not script_text.strip():
        return []

    prompt = f"""
You are an expert short-video storyboard writer.

SCRIPT (Arabic voiceover):
\"\"\"{script_text.strip()}\"\"\"

TASK:
Return 6-10 scenes (depending on length). Make scenes coherent and ordered.
Each scene must include:
- text_ar: Arabic caption chunk (short, 4-10 words)
- search_term: English stock-footage keywords (3-7 words, concrete nouns)
- visual_prompt: English visual description (cinematic, specific)
- shot: one of [wide, medium, close-up, aerial]
- motion: one of [slow push-in, pan, tilt, handheld, parallax]

RULES:
- Output JSON ONLY.
- No markdown, no backticks, no extra text.
- Keep English keywords practical for stock footage search.

OUTPUT JSON:
{{"scenes":[
  {{"text_ar":"...", "search_term":"...", "visual_prompt":"...", "shot":"...", "motion":"..."}}
]}}
""".strip()

    try:
        data = generate_json(prompt, temperature=0.3)
        if not data:
            return []

        scenes = data.get("scenes", []) or []
        cleaned = []
        for s in scenes:
            if not isinstance(s, dict):
                continue
            text_ar = str(s.get("text_ar", "")).strip()
            search_term = str(s.get("search_term", "")).strip()
            visual_prompt = str(s.get("visual_prompt", "")).strip()
            shot = str(s.get("shot", "medium")).strip()
            motion = str(s.get("motion", "slow push-in")).strip()

            if not text_ar or not search_term or not visual_prompt:
                continue

            cleaned.append({
                "text_ar": text_ar,
                "search_term": search_term,
                "visual_prompt": visual_prompt,
                "shot": shot,
                "motion": motion,
            })

        logger.info(f"✅ Gemini created {len(cleaned)} visual scenes.")
        return cleaned

    except Exception as e:
        logger.error(f"❌ Gemini Error: {e}")
        return []
