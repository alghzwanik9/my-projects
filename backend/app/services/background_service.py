"""
خدمة اختيار الخلفيات المناسبة بناءً على محتوى النص
"""
from __future__ import annotations

import logging
import re
from typing import Dict, Tuple

logger = logging.getLogger(__name__)

# كلمات مفتاحية للخلفيات المختلفة
BACKGROUND_THEMES: Dict[str, Dict[str, any]] = {
    "tech": {
        "keywords": ["ذكاء", "اصطناعي", "تقنية", "تكنولوجيا", "برمجة", "كمبيوتر", "إنترنت", "رقمي"],
        "colors": {"primary": "#1a1a2e", "secondary": "#16213e", "accent": "#0f3460"},
        "gradient": "linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)"
    },
    "business": {
        "keywords": ["عمل", "تجارة", "استثمار", "مال", "اقتصاد", "شركة", "نجاح", "ربح"],
        "colors": {"primary": "#0f2027", "secondary": "#203a43", "accent": "#2c5364"},
        "gradient": "linear-gradient(135deg, #0f2027 0%, #203a43 50%, #2c5364 100%)"
    },
    "health": {
        "keywords": ["صحة", "رياضة", "لياقة", "طعام", "نظام", "غذائي", "تمرين", "جسم"],
        "colors": {"primary": "#1a2e1a", "secondary": "#2d4a2d", "accent": "#3d6b3d"},
        "gradient": "linear-gradient(135deg, #1a2e1a 0%, #2d4a2d 50%, #3d6b3d 100%)"
    },
    "education": {
        "keywords": ["تعلم", "تعليم", "دراسة", "مدرسة", "جامعة", "معرفة", "علم", "كتاب"],
        "colors": {"primary": "#2c1810", "secondary": "#3d2817", "accent": "#4d341f"},
        "gradient": "linear-gradient(135deg, #2c1810 0%, #3d2817 50%, #4d341f 100%)"
    },
    "motivation": {
        "keywords": ["تحفيز", "نجاح", "هدف", "طموح", "أحلام", "تحدي", "إصرار", "عزيمة"],
        "colors": {"primary": "#1a0f1a", "secondary": "#2d1a2d", "accent": "#3d263d"},
        "gradient": "linear-gradient(135deg, #1a0f1a 0%, #2d1a2d 50%, #3d263d 100%)"
    },
    "default": {
        "keywords": [],
        "colors": {"primary": "#0b0f19", "secondary": "#1a1f2e", "accent": "#2a2f3e"},
        "gradient": "linear-gradient(135deg, #0b0f19 0%, #1a1f2e 50%, #2a2f3e 100%)"
    }
}


def analyze_text(text: str) -> str:
    """
    تحليل النص وتحديد الموضوع المناسب
    
    Args:
        text: النص المراد تحليله
    
    Returns:
        اسم الموضوع (theme) المناسب
    """
    text_lower = text.lower()
    
    # حساب نقاط لكل موضوع
    scores = {}
    for theme, config in BACKGROUND_THEMES.items():
        if theme == "default":
            continue
        score = sum(1 for keyword in config["keywords"] if keyword in text_lower)
        if score > 0:
            scores[theme] = score
    
    # اختيار الموضوع الأعلى نقاطاً
    if scores:
        best_theme = max(scores.items(), key=lambda x: x[1])[0]
        logger.info(f"Text analyzed: theme={best_theme}, score={scores[best_theme]}")
        return best_theme
    
    return "default"


def get_background_config(text: str) -> Dict[str, any]:
    """
    الحصول على إعدادات الخلفية المناسبة للنص
    
    Args:
        text: النص المراد تحليله
    
    Returns:
        قاموس يحتوي على إعدادات الخلفية (colors, gradient, etc.)
    """
    theme = analyze_text(text)
    config = BACKGROUND_THEMES[theme].copy()
    config["theme"] = theme
    return config


def generate_ffmpeg_background(config: Dict[str, any], width: int = 1080, height: int = 1920) -> str:
    """
    إنشاء أمر FFmpeg لخلفية ديناميكية متدرجة مع تأثيرات بصرية
    
    Args:
        config: إعدادات الخلفية
        width: عرض الفيديو
        height: ارتفاع الفيديو
    
    Returns:
        سلسلة أمر FFmpeg للخلفية
    """
    colors = config["colors"]
    primary = colors["primary"].lstrip("#")
    secondary = colors["secondary"].lstrip("#")
    
    # تحويل hex إلى قيم RGB
    p_r = int(primary[0:2], 16)
    p_g = int(primary[2:4], 16)
    p_b = int(primary[4:6], 16)
    
    s_r = int(secondary[0:2], 16)
    s_g = int(secondary[2:4], 16)
    s_b = int(secondary[4:6], 16)
    
    # خلفية متدرجة بسيطة مع حركة خفيفة
    # gradient من primary إلى secondary مع تأثير حركة خفيف
    bg_filter = (
        f"color=c=#{primary}:s={width}x{height}:r=30,"
        f"format=rgba,"
        f"geq="
        f"r='{p_r}+({s_r}-{p_r})*X/W+sin(PI*X/W+T*0.5)*8':"
        f"g='{p_g}+({s_g}-{p_g})*Y/H+sin(PI*Y/H+T*0.5)*8':"
        f"b='{p_b}+({s_b}-{p_b})*(X/W+Y/H)/2+sin(PI*(X/W+Y/H)/2+T*0.5)*8':"
        f"a=255"
    )
    
    return bg_filter
