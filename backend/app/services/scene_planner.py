from __future__ import annotations

import json
import os
import re
from typing import Any

DEFAULT_MODEL = "gemini-1.5-flash"
MIN_SCENE_SEC = 1.5
MAX_SCENE_SEC = 6.0
PREFERRED_MIN_SCENES = 4
PREFERRED_MAX_SCENES = 6

FALLBACK_QUERIES = [
    "cinematic city skyline b roll",
    "people working on laptops b roll",
    "hands typing on keyboard b roll",
    "nature landscape sunrise b roll",
    "abstract light leaks b roll",
    "close up coffee brewing b roll",
    "modern office teamwork b roll",
    "urban traffic timelapse b roll",
]

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "about", "your",
    "you", "are", "was", "were", "have", "has", "had", "will", "can", "could",
    "should", "would", "a", "an", "to", "of", "in", "on", "at", "by", "as",
}


def _get_api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")


def _get_model_name() -> str:
    return os.getenv("GEMINI_MODEL") or DEFAULT_MODEL


def _extract_json_block(text: str) -> dict[str, Any] | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _sanitize_query(query: str, fallback_query: str) -> str:
    query = query.replace("\"", "").replace("'", "").strip()
    query = re.sub(r"[^A-Za-z\s]", " ", query)
    words = [w.lower() for w in query.split() if w.strip()]
    words = [w for w in words if w not in STOPWORDS]
    if not words:
        words = fallback_query.split()
    if len(words) < 4:
        words = (words + fallback_query.split())[:4]
    if len(words) > 10:
        words = words[:10]
    return " ".join(words)


def _compute_scene_count(audio_duration_sec: float, max_scenes: int) -> int:
    if max_scenes <= 0:
        return 1
    target = round(audio_duration_sec / 4.0) if audio_duration_sec > 0 else PREFERRED_MIN_SCENES
    target = max(PREFERRED_MIN_SCENES, min(PREFERRED_MAX_SCENES, target))
    target = min(target, max_scenes)
    while target > 1 and audio_duration_sec / target < MIN_SCENE_SEC:
        target -= 1
    while target < max_scenes and audio_duration_sec / target > MAX_SCENE_SEC:
        target += 1
    return max(1, min(target, max_scenes))


def _clamp_durations(durations: list[float], total: float) -> list[float]:
    durations = durations[:]
    for _ in range(10):
        total_now = sum(durations)
        if total_now == 0:
            durations = [total / len(durations)] * len(durations)
            continue
        scale = total / total_now
        durations = [d * scale for d in durations]
        durations = [min(max(d, MIN_SCENE_SEC), MAX_SCENE_SEC) for d in durations]
        diff = total - sum(durations)
        if abs(diff) < 0.01:
            break
        adjustable = [i for i, d in enumerate(durations) if MIN_SCENE_SEC < d < MAX_SCENE_SEC]
        if not adjustable:
            break
        step = diff / len(adjustable)
        for idx in adjustable:
            durations[idx] = min(max(durations[idx] + step, MIN_SCENE_SEC), MAX_SCENE_SEC)

    diff = total - sum(durations)
    if durations:
        durations[-1] = min(max(durations[-1] + diff, MIN_SCENE_SEC), MAX_SCENE_SEC)
    return durations


def _rescale_durations(durations: list[float], total: float) -> list[float]:
    if not durations:
        return durations
    durations = _clamp_durations(durations, total)
    diff = total - sum(durations)
    if abs(diff) > 0.001:
        durations[-1] = min(max(durations[-1] + diff, MIN_SCENE_SEC), MAX_SCENE_SEC)
    return durations


def _fallback_plan(script_text_ar: str, audio_duration_sec: float, max_scenes: int) -> dict:
    sentences = [s.strip() for s in re.split(r"[.!?؟\n]+", script_text_ar) if s.strip()]
    scene_count = _compute_scene_count(audio_duration_sec, max_scenes)
    if not sentences:
        sentences = [script_text_ar.strip()] if script_text_ar.strip() else ["..."]
    while len(sentences) < scene_count:
        sentences.append(sentences[-1])

    durations = [audio_duration_sec / scene_count] * scene_count
    durations = _rescale_durations(durations, audio_duration_sec)

    scenes = []
    for idx in range(scene_count):
        text = sentences[idx % len(sentences)]
        fallback_query = FALLBACK_QUERIES[idx % len(FALLBACK_QUERIES)]
        scenes.append({
            "i": idx + 1,
            "dur": round(durations[idx], 2),
            "text": text,
            "query": fallback_query,
        })

    return {
        "style": {"transition_sec": 0.35},
        "scenes": scenes,
    }


def _validate_plan(plan: dict, script_text_ar: str, audio_duration_sec: float, max_scenes: int) -> dict:
    scenes = plan.get("scenes") if isinstance(plan, dict) else None
    if not isinstance(scenes, list) or not scenes:
        return _fallback_plan(script_text_ar, audio_duration_sec, max_scenes)

    scene_count = min(len(scenes), max_scenes)
    scene_count = max(1, scene_count)
    scenes = scenes[:scene_count]

    fallback_texts = [s.strip() for s in re.split(r"[.!?؟\n]+", script_text_ar) if s.strip()]
    if not fallback_texts:
        fallback_texts = [script_text_ar.strip()] if script_text_ar.strip() else ["..."]

    normalized = []
    for idx, scene in enumerate(scenes):
        text = scene.get("text") if isinstance(scene, dict) else None
        if not isinstance(text, str) or not text.strip():
            text = fallback_texts[idx % len(fallback_texts)]

        query = scene.get("query") if isinstance(scene, dict) else ""
        fallback_query = FALLBACK_QUERIES[idx % len(FALLBACK_QUERIES)]
        query = _sanitize_query(query, fallback_query)

        dur = scene.get("dur") if isinstance(scene, dict) else None
        if not isinstance(dur, (int, float)):
            dur = audio_duration_sec / scene_count if scene_count else audio_duration_sec

        normalized.append({
            "i": idx + 1,
            "dur": float(dur),
            "text": text.strip(),
            "query": query,
        })

    durations = _rescale_durations([s["dur"] for s in normalized], audio_duration_sec)
    for scene, dur in zip(normalized, durations):
        scene["dur"] = round(dur, 2)

    if abs(sum(scene["dur"] for scene in normalized) - audio_duration_sec) > 0.3:
        normalized = _fallback_plan(script_text_ar, audio_duration_sec, max_scenes)["scenes"]

    return {
        "style": {"transition_sec": 0.35},
        "scenes": normalized,
    }


def _call_gemini(prompt: str) -> dict[str, Any] | None:
    api_key = _get_api_key()
    if not api_key:
        return None

    try:
        import google.generativeai as genai
    except ImportError:
        genai = None

    if genai:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel(_get_model_name())
            response = model.generate_content(prompt)
            text = response.text if hasattr(response, "text") else ""
            if not text:
                return None
            return _extract_json_block(text)
        except Exception:
            return None

    try:
        import requests
    except ImportError:
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{_get_model_name()}:generateContent?key={api_key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 1024,
        },
    }

    try:
        response = requests.post(url, json=payload, timeout=30)
        if not response.ok:
            return None
        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            return None
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts)
        if not text:
            return None
        return _extract_json_block(text)
    except Exception:
        return None


def plan_scenes(script_text_ar: str, audio_duration_sec: float, max_scenes: int = 6) -> dict:
    scene_count = _compute_scene_count(audio_duration_sec, max_scenes)
    prompt = (
        "Return only JSON for a montage scene plan. "
        "Format: {\"style\": {\"transition_sec\": 0.35}, "
        "\"scenes\": [{\"i\": 1, \"dur\": 3.5, \"text\": \"...\", "
        "\"query\": \"english b roll query\"}]}\n"
        f"Total duration: {audio_duration_sec:.2f} seconds. "
        f"Scene count: {scene_count}. "
        "Each dur must be between 1.5 and 6.0 seconds. "
        "Queries must be English, visual, 4-10 words, no quotes, no brands or celebrities. "
        "Use the provided Arabic script text for scene text. "
        f"Script:\n{script_text_ar}"
    )

    plan = _call_gemini(prompt)
    if not isinstance(plan, dict):
        return _fallback_plan(script_text_ar, audio_duration_sec, max_scenes)

    return _validate_plan(plan, script_text_ar, audio_duration_sec, max_scenes)
