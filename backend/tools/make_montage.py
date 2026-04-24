from __future__ import annotations

import subprocess
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]  # .../my-projects/my-projects
BACKEND_DIR = PROJECT_ROOT / "backend"
OUTPUTS_DIR = BACKEND_DIR / "outputs"

W, H, FPS = 1080, 1920, 30


def run(cmd: list[str]) -> None:
    print("\n🟦 Running:\n", " ".join(cmd), "\n")
    p = subprocess.run(cmd, text=True)
    if p.returncode != 0:
        raise SystemExit(f"❌ ffmpeg failed with code {p.returncode}")


def latest_output_folder() -> Path:
    if not OUTPUTS_DIR.exists():
        raise SystemExit(f"❌ outputs not found: {OUTPUTS_DIR}")
    folders = [p for p in OUTPUTS_DIR.iterdir() if p.is_dir()]
    if not folders:
        raise SystemExit("❌ outputs is empty. Generate once from your app first.")
    folders.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return folders[0]


def find_audio(folder: Path) -> Path:
    # common names
    for name in ["voice.mp3", "audio.mp3", "tts.mp3", "voice.wav", "audio.wav"]:
        p = folder / name
        if p.exists():
            return p
    # any mp3/wav
    for p in list(folder.glob("*.mp3")) + list(folder.glob("*.wav")):
        return p
    raise SystemExit("❌ audio not found (voice.mp3 / audio.mp3 / any mp3/wav)")


def find_ass(folder: Path) -> Path:
    p = folder / "captions.ass"
    if p.exists():
        return p
    # any ass
    ass = list(folder.glob("*.ass"))
    if ass:
        return ass[0]
    raise SystemExit("❌ captions.ass not found (or any .ass file)")


def ass_for_ffmpeg(ass_path: Path) -> str:
    # ffmpeg filter wants forward slashes; Windows drive colon inside filter is OK with forward slashes
    return ass_path.resolve().as_posix()


def collect_clips(folder: Path) -> list[Path]:
    # put clips in: <output_folder>/clips/*.mp4  (or directly in folder)
    clips_dir = folder / "clips"
    clips: list[Path] = []
    if clips_dir.exists():
        clips += sorted(clips_dir.glob("*.mp4"))
    clips += sorted([p for p in folder.glob("*.mp4") if p.name not in ["shorts.mp4", "montage.mp4", "shorts_captioned.mp4"]])
    return clips


def make_dynamic_bg(out_video: Path, audio: Path, ass: Path) -> None:
    # Animated background via lavfi gradients + subtle zoom
    ass_f = ass_for_ffmpeg(ass)

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i",
        f"gradients=s={W}x{H}:r={FPS},zoompan=z='min(1.15,1+0.0007*on)':d=999999:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)',format=yuv420p",
        "-i", str(audio),
        "-vf", f"subtitles='{ass_f}':fontsdir='C\\:/Windows/Fonts'",
        "-shortest",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(out_video),
    ]
    run(cmd)


def make_from_single_clip(out_video: Path, audio: Path, ass: Path, clip: Path) -> None:
    ass_f = ass_for_ffmpeg(ass)

    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", str(clip),
        "-i", str(audio),
        "-vf",
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        f"subtitles='{ass_f}':fontsdir='C\\:/Windows/Fonts'",
        "-shortest",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(out_video),
    ]
    run(cmd)


def main() -> None:
    folder = latest_output_folder()
    audio = find_audio(folder)
    ass = find_ass(folder)

    out_video = folder / "montage.mp4"
    clips = collect_clips(folder)

    print("🟩 Output folder:", folder)
    print("🟩 Audio:", audio.name)
    print("🟩 Captions:", ass.name)
    print("🟩 Clips found:", len(clips))

    if clips:
        # easiest “real montage”: loop first clip + captions + audio
        make_from_single_clip(out_video, audio, ass, clips[0])
        print("✅ Created montage from clip:", out_video)
    else:
        make_dynamic_bg(out_video, audio, ass)
        print("✅ Created montage with dynamic background:", out_video)


if __name__ == "__main__":
    main()
