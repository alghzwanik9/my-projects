import os
import json
import logging

import google.generativeai as genai
from google.generativeai.types import GenerationConfig

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        logger.info("✅ GEMINI_API_KEY loaded, Gemini configured.")
    except Exception as e:
        logger.error(f"Gemini Config Error: {e}")
else:
    logger.warning("⚠️ GEMINI_API_KEY missing. Set GEMINI_API_KEY in .env (repo root).")


def _extract_json(text: str) -> dict:
    """
    Gemini أحيانًا يرجّع نص إضافي حول JSON.
    هنا نقص أول { وآخر } ونحاول نقرأ JSON بأمان.
    """
    raw = (text or "").strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Gemini did not return valid JSON.")

    clean = raw[start : end + 1]
    return json.loads(clean)


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
    if not GEMINI_API_KEY:
        logger.warning("Gemini API Key is missing (GEMINI_API_KEY env var).")
        return []

    if not script_text or not script_text.strip():
        return []

    model = genai.GenerativeModel("gemini-1.5-flash")

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
        cfg = GenerationConfig(temperature=0.3)
        resp = model.generate_content(prompt, generation_config=cfg)

        data = _extract_json(getattr(resp, "text", "") or "")
        scenes = data.get("scenes", []) or []

        # تنظيف وتطبيع بسيط
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

            cleaned.append(
                {
                    "text_ar": text_ar,
                    "search_term": search_term,
                    "visual_prompt": visual_prompt,
                    "shot": shot,
                    "motion": motion,
                }
            )

        logger.info(f"✅ Gemini created {len(cleaned)} visual scenes.")
        return cleaned

    except Exception as e:
        logger.error(f"❌ Gemini Error: {e}")
        return []
