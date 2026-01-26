import os
import random
import requests
from pathlib import Path

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "").strip()

FALLBACK_TERMS = [
    "motivation",
    "nature",
    "abstract",
    "technology",
    "city",
    "ocean",
    "space",
    "business",
]

def _pick_best_file(video_files: list[dict]) -> str | None:
    mp4s = [vf for vf in video_files if str(vf.get("file_type", "")).lower() == "video/mp4"]
    if not mp4s:
        return None
    # الأفضل غالبًا أعلى دقة (width*height)
    mp4s.sort(key=lambda x: (x.get("width", 0) * x.get("height", 0)), reverse=True)
    return mp4s[0].get("link")

def _normalize_terms(search_terms: list[str]) -> list[str]:
    cleaned: list[str] = []
    for t in (search_terms or []):
        t = (t or "").strip()
        if t and t not in cleaned:
            cleaned.append(t)

    # أضف fallback
    for t in FALLBACK_TERMS:
        if t not in cleaned:
            cleaned.append(t)

    return cleaned

def download_stock_clips(search_terms: list[str], out_dir: Path, max_clips: int = 1) -> list[Path]:
    """
    ينزّل مقاطع MP4 من Pexels حسب search_terms + fallback.
    يحفظها داخل out_dir ويرجع مساراتها.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not PEXELS_API_KEY:
        return []

    headers = {"Authorization": PEXELS_API_KEY}
    url = "https://api.pexels.com/videos/search"

    clips: list[Path] = []
    terms = _normalize_terms(search_terms)

    i = 0
    for term in terms:
        if len(clips) >= max_clips:
            break

        params = {"query": term, "per_page": 12, "orientation": "portrait"}
        try:
            r = requests.get(url, headers=headers, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
        except Exception:
            continue

        videos = data.get("videos", []) or []
        if not videos:
            continue

        v = random.choice(videos[: min(8, len(videos))])
        link = _pick_best_file(v.get("video_files", []) or [])
        if not link:
            continue

        mp4_path = out_dir / f"clip_{i:02d}.mp4"
        i += 1

        try:
            with requests.get(link, stream=True, timeout=60) as rr:
                rr.raise_for_status()
                with open(mp4_path, "wb") as f:
                    for chunk in rr.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            f.write(chunk)
        except Exception:
            if mp4_path.exists():
                try:
                    mp4_path.unlink()
                except Exception:
                    pass
            continue

        # تأكد الملف مو فاضي
        if mp4_path.exists() and mp4_path.stat().st_size > 50_000:
            clips.append(mp4_path)

    return clips
