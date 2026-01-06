from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256


@dataclass
class Scene:
    start: int
    end: int
    narration: str
    on_screen_text: str
    visual_hint: str


@dataclass
class ScriptResult:
    full_script: str
    scenes: list[Scene]


def _seed_phrase(prompt: str, tone: str, language: str) -> str:
    seed = sha256(f"{prompt}:{tone}:{language}".encode("utf-8")).hexdigest()[:6]
    return f"Seed {seed}"


def generate_script(prompt: str, duration: int, language: str, tone: str) -> ScriptResult:
    if not (15 <= duration <= 60):
        raise ValueError("Duration must be between 15 and 60 seconds.")

    scene_count = max(3, min(6, duration // 10))
    scene_length = max(3, duration // scene_count)
    seed_phrase = _seed_phrase(prompt, tone, language)

    scenes: list[Scene] = []
    current = 0
    for index in range(scene_count):
        start = current
        end = min(duration, start + scene_length)
        current = end
        narration = (
            f"{seed_phrase}: {prompt.strip().capitalize()} — scene {index + 1} in a {tone} tone."
        )
        on_screen_text = f"{prompt.strip().title()} ({index + 1}/{scene_count})"
        visual_hint = f"Highlight {prompt.strip()} with {tone} visuals."
        scenes.append(Scene(start=start, end=end, narration=narration, on_screen_text=on_screen_text, visual_hint=visual_hint))

    full_script = "\n".join(scene.narration for scene in scenes)
    return ScriptResult(full_script=full_script, scenes=scenes)
