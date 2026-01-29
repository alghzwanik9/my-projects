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


VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30
VIDEO_SIZE = f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}"
VF_ENHANCED = "eq=contrast=1.08:saturation=1.06,unsharp=5:5:0.8:3:3:0.4"
AF_LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"
XFADE_DURATION = 0.4


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


def ffprobe_video_duration(video_path: Path) -> float:
    return ffprobe_duration(video_path)


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


def read_text_arg(text_arg: str) -> str:
    text_path = Path(text_arg)
    if text_path.exists():
        return text_path.read_text(encoding="utf-8").strip()
    return text_arg


def build_video_filter(srt_ff: str, style: str, include_scale: bool) -> str:
    filters = [f"subtitles='{srt_ff}':force_style='{style}'"]
    if include_scale:
        filters.append(f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:flags=lanczos")
    filters.append(VF_ENHANCED)
    return ",".join(filters)


def build_audio_filter_complex(voice_idx: int, music_idx: int) -> str:
    return (
        f"[{music_idx}:a]volume=0.3[music];"
        f"[{voice_idx}:a]aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[voice];"
        "[music][voice]sidechaincompress=threshold=0.1:ratio=8:attack=50:release=300[ducked];"
        f"[ducked][voice]amix=inputs=2:duration=first:dropout_transition=2,{AF_LOUDNORM}[aout]"
    )


def _pick_scene_clips(clips_dir: Path) -> list[Path]:
    scenes_path = clips_dir / "scenes.json"
    clip_paths: list[Path] = []
    if scenes_path.exists():
        try:
            scenes_data = json.loads(scenes_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            scenes_data = None

        items = None
        if isinstance(scenes_data, list):
            items = scenes_data
        elif isinstance(scenes_data, dict):
            for key in ("scenes", "clips", "items"):
                if isinstance(scenes_data.get(key), list):
                    items = scenes_data[key]
                    break

        if items:
            for item in items:
                if isinstance(item, str):
                    clip_paths.append(clips_dir / item)
                elif isinstance(item, dict):
                    for key in ("file", "path", "clip", "src"):
                        if key in item:
                            clip_paths.append(clips_dir / str(item[key]))
                            break

    if not clip_paths:
        scene_dirs = sorted([p for p in clips_dir.glob("scene_*") if p.is_dir()])
        for scene_dir in scene_dirs:
            for ext in ("*.mp4", "*.mov", "*.mkv"):
                matches = sorted(scene_dir.glob(ext))
                if matches:
                    clip_paths.append(matches[0])
                    break

    if not clip_paths:
        for ext in ("*.mp4", "*.mov", "*.mkv", "*.m4v"):
            clip_paths.extend(sorted(clips_dir.glob(ext)))

    if not clip_paths:
        for ext in ("*.mp4", "*.mov", "*.mkv"):
            clip_paths.extend(sorted(clips_dir.rglob(ext)))

    return [p for p in clip_paths if p.exists()]


def build_montage(clips: list[Path], montage_path: Path):
    if not clips:
        return None

    durations = [ffprobe_video_duration(clip) for clip in clips]
    filter_parts = []
    for idx in range(len(clips)):
        filter_parts.append(
            f"[{idx}:v]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=cover,"
            f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},fps={VIDEO_FPS},format=yuv420p[v{idx}]"
        )

    if len(clips) == 1:
        output_label = "[v0]"
    else:
        offset = max(durations[0] - XFADE_DURATION, 0.01)
        filter_parts.append(
            f"[v0][v1]xfade=transition=fade:duration={XFADE_DURATION}:offset={offset}[v1x]"
        )
        for idx in range(2, len(clips)):
            offset += max(durations[idx - 1] - XFADE_DURATION, 0.01)
            filter_parts.append(
                f"[v{idx - 1}x][v{idx}]xfade=transition=fade:duration={XFADE_DURATION}:offset={offset}[v{idx}x]"
            )
        output_label = f"[v{len(clips) - 1}x]"

    filter_complex = ";".join(filter_parts)

    cmd = ["ffmpeg", "-y"]
    for clip in clips:
        cmd += ["-i", str(clip)]
    cmd += [
        "-filter_complex", filter_complex,
        "-map", output_label,
        "-r", str(VIDEO_FPS),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-an",
        str(montage_path)
    ]

    run(cmd)
    return montage_path


def main():
    if len(sys.argv) < 3:
        print("Usage: python render_shorts.py <audio_path> '<text|text_file>' [out_mp4] [clips_dir] [music_path]")
        sys.exit(1)

    audio_path = Path(sys.argv[1]).resolve()
    text = read_text_arg(sys.argv[2])
    out_mp4 = Path(sys.argv[3]).resolve() if len(sys.argv) >= 4 else audio_path.parent / "shorts.mp4"
    clips_dir = Path(sys.argv[4]).resolve() if len(sys.argv) >= 5 else None
    music_path = Path(sys.argv[5]).resolve() if len(sys.argv) >= 6 else None
    if music_path and not music_path.exists():
        print(f"Warning: music file not found at {music_path}, continuing without music.")
        music_path = None

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

    montage_path = None
    if clips_dir and clips_dir.exists():
        scenes_path = clips_dir / "scenes.json"
        clips = _pick_scene_clips(clips_dir)
        print(f"DEBUG scenes.json exists: {scenes_path.exists()}")
        print(f"DEBUG picked clips count: {len(clips)}; first 3: {[p.name for p in clips[:3]]}")
        if clips:
            montage_path = out_mp4.with_name(f"{out_mp4.stem}_montage.mp4")
            build_montage(clips, montage_path)

    if montage_path:
        video_filter = build_video_filter(srt_ff, style, include_scale=False)
        cmd = [
            "ffmpeg", "-y",
            "-i", str(montage_path),
            "-i", str(audio_path),
            "-t", f"{dur:.3f}",
            "-vf", video_filter,
        ]
        if music_path:
            cmd += ["-stream_loop", "-1", "-i", str(music_path)]
            cmd += [
                "-filter_complex", build_audio_filter_complex(1, 2),
                "-map", "0:v",
                "-map", "[aout]",
            ]
        else:
            cmd += ["-af", AF_LOUDNORM]

        cmd += [
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-shortest",
            "-movflags", "+faststart",
            str(out_mp4)
        ]
        run(cmd)
    else:
        video_filter = build_video_filter(srt_ff, style, include_scale=True)
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", bg,
            "-i", str(audio_path),
            "-t", f"{dur:.3f}",
            "-vf", video_filter,
        ]
        if music_path:
            cmd += ["-stream_loop", "-1", "-i", str(music_path)]
            cmd += [
                "-filter_complex", build_audio_filter_complex(1, 2),
                "-map", "0:v",
                "-map", "[aout]",
            ]
        else:
            cmd += ["-af", AF_LOUDNORM]

        cmd += [
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "20",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-shortest",
            "-movflags", "+faststart",
            str(out_mp4)
        ]

        run(cmd)

    print(json.dumps({
        "audio": str(audio_path),
        "video": str(out_mp4),
        "montage": str(montage_path) if montage_path else None,
        "srt": str(srt_path),
        "duration": dur,
        "background_theme": bg_config.get("theme", "default"),
        "background_colors": bg_config.get("colors", {})
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
