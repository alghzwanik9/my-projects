from __future__ import annotations

import re
from typing import Dict, List


def _split_sentences(text: str) -> List[str]:
    t = re.sub(r"\s+", " ", (text or "").strip())
    if not t:
        return []
    parts = re.split(r"(?<=[\.\!\؟\?…،])\s+", t)
    parts = [p.strip() for p in parts if p.strip()]
    return parts or [t]


def plan_scenes(
    text: str,
    total_duration: float,
    language: str = "ar",
    style: str = "cinematic_motivational",
    min_scene_dur: float = 2.8,
    max_scene_dur: float = 5.0,
    max_scenes: int = 8,
) -> Dict:
    """
    Heuristic smart planner (بدون LLM) — لاحقًا نستبدله بذكاء Gemini/LLM.
    """
    sents = _split_sentences(text)
    if total_duration <= 0:
        total_duration = 15.0

    # هدف: مشهد كل ~3.6 ثانية
    target_n = int(round(total_duration / 3.6))
    target_n = max(4, min(max_scenes, target_n))

    # تجميع الجمل على عدد مشاهد
    chunks: List[str] = []
    cur = ""
    for s in sents:
        if not cur:
            cur = s
        elif len(cur) + 1 + len(s) <= 140:
            cur = cur + " " + s
        else:
            chunks.append(cur)
            cur = s
    if cur:
        chunks.append(cur)

    # لو طلع أقل/أكثر من target_n نوزّع/نقلّص
    # إذا أقل: نجزّئ أطول Chunk
    while len(chunks) < target_n and len(chunks) > 0:
        idx = max(range(len(chunks)), key=lambda i: len(chunks[i]))
        txt = chunks.pop(idx)
        mid = max(1, len(txt) // 2)
        cut = txt.rfind(" ", 0, mid)
        if cut == -1:
            cut = mid
        a, b = txt[:cut].strip(), txt[cut:].strip()
        if a:
            chunks.insert(idx, a)
        if b:
            chunks.insert(idx + 1, b)

    # إذا أكثر: ندمج الأقصر
    while len(chunks) > target_n and len(chunks) > 1:
        idx = min(
            range(len(chunks) - 1),
            key=lambda i: len(chunks[i]) + len(chunks[i + 1]),
        )
        chunks[idx] = (chunks[idx] + " " + chunks[idx + 1]).strip()
        chunks.pop(idx + 1)

    # توزيع المدد حسب طول النص
    weights = [max(1, len(c.split())) for c in chunks]
    wsum = float(sum(weights))
    durs = [(total_duration * (w / wsum)) for w in weights]

    # قصّ/حدود
    durs = [min(max_scene_dur, max(min_scene_dur, d)) for d in durs]

    # ضبط المجموع ليطابق total_duration
    diff = total_duration - sum(durs)
    if abs(diff) > 0.01:
        step = diff / len(durs)
        durs = [max(min_scene_dur, d + step) for d in durs]

    scenes = []
    for i, (chunk, dur) in enumerate(zip(chunks, durs), start=1):
        caption = chunk.strip()
        if len(caption) > 60:
            caption = caption[:60] + "…"
        scenes.append(
            {
                "id": i,
                "dur": round(float(dur), 2),
                "text": chunk,
                "caption": caption,
                "type": "video",
                "motion": "slow_zoom_in",
                "transition": "crossfade",
            }
        )

    return {
        "style": {
            "preset": style,
            "pace": "medium_fast",
            "mood": "cinematic",
            "transition_sec": 0.35,
        },
        "language": language,
        "scenes": scenes,
    }
