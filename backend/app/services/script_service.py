from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.config import OUTPUTS_DIR
from pipelines.script_generation import generate_script
from app.services.ai_service import generate_visual_plan  # ✅ NEW


def _build_srt(scenes: list[dict]) -> str:
    lines = []
    for index, scene in enumerate(scenes, start=1):
        start = _format_timestamp(scene["start"])
        end = _format_timestamp(scene["end"])
        narration = scene["narration"].strip()
        lines.extend([str(index), f"{start} --> {end}", narration, ""])
    return "\n".join(lines).strip() + "\n"


def _format_timestamp(seconds: int) -> str:
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d},000"


def _write_srt(contents: str, outputs_dir: Path) -> str:
    outputs_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    filename = f"captions_{timestamp}_{uuid4().hex[:8]}.srt"
    path = outputs_dir / filename
    path.write_text(contents, encoding="utf-8")
    return f"outputs/{filename}"


def build_script_output(prompt: str, duration: int, language: str, tone: str) -> dict:
    script = generate_script(prompt=prompt, duration=duration, language=language, tone=tone)
    scenes = [asdict(scene) for scene in script.scenes]

    srt_contents = _build_srt(scenes)
    srt_path = _write_srt(srt_contents, OUTPUTS_DIR)

    # ✅ NEW: بناء خطة المشاهد المرئية من النص النهائي
    visual_scenes = generate_visual_plan(script.full_script)

    return {
        "script": script.full_script,
        "scenes": scenes,
        "srt_path": srt_path,
        "visual_scenes": visual_scenes,
    }
