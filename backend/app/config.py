from __future__ import annotations

from pathlib import Path
import os

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

# config.py داخل: backend/app/config.py
# parents[0] = app
# parents[1] = backend
# parents[2] = repo root (my-projects)
BASE_DIR = Path(__file__).resolve().parents[1]      # ==> backend/
REPO_DIR = Path(__file__).resolve().parents[2]      # ==> repo root

# Load .env (اختياري)
ENV_PATH = REPO_DIR / ".env"
if load_dotenv and ENV_PATH.exists():
    load_dotenv(ENV_PATH)

# ✅ outputs الرسمي: backend/outputs
OUTPUTS_DIR = (BASE_DIR / "outputs").resolve()
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# (اختياري) مفاتيح
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
