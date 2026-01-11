from pathlib import Path
import sys

from dotenv import load_dotenv  # ✅ NEW

BASE_DIR = Path(__file__).resolve().parents[2]

# ✅ Load root .env (at repo root)
load_dotenv(BASE_DIR / ".env")

OUTPUTS_DIR = BASE_DIR / "outputs"

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
