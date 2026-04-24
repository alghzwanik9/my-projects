# المسار: backend/tools/render_shorts.py
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# --- FIX PATH IMPORT ERROR ---
# نقوم بإضافة المجلد الرئيسي (backend) إلى مسارات النظام
# لكي نستطيع استيراد app.services بشكل صحيح
CURRENT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = CURRENT_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# الآن يمكننا عمل Import بأمان
try:
    from app.services.background_service import get_background_config, generate_ffmpeg_background
except ImportError:
    # Fallback
    def get_background_config(text: str): return {"colors": {"primary": "#0b0f19"}}
    def generate_ffmpeg_background(config, width=1080, height=1920): return f"color=c=#0b0f19:s={width}x{height}:r=30"

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30 
AF_LOUDNORM = "loudnorm=I=-16:TP=-1.5:LRA=11"
VF_ENHANCED = "eq=contrast=1.05:saturation=1.2,unsharp=5:5:1.0:3:3:0.0"

def run(cmd: list[str]):
    # استخدام encoding='utf-8' لتجنب مشاكل الطباعة
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
    if p.returncode != 0:
        print(f"❌ FFmpeg Error:\n{p.stderr[-1000:]}")
        raise RuntimeError(f"Command failed")
    return p.stdout.strip()

def get_duration(file_path: Path) -> float:
    try:
        out = run([
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(file_path)
        ])
        return float(out)
    except:
        return 0.0

def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def chunk_text(text: str, max_chars: int = 25) -> list[str]:
    """تقسيم النص ليكون مناسباً لليوتيوب شورتس (كلمات قليلة في كل سطر)"""
    words = text.split()
    lines = []
    current_line = []
    current_len = 0
    for word in words:
        if current_len + len(word) + 1 > max_chars:
            lines.append(" ".join(current_line))
            current_line = [word]
            current_len = len(word)
        else:
            current_line.append(word)
            current_len += len(word) + 1
    if current_line: lines.append(" ".join(current_line))
    return lines

def write_srt(text: str, total_dur: float, out_srt: Path):
    chunks = chunk_text(text)
    if not chunks: return
    chunk_dur = total_dur / len(chunks)
    with open(out_srt, "w", encoding="utf-8") as f:
        for i, line in enumerate(chunks):
            start = i * chunk_dur
            end = (i + 1) * chunk_dur - 0.1
            if end < start: end = start + 0.05
            f.write(f"{i+1}\n{srt_time(start)} --> {srt_time(end)}\n{line}\n\n")

def ffmpeg_escape(p: str) -> str:
    return p.replace("\\", "/").replace(":", r"\:")

def pick_scene_clips(clips_dir: Path) -> list[Path]:
    all_clips = []
    if not clips_dir or not clips_dir.exists(): return []
    
    scene_folders = sorted(clips_dir.glob("scene_*"))
    for folder in scene_folders:
        videos = sorted(list(folder.glob("*.mp4")) + list(folder.glob("*.mov")))
        if videos: all_clips.append(videos[0])
    
    if not all_clips:
        all_clips = sorted(list(clips_dir.glob("*.mp4")) + list(clips_dir.glob("*.mov")))
    return all_clips

def build_montage(clips: list[Path], montage_path: Path, target_duration: float):
    if not clips: return False
    num_clips = len(clips)
    clip_time = target_duration / num_clips
    
    inputs = []
    filter_complex = []
    
    for i, clip in enumerate(clips):
        inputs.extend(["-i", str(clip)])
        filter_complex.append(
            f"[{i}:v]scale=w='max(iw*1920/ih,1080)':h='max(1920,ih*1080/iw)':force_original_aspect_ratio=increase,"
            f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},"
            f"setsar=1,"
            f"loop=loop=-1:size=32767:start=0,"
            f"trim=duration={clip_time:.3f},setpts=PTS-STARTPTS[v{i}]"
        )
        
    concat_inputs = "".join([f"[v{i}]" for i in range(num_clips)])
    filter_complex.append(f"{concat_inputs}concat=n={num_clips}:v=1:a=0[outv]")
    
    cmd = ["ffmpeg", "-y"]
    cmd.extend(inputs)
    cmd.extend(["-filter_complex", ";".join(filter_complex)])
    cmd.extend(["-map", "[outv]"])
    cmd.extend(["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", str(montage_path)])
    
    print(f"🎬 Building High-Quality Montage...")
    run(cmd)
    return True

def main():
    # 🔥 FIX ENCODING ERROR ON WINDOWS 🔥
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8')

    if len(sys.argv) < 3:
        print("Usage error")
        sys.exit(1)

    audio_path = Path(sys.argv[1]).resolve()
    text_path_arg = Path(sys.argv[2])
    text = text_path_arg.read_text(encoding="utf-8").strip() if text_path_arg.exists() else sys.argv[2]
    out_mp4 = Path(sys.argv[3]).resolve()
    clips_dir = Path(sys.argv[4]).resolve() if len(sys.argv) > 4 else None
    music_path = Path(sys.argv[5]).resolve() if len(sys.argv) > 5 else None

    # 1. المدة والترجمة
    audio_dur = get_duration(audio_path)
    srt_path = audio_path.parent / "captions.srt"
    write_srt(text, audio_dur, srt_path)
    srt_ff = ffmpeg_escape(str(srt_path))

    # 2. بناء المونتاج
    montage_path = audio_path.parent / "montage_temp.mp4"
    clips = pick_scene_clips(clips_dir) if clips_dir else []
    has_video = False
    if clips:
        try:
            has_video = build_montage(clips, montage_path, audio_dur)
        except Exception as e:
            print(f"⚠️ Montage Error: {e}")

    # الترجمة: تصميم احترافي (صغير، في الأسفل، مع ظل خفيف)
    style = (
        "FontName=Cairo,Fontsize=22,"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BackColour=&H00000000,"
        "BorderStyle=1,Outline=1,Shadow=1,"
        "Alignment=2,MarginV=60,Bold=1"
    )
    subtitles_filter = f"subtitles='{srt_ff}':force_style='{style}'"
    
    final_inputs = []
    filter_chain = []
    
    if has_video and montage_path.exists():
        final_inputs.extend(["-i", str(montage_path)])
        filter_chain.append(
            f"[0:v]{VF_ENHANCED},{subtitles_filter}[vfinal]"
        )
    else:
        # خلفية داكنة نظيفة كـ fallback
        final_inputs.extend([
            "-f", "lavfi",
            "-i", f"color=c=#0d1b2a:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:r=30:d={audio_dur}"
        ])
        filter_chain.append(
            f"[0:v]{subtitles_filter}[vfinal]"
        )

    final_inputs.extend(["-i", str(audio_path)])
    
    if music_path and music_path.exists():
        final_inputs.extend(["-stream_loop", "-1", "-i", str(music_path)])
        audio_filter = (
            f"[2:a]volume=0.15[music];"
            f"[1:a]volume=1.0[voice];"
            f"[music][voice]amix=inputs=2:duration=first:dropout_transition=2,{AF_LOUDNORM}[afinal]"
        )
    else:
        audio_filter = f"[1:a]{AF_LOUDNORM}[afinal]"
    
    filter_chain.append(audio_filter)

    cmd = ["ffmpeg", "-y"]
    cmd.extend(final_inputs)
    cmd.extend(["-filter_complex", ";".join(filter_chain)])
    cmd.extend(["-map", "[vfinal]", "-map", "[afinal]"])
    cmd.extend([
        "-c:v", "libx264", "-profile:v", "high", "-preset", "slower", "-crf", "15",
        "-c:a", "aac", "-b:a", "256k",
        "-movflags", "+faststart", "-pix_fmt", "yuv420p", str(out_mp4)
    ])

    print("🚀 Rendering High-Quality Final Video...")
    run(cmd)

    if montage_path.exists():
        try: montage_path.unlink() 
        except: pass

    print(json.dumps({"status": "success", "video": str(out_mp4)}))

if __name__ == "__main__":
    main()