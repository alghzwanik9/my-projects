# tools/render_shorts.py
# Usage:
#   python tools/render_shorts.py <audio.mp3> <script.txt> <out.mp4>
#
# Produces 9:16 short video with:
# - background (clips if exist, else images, else dynamic solid)
# - Arabic captions (ASS via libass)
# - audio mixed in
#
# Requirements:
# - ffmpeg, ffprobe in PATH
# - A font that supports Arabic (recommended: Noto Naskh Arabic or Arial)
#
import sys
import re
import json
import subprocess
from pathlib import Path

W = 1080
H = 1920
FPS = 30

# Background settings
BG_COLOR = "#0b1220"  # dark

# Caption styling (ASS)
FONT_NAME = "Arial"
FONT_SIZE = 64
OUTLINE = 4
SHADOW = 1
MARGIN_V = 120
MAX_CHARS_PER_LINE = 22


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def require_tools():
    for t in ["ffmpeg", "ffprobe"]:
        r = run([t, "-version"])
        if r.returncode != 0:
            raise RuntimeError(f"{t} not found. Install FFmpeg and ensure it's in PATH.")


def get_audio_duration_sec(audio_path: Path) -> float:
    r = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(audio_path),
        ]
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {r.stderr[:400]}")
    data = json.loads(r.stdout)
    dur = float(data["format"]["duration"])
    return max(0.1, dur + 0.15)  # small padding


def clean_text(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace(" ،", "،").replace(" .", ".").replace(" ؟", "؟").replace(" !", "!")
    return text


def split_sentences_ar(text: str) -> list[str]:
    parts = re.split(r"(?<=[\.\!\؟\!،])\s+", text)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) <= 1 and len(text) > MAX_CHARS_PER_LINE:
        parts = chunk_by_length(text, MAX_CHARS_PER_LINE * 2)
    return parts


def chunk_by_length(text: str, maxlen: int) -> list[str]:
    words = text.split()
    lines = []
    cur = []
    n = 0
    for w in words:
        if n + len(w) + (1 if cur else 0) > maxlen:
            if cur:
                lines.append(" ".join(cur))
            cur = [w]
            n = len(w)
        else:
            cur.append(w)
            n += len(w) + (1 if len(cur) > 1 else 0)
    if cur:
        lines.append(" ".join(cur))
    return lines


def wrap_for_two_lines(text: str, max_chars_per_line: int) -> str:
    words = text.split()
    lines = []
    cur = []
    count = 0

    for i, w in enumerate(words):
        add = len(w) + (1 if cur else 0)
        if count + add > max_chars_per_line:
            lines.append(" ".join(cur))
            if len(lines) == 1:
                rest = words[i:]
                return lines[0] + r"\N" + " ".join(rest)
            cur = [w]
            count = len(w)
        else:
            cur.append(w)
            count += add

    if cur:
        lines.append(" ".join(cur))

    if len(lines) == 1:
        return lines[0]
    return lines[0] + r"\N" + lines[1]


def ass_time(t: float) -> str:
    if t < 0:
        t = 0
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = int(t % 60)
    cs = int(round((t - int(t)) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def build_ass(subs: list[tuple[float, float, str]], out_ass: Path):
    header = f"""[Script Info]
Title: captions
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT_NAME},{FONT_SIZE},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,{OUTLINE},{SHADOW},2,60,60,{MARGIN_V},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for (st, en, txt) in subs:
        st_s = ass_time(st)
        en_s = ass_time(en)
        safe = txt.replace("\n", " ").replace("\r", " ").replace("{", "").replace("}", "")
        lines.append(f"Dialogue: 0,{st_s},{en_s},Default,,0,0,0,,{safe}\n")

    out_ass.write_text("".join(lines), encoding="utf-8")


def make_timed_subs(script_text: str, duration: float) -> list[tuple[float, float, str]]:
    script_text = clean_text(script_text)
    chunks = split_sentences_ar(script_text)
    display = [wrap_for_two_lines(c, MAX_CHARS_PER_LINE) for c in chunks]

    weights = [max(12, len(re.sub(r"\s+", "", c))) for c in chunks]
    total = sum(weights) if weights else 1

    min_sec = 1.4
    max_sec = 4.8
    subs = []
    t = 0.0
    for w, txt in zip(weights, display):
        span = duration * (w / total)
        span = max(min_sec, min(max_sec, span))
        st = t
        en = min(duration, t + span)
        if en - st < 0.6:
            en = min(duration, st + 0.8)
        subs.append((st, en, txt))
        t = en

    if subs and subs[-1][1] < duration:
        st, _, txt = subs[-1]
        subs[-1] = (st, duration, txt)

    return subs


def _escape_ass_path_for_ffmpeg(p: Path) -> str:
    """
    ffmpeg filter needs escaping on Windows:
    - drive letter ":" -> "\\:"
    - single quote "'" -> "\\'"
    """
    s = p.resolve().as_posix()
    s = s.replace(":", r"\:")
    s = s.replace("'", r"\'")
    return s


def _dynamic_bg_filter(script_text: str, duration: float) -> str:
    """
    Background lavfi string. No imports from app.* (so it works when called from FastAPI subprocess).
    Keeps it stable and fast.
    """
    t = (script_text or "").lower()

    # very simple themes
    if any(k in t for k in ["ذكاء", "اصطناعي", "تقنية", "برمجة", "كمبيوتر", "ai", "tech"]):
        c1, c2 = "#1a1a2e", "#16213e"
    elif any(k in t for k in ["عمل", "تجارة", "استثمار", "مال", "شركة", "business"]):
        c1, c2 = "#0f2027", "#203a43"
    elif any(k in t for k in ["صحة", "رياضة", "لياقة", "تمرين", "health"]):
        c1, c2 = "#1a2e1a", "#2d4a2d"
    elif any(k in t for k in ["تعلم", "تعليم", "دراسة", "جامعة", "كتاب", "education"]):
        c1, c2 = "#2c1810", "#3d2817"
    else:
        c1, c2 = BG_COLOR, "#1a1f2e"

    # base color with duration
    # plus a soft overlay box to make it feel less flat
    return (
        f"color=c={c1}:s={W}x{H}:r={FPS}:d={duration},format=rgba,"
        f"drawbox=x=0:y=0:w={W}:h={H}:color={c2}@0.25:t=fill,"
        f"eq=brightness=0.02:contrast=1.05"
    )


def render(audio_path: Path, script_path: Path, out_video: Path):
    require_tools()

    if not audio_path.exists():
        raise FileNotFoundError(f"Audio not found: {audio_path}")
    if not script_path.exists():
        raise FileNotFoundError(f"Script not found: {script_path}")

    script_text = clean_text(script_path.read_text(encoding="utf-8", errors="ignore"))
    duration = get_audio_duration_sec(audio_path)

    out_video.parent.mkdir(parents=True, exist_ok=True)

    # captions.ass
    ass_path = out_video.parent / "captions.ass"
    subs = make_timed_subs(script_text, duration)
    build_ass(subs, ass_path)

    ass_escaped = _escape_ass_path_for_ffmpeg(ass_path)

    # ✅ 1) لو فيه CLIPS داخل outputs/<id>/clips نستخدمها كمشاهد (أفضل)
    clips_dir = out_video.parent / "clips"
    clip_files = []
    if clips_dir.exists():
        clip_files = sorted([p for p in clips_dir.iterdir() if p.suffix.lower() == ".mp4"])

    if clip_files:
        per = max(2.5, duration / len(clip_files))
        cmd = ["ffmpeg", "-y"]

        # Inputs: clips + audio
        for clip in clip_files:
            cmd += ["-stream_loop", "-1", "-i", str(clip)]  # loop clip if short
        cmd += ["-i", str(audio_path)]

        filters = []
        for i in range(len(clip_files)):
            filters.append(
                f"[{i}:v]"
                f"scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},setsar=1,"
                f"trim=duration={per:.3f},setpts=PTS-STARTPTS,"
                f"fps={FPS},format=yuv420p"
                f"[v{i}]"
            )

        concat_inputs = "".join([f"[v{i}]" for i in range(len(clip_files))])
        filters.append(f"{concat_inputs}concat=n={len(clip_files)}:v=1:a=0[bg]")
        filters.append(f"[bg]ass=filename='{ass_escaped}',fps={FPS},format=yuv420p[vout]")

        filter_complex = ";".join(filters)
        audio_index = len(clip_files)

        cmd += [
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", f"{audio_index}:a:0",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            "-r", str(FPS),
            "-movflags", "+faststart",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(out_video),
        ]

        r = run(cmd)
        if r.returncode != 0:
            raise RuntimeError(f"FFmpeg failed:\n{(r.stderr or '')[-1600:]}")
        print(f"OK: {out_video}")
        return

    # ✅ 2) لو فيه صور داخل outputs/<id>/images نستخدمها
    images_dir = out_video.parent / "images"
    image_files = []
    if images_dir.exists():
        image_files = sorted([p for p in images_dir.iterdir() if p.suffix.lower() in [".jpg", ".jpeg", ".png"]])

    if image_files:
        per = max(2.5, duration / len(image_files))
        cmd = ["ffmpeg", "-y"]

        for img in image_files:
            cmd += ["-loop", "1", "-t", f"{per:.3f}", "-i", str(img)]
        cmd += ["-i", str(audio_path)]

        filters = []
        for i in range(len(image_files)):
            filters.append(
                f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H},setsar=1,fps={FPS},format=yuv420p[v{i}]"
            )

        concat_inputs = "".join([f"[v{i}]" for i in range(len(image_files))])
        filters.append(f"{concat_inputs}concat=n={len(image_files)}:v=1:a=0[bg]")
        filters.append(f"[bg]ass=filename='{ass_escaped}',fps={FPS},format=yuv420p[vout]")

        filter_complex = ";".join(filters)
        audio_index = len(image_files)

        cmd = [
            "ffmpeg", "-y",
            *sum([["-loop", "1", "-t", f"{per:.3f}", "-i", str(img)] for img in image_files], []),
            "-i", str(audio_path),
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-map", f"{audio_index}:a:0",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-pix_fmt", "yuv420p",
            "-r", str(FPS),
            "-movflags", "+faststart",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            str(out_video),
        ]
    else:
        # ✅ 3) fallback: خلفية ديناميكية حسب النص (بدل color ثابت)
        bg_filter = _dynamic_bg_filter(script_text, duration)

        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            bg_filter,
            "-i",
            str(audio_path),
            "-vf",
            f"ass=filename='{ass_escaped}',fps={FPS},format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(FPS),
            "-movflags",
            "+faststart",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            str(out_video),
        ]

    r = run(cmd)
    if r.returncode != 0:
        hint = ""
        if "fontconfig" in (r.stderr or "").lower() or "no fonts" in (r.stderr or "").lower():
            hint = (
                "\n\n[Hint] Fonts issue. Install an Arabic-supporting font on your system.\n"
                "Recommended: Noto Naskh Arabic (Windows/Linux) or set FONT_NAME to 'Arial'.\n"
            )
        raise RuntimeError(f"FFmpeg failed:\n{(r.stderr or '')[-1600:]}{hint}")

    print(f"OK: {out_video}")


def main():
    if len(sys.argv) != 4:
        print("Usage: python render_shorts.py <audio.mp3> <script.txt> <out.mp4>")
        sys.exit(2)

    audio_path = Path(sys.argv[1]).resolve()
    script_path = Path(sys.argv[2]).resolve()
    out_video = Path(sys.argv[3]).resolve()

    render(audio_path, script_path, out_video)


if __name__ == "__main__":
    main()
