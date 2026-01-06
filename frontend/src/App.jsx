import { useState } from "react";

const defaultForm = {
  prompt: "",
  duration: 30,
  language: "en",
  tone: "friendly",
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

    try {
      const response = await fetch("http://localhost:8000/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: form.prompt,
          duration: Number(form.duration),
          language: form.language,
          tone: form.tone,
        }),
      });

      if (!response.ok) {
        const details = await response.json();
        throw new Error(details.detail || "Failed to generate.");
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page">
      <header>
        <h1>Short Video MVP</h1>
        <p>Generate a script, scenes, and captions from a simple prompt.</p>
      </header>

      <form className="card" onSubmit={handleSubmit}>
        <label>
          Prompt
          <textarea
            value={form.prompt}
            onChange={updateField("prompt")}
            placeholder="e.g., 5 tips for better focus"
            required
          />
        </label>

        <div className="grid">
          <label>
            Duration (seconds)
            <input
              type="number"
              min="15"
              max="60"
              value={form.duration}
              onChange={updateField("duration")}
              required
            />
          </label>

          <label>
            Language
            <select value={form.language} onChange={updateField("language")}>
              <option value="en">English</option>
              <option value="ar">Arabic</option>
            </select>
          </label>

          <label>
            Tone
            <input
              type="text"
              value={form.tone}
              onChange={updateField("tone")}
              placeholder="friendly, bold, calm"
              required
            />
          </label>
        </div>

        <button type="submit" disabled={loading}>
          {loading ? "Generating..." : "Generate"}
        </button>

        {error && <p className="error">{error}</p>}
      </form>

      {result && (
        <section className="results">
          <div className="card">
            <h2>Script</h2>
            <pre>{result.script}</pre>
            <a className="download" href={`http://localhost:8000/${result.srt_path}`}>
              Download SRT
            </a>
          </div>

          <div className="card">
            <h2>Scenes</h2>
            <table>
              <thead>
                <tr>
                  <th>Start</th>
                  <th>End</th>
                  <th>Narration</th>
                  <th>On-screen text</th>
                  <th>Visual hint</th>
                </tr>
              </thead>
              <tbody>
                {result.scenes.map((scene, index) => (
                  <tr key={`${scene.start}-${index}`}>
                    <td>{scene.start}s</td>
                    <td>{scene.end}s</td>
                    <td>{scene.narration}</td>
                    <td>{scene.on_screen_text}</td>
                    <td>{scene.visual_hint}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
