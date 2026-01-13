import { useState } from "react";

// استخدام proxy في development أو URL مباشر في production
const API_BASE = import.meta.env.DEV ? "" : "http://127.0.0.1:8000";

const defaultForm = {
  text: "",
};

export default function App() {
  const [form, setForm] = useState(defaultForm);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const updateField = (field) => (event) => {
    setForm((prev) => ({ ...prev, [field]: event.target.value }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);

    const text = form.text.trim();
    
    // Validation
    if (!text) {
      setError("اكتب نص أولاً");
      setLoading(false);
      return;
    }
    if (text.length < 10) {
      setError("النص قصير جداً. يجب أن يكون 10 أحرف على الأقل");
      setLoading(false);
      return;
    }
    if (text.length > 2000) {
      setError("النص طويل جداً. الحد الأقصى 2000 حرف");
      setLoading(false);
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/api/generate-video`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });

      if (!response.ok) {
        const details = await response.json();
        throw new Error(details.detail || "فشل الطلب");
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const loadDemoText = () => {
    setForm({
      text: `هل تعلم أن الذكاء الاصطناعي لا يفهم مثل الإنسان؟
لكنه يتعلّم من البيانات ويكتشف الأنماط.
لهذا تراه في التوصيات والترجمة والبحث.
تابع AI Explained | بالعربي للمزيد.`
    });
  };

  return (
    <div className="page">
      <header>
        <h1>🎬 AI Shorts Generator — Arabic</h1>
        <p>✨ صوت ذكوري طبيعي • خلفيات ذكية • جودة عالية ✨</p>
      </header>

      <form className="card" onSubmit={handleSubmit}>
        <label>
          نص الفيديو
          <textarea
            value={form.text}
            onChange={updateField("text")}
            placeholder="اكتب نص الفيديو هنا..."
            required
            rows={6}
          />
        </label>

        <div style={{ display: "flex", gap: "10px", marginTop: "12px", flexWrap: "wrap" }}>
          <button type="submit" disabled={loading} style={{ flex: 1, minWidth: "150px" }}>
            {loading ? "⏳ جاري الإنشاء..." : "🎬 إنشاء الفيديو"}
          </button>
          <button type="button" onClick={loadDemoText} style={{ padding: "12px 16px" }}>
            📝 نص تجريبي
          </button>
        </div>

        {error && <p className="error" style={{ color: "#ff6b6b", marginTop: "12px" }}>❌ {error}</p>}
      </form>

      {result && (
        <section className="results" style={{ marginTop: "24px" }}>
          <div className="card">
            <h2>✅ تم إنشاء الفيديو بنجاح!</h2>
            <video 
              controls 
              style={{ width: "100%", maxHeight: "720px", borderRadius: "12px", marginTop: "16px" }}
              src={`${API_BASE}${result.video_url}?t=${Date.now()}`}
            />
            <div style={{ marginTop: "16px", display: "flex", gap: "10px", flexWrap: "wrap" }}>
              <a 
                className="download" 
                href={`${API_BASE}${result.video_url}`}
                download
                style={{
                  display: "inline-block",
                  color: "#fff",
                  textDecoration: "none",
                  border: "1px solid rgba(255, 255, 255, 0.18)",
                  padding: "10px 14px",
                  borderRadius: "14px"
                }}
              >
                ⬇️ تحميل الفيديو
              </a>
              <div style={{ fontSize: "12px", color: "rgba(255, 255, 255, 0.65)", padding: "10px 14px" }}>
                Run ID: {result.run_id}
              </div>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
