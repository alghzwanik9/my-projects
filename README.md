# AI Shorts Generator — Arabic

تطبيق لإنشاء فيديوهات قصيرة (Shorts) باللغة العربية مع نصوص تلقائية وصوت.

## المميزات

- ✅ إنشاء فيديوهات قصيرة من النص
- ✅ **صوت ذكوري طبيعي** باستخدام Microsoft Edge TTS (صوت طبيعي جداً)
- ✅ **خلفيات ديناميكية** تتوافق مع محتوى النص تلقائياً
- ✅ إضافة ترجمات تلقائية (Subtitles) بتصميم احترافي
- ✅ واجهة عربية مع دعم RTL
- ✅ تحميل الفيديو النهائي
- ✅ جودة فيديو عالية مع تأثيرات بصرية محسّنة

## المتطلبات

- Python 3.8+
- FFmpeg (يجب تثبيته على النظام)
- Node.js (للواجهة الأمامية - اختياري)

## الإعداد

### Backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### الواجهة (Frontend - React)

```bash
cd frontend
npm install
npm run dev
```

افتح المتصفح على: `http://localhost:5173/`

**أو للبناء للإنتاج:**
```bash
cd frontend
npm run build
# ثم الباك إند سيخدم الفرونت إند على http://127.0.0.1:8000/
```

## الاستخدام

### API

Health check:

```bash
curl http://localhost:8000/api/health
```

إنشاء فيديو:

```bash
curl -X POST http://localhost:8000/api/generate-video \
  -H "Content-Type: application/json" \
  -d '{"text":"نص الفيديو هنا..."}'
```

### الواجهة

**في وضع التطوير (Development):**
1. شغّل الفرونت إند: `cd frontend && npm run dev`
2. افتح `http://localhost:5173/`
3. اكتب النص في المربع
4. اضغط "🎬 إنشاء الفيديو"
5. انتظر حتى يتم إنشاء الفيديو
6. حمّل الفيديو النهائي

**في وضع الإنتاج (Production):**
1. ابنِ الفرونت إند: `cd frontend && npm run build`
2. شغّل الباك إند: `cd backend && uvicorn app.main:app --reload --port 8000`
3. افتح `http://127.0.0.1:8000/`

## الملفات المُنتجة

الفيديوهات تُحفظ في: `backend/outputs/<run_id>/shorts.mp4`

## الميزات الإضافية

### تنظيف الملفات القديمة

```bash
# تنظيف الملفات الأقدم من 7 أيام (افتراضي)
python backend/tools/cleanup.py

# تنظيف الملفات الأقدم من 3 أيام
python backend/tools/cleanup.py 3

# أو عبر API
curl -X POST http://localhost:8000/api/cleanup?max_age_days=7
```

## الميزات الجديدة ✨

### صوت ذكوري طبيعي
- استخدام **Microsoft Edge TTS** للحصول على صوت ذكوري طبيعي جداً
- صوت: `ar-SA-HamedNeural` (صوت ذكوري سعودي احترافي)
- Fallback تلقائي إلى gTTS إذا Edge TTS غير متاح

### خلفيات ذكية
النظام يحلل النص تلقائياً ويختار خلفية مناسبة:
- **تقنية**: للكلمات مثل "ذكاء اصطناعي"، "تقنية"، "برمجة"
- **أعمال**: للكلمات مثل "عمل"، "استثمار"، "نجاح"
- **صحة**: للكلمات مثل "صحة"، "رياضة"، "لياقة"
- **تعليم**: للكلمات مثل "تعلم"، "دراسة"، "معرفة"
- **تحفيز**: للكلمات مثل "نجاح"، "هدف"، "طموح"

### تحسينات الجودة
- جودة فيديو عالية (CRF 23)
- تأثيرات بصرية محسّنة
- ترجمات بتصميم احترافي مع ظلال وحدود
- خلفيات متدرجة متحركة

## ملاحظات

- تأكد من تثبيت FFmpeg على النظام
- النصوص الطويلة قد تستغرق وقتاً أطول
- الفيديوهات تُحفظ محلياً في مجلد `backend/outputs/`
- الحد الأدنى للنص: 10 أحرف
- الحد الأقصى للنص: 2000 حرف
- يتم تسجيل جميع العمليات في الـ logs
- **Edge TTS** يحتاج اتصال بالإنترنت (يستخدم خدمات Microsoft)

## هيكل المشروع

```
.
├── backend/
│   ├── app/
│   │   ├── main.py                    # API الرئيسي
│   │   └── services/
│   │       ├── tts_service.py        # خدمة TTS (Edge TTS)
│   │       └── background_service.py # خدمة اختيار الخلفيات
│   ├── tools/
│   │   ├── render_shorts.py         # تصيير الفيديو
│   │   └── cleanup.py               # تنظيف الملفات
│   ├── outputs/                      # الفيديوهات المُنتجة
│   └── requirements.txt
├── frontend/               # واجهة React
│   ├── src/
│   │   ├── App.jsx        # المكون الرئيسي
│   │   └── index.css     # التصميم
│   └── package.json
└── README.md
```
