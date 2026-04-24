# المسار: backend/app/services/scene_planner.py
from __future__ import annotations

import json
import os
import re
from typing import Any

# --- Constants ---
DEFAULT_MODEL = "gemini-1.5-flash"
MIN_SCENE_SEC = 1.5
MAX_SCENE_SEC = 6.0
PREFERRED_MIN_SCENES = 4
PREFERRED_MAX_SCENES = 6
MAX_SCENES_HARD_CAP = 10

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "about", "your",
    "you", "are", "was", "were", "have", "has", "had", "will", "can", "could",
    "should", "would", "a", "an", "to", "of", "in", "on", "at", "by", "as",
}

ARABIC_RE = re.compile(r"[\u0600-\u06FF]+")

ARABIC_TO_LATIN = {
    "\u0627": "a", "\u0623": "a", "\u0625": "i", "\u0622": "a",
    "\u0628": "b", "\u062a": "t", "\u062b": "th", "\u062c": "j", "\u062d": "h", "\u062e": "kh",
    "\u062f": "d", "\u0630": "dh", "\u0631": "r", "\u0632": "z", "\u0633": "s", "\u0634": "sh",
    "\u0635": "s", "\u0636": "d", "\u0637": "t", "\u0638": "z", "\u0639": "a", "\u063a": "gh",
    "\u0641": "f", "\u0642": "q", "\u0643": "k", "\u0644": "l", "\u0645": "m", "\u0646": "n",
    "\u0647": "h", "\u0648": "w", "\u064a": "y", "\u0649": "a", "\u0629": "a", "\u0621": "a",
    "\u0624": "w", "\u0626": "y",
}

# --- Helper Functions (MUST be defined before plan_scenes) ---

def _get_api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

def _get_model_name() -> str:
    return os.getenv("GEMINI_MODEL") or DEFAULT_MODEL

def _extract_json_block(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    if start == -1: return None
    depth = 0
    for idx in range(start, len(text)):
        char = text[idx]
        if char == "{": depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                block = text[start:idx + 1]
                try: return json.loads(block)
                except: return None
    return None

def _sanitize_query(query: str, fallback_query: str) -> str:
    query = query.replace("\"", "").replace("'", "").strip()
    query = re.sub(r"[^A-Za-z\s]", " ", query)
    words = [w.lower() for w in query.split() if w.strip()]
    words = [w for w in words if w not in STOPWORDS]
    if not words: words = fallback_query.split()
    if len(words) < 4: words = (words + fallback_query.split())[:4]
    return " ".join(words[:10])

def _cap_max_scenes(max_scenes: int) -> int:
    if max_scenes <= 0: return 1
    return max(1, min(max_scenes, MAX_SCENES_HARD_CAP))

def _compute_scene_count(audio_duration_sec: float, max_scenes: int) -> int:
    max_scenes = _cap_max_scenes(max_scenes)
    target = round(audio_duration_sec / 4.0) if audio_duration_sec > 0 else PREFERRED_MIN_SCENES
    target = max(PREFERRED_MIN_SCENES, min(PREFERRED_MAX_SCENES, target))
    target = min(target, max_scenes)
    return max(1, min(target, max_scenes))

def _normalize_durations(durations: list[float], total: float) -> list[float]:
    if not durations: return []
    durations = [float(d) for d in durations]
    total_now = sum(durations)
    if total > 0 and total_now > 0:
        scale = total / total_now
        durations = [d * scale for d in durations]
    elif total_now == 0 and total > 0:
        durations = [total / len(durations)] * len(durations)
    return [min(max(d, MIN_SCENE_SEC), MAX_SCENE_SEC) for d in durations]

def _split_arabic_chunks(script_text_ar: str) -> list[str]:
    chunks = [s.strip() for s in re.split(r"(?<=[\.\!\u061F\?\u2026\u060C])\s+", script_text_ar) if s.strip()]
    if not chunks and script_text_ar.strip(): chunks = [script_text_ar.strip()]
    return chunks

def _arabic_word_count(text: str) -> int:
    return len(ARABIC_RE.findall(text))

def _romanize_arabic_word(word: str) -> str:
    result = []
    for char in word: result.append(ARABIC_TO_LATIN.get(char, ""))
    return "".join(result)

def _keywords_from_arabic(text: str, max_words: int = 3) -> list[str]:
    words = ARABIC_RE.findall(text)
    seen: set[str] = set()
    keywords: list[str] = []
    for word in words:
        romanized = _romanize_arabic_word(word)
        romanized = re.sub(r"[^a-zA-Z]", "", romanized).lower()
        if not romanized or romanized in seen: continue
        seen.add(romanized)
        keywords.append(romanized)
        if len(keywords) >= max_words: break
    return keywords

def _build_fallback_query(keywords: list[str]) -> str:
    words = ["cinematic", "b", "roll"]
    if keywords: words.extend(keywords)
    if len(words) < 4: words.extend(["arabic", "story"])
    return " ".join(words[:10])

def _fallback_plan(script_text_ar: str, audio_duration_sec: float, max_scenes: int) -> dict:
    max_scenes = _cap_max_scenes(max_scenes)
    chunks = _split_arabic_chunks(script_text_ar)
    scene_count = _compute_scene_count(audio_duration_sec, max_scenes)
    if not chunks: chunks = [script_text_ar.strip()]
    while len(chunks) < scene_count: chunks.append(chunks[-1])
    
    scene_texts = chunks[:scene_count]
    durations = _normalize_durations([audio_duration_sec/len(scene_texts)]*len(scene_texts), audio_duration_sec)
    
    scenes = []
    for idx in range(scene_count):
        text = scene_texts[idx]
        keywords = _keywords_from_arabic(text, max_words=3)
        scenes.append({
            "i": idx + 1,
            "dur": round(durations[idx], 2),
            "text": text,
            "query": _build_fallback_query(keywords),
        })
    return {"style": {"transition_sec": 0.35}, "scenes": scenes}

def _validate_plan(plan: dict, script_text_ar: str, audio_duration_sec: float, max_scenes: int) -> dict:
    scenes = plan.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        return _fallback_plan(script_text_ar, audio_duration_sec, max_scenes)
    
    max_scenes = _cap_max_scenes(max_scenes)
    scenes = scenes[:max_scenes]
    
    normalized = []
    fallback_texts = _split_arabic_chunks(script_text_ar)
    if not fallback_texts: fallback_texts = [script_text_ar]

    for idx, scene in enumerate(scenes):
        text = scene.get("text", "")
        if not text: text = fallback_texts[idx % len(fallback_texts)]
        
        query = scene.get("query", "")
        fallback_query = _build_fallback_query(_keywords_from_arabic(text, 3))
        query = _sanitize_query(query, fallback_query)
        
        dur = scene.get("dur", 0)
        normalized.append({
            "i": idx + 1,
            "dur": float(dur),
            "text": text,
            "query": query,
        })
        
    durations = _normalize_durations([s["dur"] for s in normalized], audio_duration_sec)
    for scene, dur in zip(normalized, durations):
        scene["dur"] = round(dur, 2)
        
    return {"style": {"transition_sec": 0.35}, "scenes": normalized}

def _call_gemini(prompt: str) -> dict[str, Any] | None:
    """استدعاء Gemini عبر الخدمة المركزية."""
    try:
        from app.services.gemini_client import generate_json
        return generate_json(prompt, temperature=0.4)
    except Exception:
        return None

# --- Main Logic ---

def plan_scenes(script_text_ar: str, audio_duration_sec: float, max_scenes: int = 6) -> dict:
    max_scenes = _cap_max_scenes(max_scenes)
    # زيادة عدد المشاهد لضمان التغيير السريع (كل 2.5 إلى 3 ثواني مشهد)
    scene_count = max(6, min(int(audio_duration_sec / 2.8), max_scenes))
    
    prompt = (
        'You are an expert video director. Create a JSON montage plan for a short video based on this Arabic script. '
        'The goal is to visualize the abstract meanings with high-quality stock footage ideas.\n\n'
        f'SCRIPT: "{script_text_ar}"\n'
        f'Total Audio Duration: {audio_duration_sec:.2f} seconds.\n'
        f'Target Scene Count: {scene_count}.\n\n'
        'REQUIREMENTS:\n'
        '1. "text": The exact Arabic sentence segment for this scene (split the script logically).\n'
        '2. "dur": Duration in seconds (must sum up exactly to Total Audio Duration).\n'
        '3. "query": A very specific English search query for stock footage. '
        'Example: if the text is about "The heart of a blue whale", use "blue whale swimming underwater cinematic" '
        'NOT just "whale". If it is about "Ancient Egypt", use "Ancient Egypt pyramids desert drone shot". '
        'Use visual nouns and action verbs.\n\n'
        'JSON OUTPUT FORMAT:\n'
        '{"style": {"transition_sec": 0}, "scenes": [{"i": 1, "dur": 4.0, "text": "...", "query": "..."}]}'
    )

    plan = _call_gemini(prompt)
    if not isinstance(plan, dict):
        return _fallback_plan(script_text_ar, audio_duration_sec, max_scenes)

    return _validate_plan(plan, script_text_ar, audio_duration_sec, max_scenes)


def plan_search_terms(scene_text: str, max_clips: int = 3) -> list[str]:
    """
    يولّد قائمة من عبارات البحث الإنجليزية لمشهد معين.
    يُستخدم لتحميل كليبات Pexels لكل مشهد.
    """
    if not scene_text or not scene_text.strip():
        return ["cinematic b roll arabic story"]

    # استخراج كلمات عربية وتحويلها
    keywords = _keywords_from_arabic(scene_text, max_words=4)
    fallback = _build_fallback_query(keywords)

    # حاول Gemini للحصول على عبارات بحث دقيقة
    prompt = (
        f'Given this Arabic video script segment: "{scene_text.strip()[:200]}" '
        f'Generate {max_clips} English search queries for stock footage (Pexels). '
        f'Each query: 3-6 concrete visual words, cinematic style. '
        f'Output JSON only: {{"terms": ["query1", "query2", "query3"]}}'
    )
    try:
        result = _call_gemini(prompt)
        if isinstance(result, dict):
            terms = result.get("terms", [])
            if isinstance(terms, list) and terms:
                cleaned = []
                for t in terms[:max_clips]:
                    t_clean = _sanitize_query(str(t), fallback)
                    if t_clean:
                        cleaned.append(t_clean)
                if cleaned:
                    return cleaned
    except Exception:
        pass

    # fallback
    return [fallback]