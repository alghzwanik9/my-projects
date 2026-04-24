"""
أداة تنظيف الملفات القديمة
يمكن تشغيلها يدوياً: python backend/tools/cleanup.py [days]
أو عبر API: POST /api/cleanup?max_age_days=7
"""
from __future__ import annotations

import logging
import shutil
import sys
import time
from pathlib import Path

# backend/
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.config import OUTPUTS_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def cleanup_old_outputs(max_age_days: int = 7) -> dict:
    """حذف مجلدات outputs الأقدم من max_age_days أيام"""
    deleted = 0
    errors = []
    cutoff = time.time() - (max_age_days * 86400)
    output_dir = Path(OUTPUTS_DIR)

    if not output_dir.exists():
        logger.warning(f"Outputs directory not found: {output_dir}")
        return {"deleted": 0, "errors": []}

    for run_dir in output_dir.iterdir():
        if not run_dir.is_dir():
            continue
        try:
            mtime = run_dir.stat().st_mtime
            if mtime < cutoff:
                shutil.rmtree(run_dir)
                deleted += 1
                logger.info(f"🗑️  Deleted old run: {run_dir.name}")
        except Exception as e:
            errors.append(str(e))
            logger.warning(f"⚠️  Could not delete {run_dir}: {e}")

    return {"deleted": deleted, "errors": errors}


def main():
    max_age_days = 7

    if len(sys.argv) > 1:
        try:
            max_age_days = int(sys.argv[1])
        except ValueError:
            logger.error(f"Invalid number of days: {sys.argv[1]}")
            sys.exit(1)

    logger.info(f"Starting cleanup for files older than {max_age_days} days...")
    result = cleanup_old_outputs(max_age_days)

    logger.info(f"Cleanup completed:")
    logger.info(f"  - Deleted directories: {result['deleted']}")
    if result["errors"]:
        logger.warning(f"  - Errors: {len(result['errors'])}")
        for error in result["errors"]:
            logger.error(f"    {error}")

    sys.exit(0 if not result["errors"] else 1)


if __name__ == "__main__":
    main()
