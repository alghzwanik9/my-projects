import { useState, useEffect, useCallback } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "";

// ── Progress Steps ─────────────────────────────────────────
const STEPS = [
  { threshold: 0,  label: "🚀 بدء المعالجة..." },
  { threshold: 15, label: "🎙️ توليد الصوت..." },
  { threshold: 40, label: "🧠 تخطيط المشاهد بـ Gemini..." },
  { threshold: 60, label: "🎞️ تحميل كليبات Pexels..." },
  { threshold: 80, label: "🎬 تركيب الفيديو بـ FFmpeg..." },
  { threshold: 95, label: "✨ اللمسات الأخيرة..." },
];

function getStepLabel(progress) {
  let label = STEPS[0].label;
  for (const step of STEPS) {
    if (progress >= step.threshold) label = step.label;
  }
  return label;
}

// ── Format seconds ─────────────────────────────────────────
function fmtDuration(sec) {
  if (!sec) return "";
  return sec < 60 ? `${Math.round(sec)}s` : `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`;
}

function fmtDate(timestamp) {
  if (!timestamp) return "";
  return new Date(timestamp * 1000).toLocaleString("ar-SA", {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

export default function App() {
  const [tab, setTab] = useState("create"); // "create" | "history"
  const [text, setText] = useState("");
  const [topic, setTopic] = useState("");
  const [language, setLanguage] = useState("ar");
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [history, setHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  // ── Progress animation ─────────────────────────────────
  useEffect(() => {
    if (!loading) { setProgress(0); return; }
    setProgress(5);
    const steps = [15, 40, 55, 68, 80, 90, 95];
    const intervals = [3000, 6000, 10000, 16000, 22000, 28000, 34000];
    const timers = steps.map((p, i) => setTimeout(() => setProgress(p), intervals[i]));
    return () => timers.forEach(clearTimeout);
  }, [loading]);

  // ── Load history ───────────────────────────────────────
  const loadHistory = useCallback(async () => {
    setHistoryLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/videos?limit=50`);
      if (res.ok) {
        const data = await res.json();
        setHistory(data.videos || []);
      }
    } catch (e) {
      console.error("Failed to load history:", e);
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    if (tab === "history") loadHistory();
  }, [tab, loadHistory]);

  // ── Delete video ───────────────────────────────────────
  const deleteVideo = async (runId) => {
    try {
      const res = await fetch(`${API_BASE}/api/videos/${runId}`, { method: "DELETE" });
      if (res.ok) {
        setHistory((prev) => prev.filter((v) => v.run_id !== runId));
        if (result?.run_id === runId) setResult(null);
      }
    } catch (e) {
      console.error("Delete failed:", e);
    } finally {
      setDeleteConfirm(null);
    }
  };

  // ── Demo text ──────────────────────────────────────────
  const loadDemo = () => {
    setText(
      `هل تعلم أن الذكاء الاصطناعي لا يفهم مثل الإنسان؟\nلكنه يتعلّم من البيانات ويكتشف الأنماط.\nلهذا تراه في التوصيات والترجمة والبحث.\nتابع AI Explained | بالعربي للمزيد.`
    );
    setTopic("");
  };

  // ── Submit ─────────────────────────────────────────────
  const handleSubmit = async (e) => {
    e.preventDefault();
    const trimmedText = text.trim();
    const trimmedTopic = topic.trim();

    if (!trimmedText && !trimmedTopic) return setError("اكتب نصاً أو عنواناً أولاً");
    if (trimmedText && trimmedText.length < 10) return setError("النص قصير جداً (10 أحرف على الأقل)");
    if (trimmedText && trimmedText.length > 5000) return setError("النص طويل جداً (الحد الأقصى 5000 حرف)");

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const res = await fetch(`${API_BASE}/api/generate-video`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: trimmedText,
          topic: trimmedTopic,
          language,
          images_count: 0,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data?.detail || "فشل الطلب");
      setProgress(100);
      setTimeout(() => {
        setResult(data);
        setTab("create");
      }, 400);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const charCount = text.length;
  const charColor =
    charCount > 4500 ? "#ff6b6b" : charCount > 3000 ? "#fbbf24" : "rgba(255,255,255,0.4)";

  return (
    <div className="page">
      {/* ── Header ── */}
      <header className="hero">
        <div className="hero-icon">🎬</div>
        <h1>AI Shorts Generator</h1>
        <p className="hero-sub">
          أنشئ فيديو قصير احترافي من نص بالعربي — صوت + ترجمة + كليبات تلقائية
        </p>
      </header>

      {/* ── Tabs ── */}
      <div className="tabs">
        <button
          className={`tab-btn ${tab === "create" ? "active" : ""}`}
          onClick={() => setTab("create")}
          id="tab-create"
        >
          ✨ إنشاء فيديو
        </button>
        <button
          className={`tab-btn ${tab === "history" ? "active" : ""}`}
          onClick={() => setTab("history")}
          id="tab-history"
        >
          📁 فيديوهاتي
          {history.length > 0 && <span className="tab-badge">{history.length}</span>}
        </button>
      </div>

      {/* ── Create Tab ── */}
      {tab === "create" && (
        <>
          <form className="card" onSubmit={handleSubmit} id="video-form">
            {/* Topic input */}
            <label className="field-label">
              العنوان / الموضوع <span className="optional-tag">(اختياري)</span>
            </label>
            <input
              type="text"
              className="topic-input"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="مثال: 5 حقائق عن الذكاء الاصطناعي"
              disabled={loading}
              id="input-topic"
            />
            <p className="field-hint">
              إذا أضفت موضوعاً وتركت النص فارغاً، سيكتب Gemini النص تلقائياً
            </p>

            {/* Main text area */}
            <label className="field-label" style={{ marginTop: "20px" }}>
              نص الفيديو <span className="optional-tag">(اختياري إذا وُجد الموضوع)</span>
            </label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="اكتب محتوى فيديوك هنا... أو اترك فارغاً وأضف موضوعاً"
              rows={7}
              disabled={loading}
              id="input-text"
            />
            <div className="char-count" style={{ color: charColor }}>
              {charCount.toLocaleString()} / 5,000
            </div>

            {/* Language selector */}
            <div className="lang-row">
              <label className="field-label" style={{ marginBottom: 0 }}>
                🌐 لغة الصوت:
              </label>
              <div className="lang-options">
                <label className={`lang-option ${language === "ar" ? "selected" : ""}`}>
                  <input
                    type="radio"
                    name="language"
                    value="ar"
                    checked={language === "ar"}
                    onChange={() => setLanguage("ar")}
                    disabled={loading}
                  />
                  🇸🇦 عربي
                </label>
                <label className={`lang-option ${language === "en" ? "selected" : ""}`}>
                  <input
                    type="radio"
                    name="language"
                    value="en"
                    checked={language === "en"}
                    onChange={() => setLanguage("en")}
                    disabled={loading}
                  />
                  🇺🇸 English
                </label>
              </div>
            </div>

            {/* Buttons */}
            <div className="btn-row">
              <button type="submit" disabled={loading} className="btn-primary" id="btn-generate">
                {loading ? "⏳ جاري الإنشاء..." : "🚀 إنشاء الفيديو"}
              </button>
              <button
                type="button"
                onClick={loadDemo}
                disabled={loading}
                className="btn-ghost"
                id="btn-demo"
              >
                📝 نص تجريبي
              </button>
            </div>

            {/* Progress */}
            {loading && (
              <div className="progress-wrap" id="progress-bar-wrap">
                <div className="progress-bar" style={{ width: `${progress}%` }} />
                <span className="progress-label">{getStepLabel(progress)}</span>
              </div>
            )}

            {error && <p className="error" id="error-msg">❌ {error}</p>}
          </form>

          {/* Result */}
          {result && (
            <section className="card result-card" id="result-section">
              <div className="result-header">
                <h2>✅ تم إنشاء الفيديو!</h2>
                <div className="result-meta">
                  {result.audio_duration && (
                    <span className="meta-badge">⏱️ {fmtDuration(result.audio_duration)}</span>
                  )}
                  {result.size_mb && (
                    <span className="meta-badge">💾 {result.size_mb} MB</span>
                  )}
                  {result.scenes_count && (
                    <span className="meta-badge">🎞️ {result.scenes_count} مشاهد</span>
                  )}
                </div>
              </div>

              <video
                controls
                autoPlay
                src={`${API_BASE}${result.video_url}?t=${Date.now()}`}
                id="result-video"
              />

              <div className="result-actions">
                <a
                  className="btn-download"
                  href={`${API_BASE}${result.video_url}`}
                  download
                  id="btn-download"
                >
                  ⬇️ تحميل الفيديو
                </a>
                <button
                  className="btn-ghost btn-sm"
                  onClick={() => {
                    setResult(null);
                    setText("");
                    setTopic("");
                  }}
                  id="btn-new"
                >
                  ✨ إنشاء جديد
                </button>
                {result.run_id && (
                  <span className="run-id">ID: {result.run_id.slice(0, 8)}</span>
                )}
              </div>
            </section>
          )}
        </>
      )}

      {/* ── History Tab ── */}
      {tab === "history" && (
        <section className="card" id="history-section">
          <div className="history-header">
            <h2 className="history-title">📁 فيديوهاتي السابقة</h2>
            <button className="btn-ghost btn-sm" onClick={loadHistory} disabled={historyLoading}>
              {historyLoading ? "⏳" : "🔄 تحديث"}
            </button>
          </div>

          {historyLoading && (
            <div className="history-loading">
              <span className="spinner" />
              جاري التحميل...
            </div>
          )}

          {!historyLoading && history.length === 0 && (
            <div className="history-empty">
              <span>🎬</span>
              <p>لا توجد فيديوهات بعد. أنشئ أول فيديو لك!</p>
              <button className="btn-primary" onClick={() => setTab("create")}>
                ✨ إنشاء فيديو
              </button>
            </div>
          )}

          <div className="history-grid">
            {history.map((video) => (
              <div key={video.run_id} className="history-card">
                <video
                  src={`${API_BASE}${video.video_url}`}
                  className="history-thumb"
                  muted
                  onMouseEnter={(e) => e.target.play()}
                  onMouseLeave={(e) => { e.target.pause(); e.target.currentTime = 0; }}
                />
                <div className="history-info">
                  {video.text_preview && (
                    <p className="history-text">{video.text_preview}</p>
                  )}
                  <div className="history-meta">
                    <span>💾 {video.size_mb} MB</span>
                    {video.created_at && <span>📅 {fmtDate(video.created_at)}</span>}
                  </div>
                  <div className="history-actions">
                    <a
                      className="btn-download btn-sm"
                      href={`${API_BASE}${video.video_url}`}
                      download
                    >
                      ⬇️ تحميل
                    </a>
                    <button
                      className="btn-ghost btn-sm"
                      onClick={() => {
                        setResult(video);
                        setTab("create");
                      }}
                    >
                      ▶️ مشاهدة
                    </button>
                    {deleteConfirm === video.run_id ? (
                      <>
                        <button
                          className="btn-danger btn-sm"
                          onClick={() => deleteVideo(video.run_id)}
                        >
                          تأكيد الحذف
                        </button>
                        <button
                          className="btn-ghost btn-sm"
                          onClick={() => setDeleteConfirm(null)}
                        >
                          إلغاء
                        </button>
                      </>
                    ) : (
                      <button
                        className="btn-ghost btn-sm icon-btn"
                        onClick={() => setDeleteConfirm(video.run_id)}
                        title="حذف"
                      >
                        🗑️
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Footer ── */}
      <footer className="footer">
        <span>⚡ Powered by Gemini AI · ElevenLabs · Pexels · FFmpeg</span>
      </footer>
    </div>
  );
}
