from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# إضافة مسار backend إلى sys.path للوصول إلى services
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

try:
    from app.services.background_service import get_background_config, generate_ffmpeg_background
except ImportError:
    # Fallback إذا لم تكن الخدمة متاحة
    def get_background_config(text: str):
        return {"colors": {"primary": "#0b0f19", "secondary": "#1a1f2e", "accent": "#2a2f3e"}}
    
    def generate_ffmpeg_background(config: dict, width: int = 1080, height: int = 1920) -> str:
        return f"color=c=#0b0f19:s={width}x{height}:r=30,format=rgba,geq=r='X/W*20+20':g='Y/H*20+20':b='40':a=255"


def run(cmd: list[str]):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed:\n{' '.join(cmd)}\n\nSTDERR:\n{p.stderr}")
    return p.stdout.strip()


def ffprobe_duration(audio_path: Path) -> float:
    out = run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path)
    ])
    return float(out)


def srt_time(t: float) -> str:
    if t < 0:
        t = 0
    ms = int(round(t * 1000))
    h = ms // 3600000
    ms %= 3600000
    m = ms // 60000
    ms %= 60000
    s = ms // 1000
    ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def chunk_text(text: str, words_per_line: int = 5) -> list[str]:
    text = " ".join(text.replace("\n", " ").split())
    words = text.split(" ")
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i + words_per_line]).strip()
        if chunk:
            chunks.append(chunk)
        i += words_per_line
    return chunks


def write_srt(chunks: list[str], total_dur: float, out_srt: Path):
    weights = [max(1, len(c)) for c in chunks]
    wsum = sum(weights)

    min_seg = 0.9
    max_seg = 2.2

    raw = [(w / wsum) * total_dur for w in weights]
    segs = [min(max(r, min_seg), max_seg) for r in raw]

    scale = total_dur / sum(segs)
    segs = [s * scale for s in segs]

    t = 0.0
    lines = []
    for idx, (txt, dur) in enumerate(zip(chunks, segs), start=1):
        t1 = t
        t2 = t + dur
        lines.append(str(idx))
        lines.append(f"{srt_time(t1)} --> {srt_time(t2)}")
        lines.append(txt)
        lines.append("")
        t = t2

    out_srt.write_text("\n".join(lines), encoding="utf-8")


def ffmpeg_escape(p: str) -> str:
    return p.replace("\\", "/").replace(":", r"\:")


def main():
    if len(sys.argv) < 3:
        print("Usage: python render_shorts.py <audio_path> '<text>' [out_mp4]")
        sys.exit(1)

    audio_path = Path(sys.argv[1]).resolve()
    text = sys.argv[2]
    out_mp4 = Path(sys.argv[3]).resolve() if len(sys.argv) >= 4 else audio_path.parent / "shorts.mp4"

    dur = ffprobe_duration(audio_path)

    srt_path = audio_path.parent / "captions.srt"
    chunks = chunk_text(text, words_per_line=5)
    write_srt(chunks, dur, srt_path)

    srt_ff = ffmpeg_escape(str(srt_path))

    # 🎨 تحليل النص واختيار خلفية مناسبة
    bg_config = get_background_config(text)
    bg = generate_ffmpeg_background(bg_config, width=1080, height=1920)
    
    # 🎨 ستايل نص احترافي محسّن
    # استخدام لون من الخلفية مع تباين جيد
    primary_color = bg_config["colors"]["primary"].lstrip("#")
    # تحويل hex إلى BGR للـ ASS
    r, g, b = int(primary_color[0:2], 16), int(primary_color[2:4], 16), int(primary_color[4:6], 16)
    outline_color = f"&H00{r:02x}{g:02x}{b:02x}&"
    
    style = (
        "FontName=Arial,"
        "Fontsize=52,"  # حجم أكبر قليلاً
        "PrimaryColour=&H00FFFFFF&,"  # أبيض
        f"OutlineColour={outline_color},"  # لون من الخلفية
        "BorderStyle=3,"
        "Outline=3,"  # حدود أسمك
        "Shadow=2,"  # ظل خفيف
        "Alignment=2,"  # وسط
        "MarginV=200,"  # مسافة من الأسفل
        "Bold=1"  # نص عريض
    )

    # 🎬 تحسين جودة الفيديو
    # إضافة تأثيرات بصرية وتحسينات
    video_filters = [
        f"subtitles='{srt_ff}':force_style='{style}'",
        "scale=1080:1920:flags=lanczos",  # تحسين التكبير
        "eq=contrast=1.1:brightness=0.02",  # تحسين التباين والسطوع
    ]
    
    video_filter = ",".join(video_filters)
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", bg,
        "-i", str(audio_path),
        "-t", f"{dur:.3f}",
        "-vf", video_filter,
        "-c:v", "libx264",
        "-preset", "medium",  # توازن بين السرعة والجودة
        "-crf", "23",  # جودة عالية
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "44100",  # معدل عينة أفضل
        "-shortest",
        "-movflags", "+faststart",  # تحسين التحميل
        str(out_mp4)
    ]

    run(cmd)

    print(json.dumps({
        "audio": str(audio_path),
        "video": str(out_mp4),
        "srt": str(srt_path),
        "duration": dur,
        "background_theme": bg_config.get("theme", "default"),
        "background_colors": bg_config.get("colors", {})
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
