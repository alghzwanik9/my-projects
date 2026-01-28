# tools/render_shorts.py
# Usage:
#   python tools/render_shorts.py <audio.mp3> <script.txt> <out.mp4> [clips_dir]
#
# Produces 9:16 short video with:
# - If scenes.json + clips exist -> montage with transitions
# - Else -> solid background
# - Arabic captions (ASS via libass)
# - Audio mixed in
#
# Requirements:
# - ffmpeg, ffprobe in PATH
# - A font that supports Arabic (recommended: Arial or Noto Naskh Arabic)

from __future__ import annotations

import json
import math
import re
import subprocess
from pathlib import Path
import sys

# Fix Windows console encoding (avoid cp1252 issues)
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

W = 1080
H = 1920
FPS = 30

# Background (fallback)
BG_COLOR = "#0b1220"  # dark

# Caption styling (ASS)
FONT_NAME = "Arial"
FONT_SIZE = 64
OUTLINE = 4
SHADOW = 1
MARGIN_V = 120  # distance from bottom
MAX_CHARS_PER_LINE = 22


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    print("\nRUN CMD:\n", " ".join(cmd))
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    if p.stdout:
        print("\n--- STDOUT ---\n", p.stdout[:4000])
    if p.stderr:
        print("\n--- STDERR ---\n", p.stderr[:4000])
    if p.returncode != 0:
        # On Windows returncode may appear as large unsigned -> still treat as error
        raise RuntimeError(f"ERROR: Command failed (code={p.returncode})\n{p.stderr[-1200:]}")
    return p


def _require_tools() -> None:
    _run(["ffmpeg", "-version"])
    _run(["ffprobe", "-version"])


def _ffprobe_duration_sec(audio_path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nw=1:nk=1",
        str(audio_path),
    ]
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    try:
        return float((p.stdout or "0").strip())
    except Exception:
        return 0.0


def clean_text(t: str) -> str:
    t = (t or "").strip()
    # normalize spaces
    t = re.sub(r"\s+", " ", t)
    # remove weird quotes
    t = t.replace("“", '"').replace("”", '"').replace("’", "'")
    return t


def _wrap_lines(text: str, max_chars: int = MAX_CHARS_PER_LINE) -> list[str]:
    # naive wrapping by spaces, works for Arabic reasonably
    words = (text or "").split()
    if not words:
        return []
    lines = []
    cur = ""
    for w in words:
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= max_chars:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _sec_to_ass_time(sec: float) -> str:
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"  # H:MM:SS.xx


def make_timed_subs(script_text: str, total_duration: float) -> list[dict]:
    """
    Simple timing: splits script into lines then distributes time proportional to words.
    For best results later we’ll align by words, but this is solid for now.
    """
    script_text = clean_text(script_text)
    if not script_text:
        return []

    # Split by punctuation pauses
    chunks = re.split(r"(?<=[\.\!\؟\?…،])\s+", script_text)
    chunks = [c.strip() for c in chunks if c.strip()]
    if not chunks:
        chunks = [script_text]

       # Convert chunks to display lines with wrapping
    lines = []
    for ch in chunks:
        wrapped = _wrap_lines(ch)
        if wrapped:
            # keep max 2 lines per chunk to avoid spam
            if len(wrapped) <= 2:
                lines.append(r"\N".join(wrapped))
            else:
                lines.append(r"\N".join(wrapped[:2]))
        else:
            lines.append(ch)



    # weights by word count
    weights = []
    for ch in chunks:
        wc = len(ch.split())
        weights.append(max(1, wc))

    wsum = float(sum(weights)) if weights else 1.0
    # keep a tiny minimum per subtitle
    min_d = 0.9
    durs = [max(min_d, total_duration * (w / wsum)) for w in weights]

    # normalize to total_duration
    diff = total_duration - sum(durs)
    if abs(diff) > 0.01 and durs:
        step = diff / len(durs)
        durs = [max(min_d, d + step) for d in durs]

    subs = []
    t = 0.0
    for i, (line, dur) in enumerate(zip(lines, durs), start=1):
        start = t
        end = min(total_duration, t + dur)
        if end - start < 0.2:
            end = min(total_duration, start + 0.6)
        subs.append({"i": i, "start": start, "end": end, "text": line})
        t = end
        if t >= total_duration:
            break

    return subs


def build_ass(subs: list[dict], ass_path: Path) -> None:
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT_NAME},{FONT_SIZE},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,{OUTLINE},{SHADOW},2,80,80,{MARGIN_V},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for s in subs:
        start = _sec_to_ass_time(s["start"])
        end = _sec_to_ass_time(s["end"])
        text = s["text"].replace("\n", r"\N")
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n")

    ass_path.write_text("".join(lines), encoding="utf-8")


def _pick_scene_clips(run_dir: Path, clips_dir: Path | None = None) -> list[Path]:
    clips_root = clips_dir if clips_dir else (run_dir / "clips")
    if not clips_root.exists():
        return []

    clips: list[Path] = []

    # 1) الشكل المتوقع: clips/scene_01/*.mp4
    for scene_dir in sorted(clips_root.glob("scene_*")):
        mp4s = sorted(scene_dir.glob("*.mp4"))
        if mp4s:
            clips.append(mp4s[0])

    # 2) fallback: أي mp4 داخل clips مباشرة/بأي عمق
    if not clips:
        mp4s = sorted(clips_root.rglob("*.mp4"))
        clips = mp4s[:12]  # حد أعلى

    return clips



def _build_montage_xfade(scene_videos: list[Path], durs: list[float], out_montage: Path, transition_sec: float = 0.35) -> None:
    if len(scene_videos) == 1:
        # just copy
        _run(["ffmpeg", "-y", "-i", str(scene_videos[0]), "-c", "copy", str(out_montage)])
        return

    inputs = []
    for v in scene_videos:
        inputs += ["-i", str(v)]

    fc = []
    for i in range(len(scene_videos)):
        fc.append(f"[{i}:v]setpts=PTS-STARTPTS[v{i}];")

    acc = 0.0
    cur_label = "v0"
    for i in range(1, len(scene_videos)):
        acc += durs[i - 1]
        offset = acc - (transition_sec * i)
        nxt = f"v{i}"
        out = f"vx{i}"
        fc.append(
            f"[{cur_label}][{nxt}]xfade=transition=fade:duration={transition_sec}:offset={max(0.0, offset):.3f}[{out}];"
        )
        cur_label = out

    filter_complex = "".join(fc)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", f"[{cur_label}]",
        "-r", str(FPS),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        str(out_montage),
    ]
    _run(cmd)


def render(audio_path: Path, script_path: Path, out_video: Path, clips_dir: Path | None = None) -> None:
    _require_tools()

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    out_video.parent.mkdir(parents=True, exist_ok=True)

    script_text = clean_text(script_path.read_text(encoding="utf-8", errors="ignore"))
    duration = _ffprobe_duration_sec(audio_path)
    if duration <= 0:
        duration = 15.0

    # captions.ass
    ass_path = out_video.parent / "captions.ass"
    subs = make_timed_subs(script_text, duration)
    build_ass(subs, ass_path)

    # Windows: escape ":" in drive letter for filter parsing
    ass_filter_path = ass_path.resolve().as_posix()
    ass_escaped = ass_filter_path.replace(":", r"\:")
    # ✅ IMPORTANT FIX (your working solution)
    vf_ass = f"ass=filename='{ass_escaped}'"

    run_dir = out_video.parent
    scenes_path = run_dir / "scenes.json"
    clips = _pick_scene_clips(run_dir, clips_dir=clips_dir)

    # =========================
    # SMART MONTAGE PATH
    # =========================
    if scenes_path.exists() and clips:
        data = json.loads(scenes_path.read_text(encoding="utf-8", errors="ignore") or "{}")
        scenes = data.get("scenes") or []
        if scenes:
            temp_dir = run_dir / "_tmp_scenes"
            temp_dir.mkdir(parents=True, exist_ok=True)

            scene_videos: list[Path] = []
            durs: list[float] = []

            for i, sc in enumerate(scenes):
                dur_i = float(sc.get("dur", 3.5))
                dur_i = max(1.5, dur_i)
                durs.append(dur_i)

                clip = clips[i % len(clips)]
                out_i = temp_dir / f"scene_{i+1:02d}.mp4"

                # cinematic: scale/crop to 9:16 + trim
                vf_scene = (
                    f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                    f"crop={W}:{H},fps={FPS},"
                    f"trim=0:{dur_i},setpts=PTS-STARTPTS"
                )

                cmd_scene = [
                    "ffmpeg", "-y",
                    "-i", str(clip),
                    "-vf", vf_scene,
                    "-t", str(dur_i),
                    "-an",
                    "-c:v", "libx264",
                    "-pix_fmt", "yuv420p",
                    str(out_i),
                ]
                _run(cmd_scene)
                scene_videos.append(out_i)

            montage = run_dir / "_montage.mp4"
            transition_sec = float((data.get("style") or {}).get("transition_sec", 0.35))
            _build_montage_xfade(scene_videos, durs, montage, transition_sec=transition_sec)

            # Add captions + audio
            cmd_final = [
                "ffmpeg", "-y",
                "-i", str(montage),
                "-i", str(audio_path),
                "-vf", vf_ass,
                "-shortest",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                str(out_video),
            ]
            _run(cmd_final)

            if not out_video.exists() or out_video.stat().st_size < 50_000:
                raise RuntimeError(f"Render finished but output missing/too small: {out_video}")
            return

    # =========================
    # FALLBACK: SOLID BG PATH
    # =========================
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"color=c={BG_COLOR}:s={W}x{H}:r={FPS}:d={duration}",
        "-i",
        str(audio_path),
        "-vf",
        vf_ass,
        "-shortest",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(out_video),
    ]
    _run(cmd)

    if not out_video.exists() or out_video.stat().st_size < 50_000:
        raise RuntimeError(f"Render finished but output missing/too small: {out_video}")


def main() -> None:
    import sys

    if len(sys.argv) < 4:
        print("Usage: python tools/render_shorts.py <audio.mp3> <script.txt> <out.mp4> [clips_dir]")
        raise SystemExit(2)

    audio_path = Path(sys.argv[1]).resolve()
    script_path = Path(sys.argv[2]).resolve()
    out_video = Path(sys.argv[3]).resolve()
    clips_dir = None
    if len(sys.argv) >= 5:
        clips_dir = Path(sys.argv[4]).resolve()

    render(audio_path, script_path, out_video, clips_dir=clips_dir)
    print(f"\nDone: {out_video}")


if __name__ == "__main__":
    main()
