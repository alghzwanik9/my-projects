from __future__ import annotations
import re
from dataclasses import dataclass
from typing import List

@dataclass
class Scene:
    text: str
    query: str

# قاموس بسيط (تقدر تكبره مع الوقت)
AR2EN = {
    "ذكاء اصطناعي": "artificial intelligence",
    "ذكاء": "artificial intelligence",
    "تقنية": "technology",
    "برمجة": "programming code",
    "كمبيوتر": "computer screen",
    "تطبيق": "mobile app",
    "إنترنت": "internet network",
    "بيانات": "data analytics",
    "روبوت": "robot",
    "تعلم": "learning education",
    "جامعة": "university students",
    "كتاب": "book reading",
    "صحة": "healthy lifestyle",
    "رياضة": "fitness workout",
    "فلوس": "money finance",
    "استثمار": "investment stock market",
    "شركة": "business office meeting",
    "نجاح": "success motivation",
    "سيارة": "car driving",
    "سفر": "travel city",
    "طبيعة": "nature landscape",
}

GENERIC_FALLBACK = [
    "abstract background",
    "technology background",
    "city timelapse",
    "business meeting",
    "nature calm",
]

def clean_text(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s

def split_sentences_ar(text: str) -> list[str]:
    # تقسيم خفيف
    parts = re.split(r"(?<=[\.\!\؟\!،])\s+", clean_text(text))
    return [p.strip() for p in parts if p.strip()]

def chunk_sentences(sentences: list[str], target_scenes: int) -> list[str]:
    if not sentences:
        return []
    target_scenes = max(1, min(10, target_scenes))
    # دمج الجمل عشان نطلع عدد مشاهد قريب من target
    if len(sentences) <= target_scenes:
        return sentences

    chunks = []
    per = max(1, len(sentences) // target_scenes)
    cur = []
    for i, s in enumerate(sentences):
        cur.append(s)
        if (i + 1) % per == 0 and len(chunks) < target_scenes - 1:
            chunks.append(" ".join(cur))
            cur = []
    if cur:
        chunks.append(" ".join(cur))
    return chunks

def ar_to_query(scene_text: str, scene_index: int) -> str:
    t = scene_text
    t_norm = t

    # أولاً: عبارات مركبة
    for k, v in AR2EN.items():
        if k in t_norm:
            return v

    # ثانياً: كلمات مفردة (نستخرج كلمات “مهمة” بشكل بسيط)
    words = re.findall(r"[اأإآء-ي]+", t_norm)
    words = [w for w in words if len(w) >= 3]
    for w in words:
        if w in AR2EN:
            return AR2EN[w]

    # fallback عام لكن متنوع
    return GENERIC_FALLBACK[scene_index % len(GENERIC_FALLBACK)]

def plan_scenes(script_text: str, max_clips: int = 5) -> List[Scene]:
    sents = split_sentences_ar(script_text)
    chunks = chunk_sentences(sents, target_scenes=max_clips)
    scenes: List[Scene] = []
    for i, c in enumerate(chunks[:max_clips]):
        scenes.append(Scene(text=c, query=ar_to_query(c, i)))
    return scenes
