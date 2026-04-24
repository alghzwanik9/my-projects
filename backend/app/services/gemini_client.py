"""
خدمة Gemini AI المركزية — تدعم:
  1. google-genai  (SDK v2 الجديد)  ← الأولوية الأولى
  2. HTTP REST مباشر ← fallback موثوق بدون تبعيات

ملاحظة: google-generativeai (SDK v1) وصل لنهاية حياته ولن يتلقى تحديثات.
"""
from __future__ import annotations

import warnings
warnings.filterwarnings("ignore", category=FutureWarning, module="google.generativeai")

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-1.5-flash"  # جربنا gemini-1.5-flash-latest أيضاً


def get_api_key() -> str | None:
    return (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or ""
    ).strip() or None


def get_model_name() -> str:
    return os.getenv("GEMINI_MODEL", DEFAULT_MODEL)


def extract_json_block(text: str) -> dict[str, Any] | None:
    """يستخرج أول JSON object أو array من النص."""
    # حاول JSON مباشر أولاً
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    # ابحث عن { أو [
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        if start == -1:
            continue
        depth = 0
        for idx in range(start, len(text)):
            char = text[idx]
            if char == start_char:
                depth += 1
            elif char == end_char:
                depth -= 1
                if depth == 0:
                    block = text[start: idx + 1]
                    try:
                        return json.loads(block)
                    except json.JSONDecodeError:
                        break
    return None


def generate_text(prompt: str, temperature: float = 0.3) -> str | None:
    """
    يستدعي Gemini ويرجع النص الخام.
    يجرب SDK v2 → SDK v1 → HTTP fallback.
    """
    api_key = get_api_key()
    if not api_key:
        logger.warning("⚠️ GEMINI_API_KEY missing.")
        return None

    model_name = get_model_name()

    # ─── 1) Google GenAI SDK v2 (google-genai) ───
    try:
        import google.genai as genai  # type: ignore
        from google.genai import types  # type: ignore

        client = genai.Client(api_key=api_key)
        # إزالة بادئة 'models/' إذا كانت موجودة، الـ SDK يضيفها تلقائياً
        clean_model = model_name.replace("models/", "")
        response = client.models.generate_content(
            model=clean_model,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=temperature),
        )
        text = (response.text or "").strip()
        if text:
            logger.info("✅ Gemini SDK v2 response received.")
            return text
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"Gemini SDK v2 failed: {e}")

    # ─── 2) HTTP Fallback ───
    try:
        import requests

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model_name}:generateContent?key={api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature},
        }
        resp = requests.post(url, json=payload, timeout=30)
        if resp.ok:
            candidates = resp.json().get("candidates", [])
            if candidates:
                text = candidates[0]["content"]["parts"][0]["text"]
                logger.info("✅ Gemini HTTP fallback response received.")
                return text
    except Exception as e:
        logger.error(f"Gemini HTTP fallback also failed: {e}")

    return None


def generate_json(prompt: str, temperature: float = 0.3) -> dict[str, Any] | None:
    """يستدعي Gemini ويرجع JSON مباشرة."""
    text = generate_text(prompt, temperature)
    if not text:
        return None
    return extract_json_block(text)
