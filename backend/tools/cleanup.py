"""
أداة تنظيف الملفات القديمة
يمكن تشغيلها يدوياً أو جدولتها (cron/scheduled task)
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# إضافة مسار backend إلى sys.path
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.main import cleanup_old_outputs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def main():
    """تنظيف الملفات الأقدم من 7 أيام (افتراضي)"""
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
    if result['errors']:
        logger.warning(f"  - Errors: {len(result['errors'])}")
        for error in result['errors']:
            logger.error(f"    {error}")
    
    sys.exit(0 if not result['errors'] else 1)


if __name__ == "__main__":
    main()
