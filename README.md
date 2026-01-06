# Short Video MVP

Minimal MVP for generating short-video scripts, scenes JSON, and SRT captions.

## Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Health check:

```bash
curl http://localhost:8000/api/health
```

Generate script + scenes + SRT:

```bash
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"5 tips for focus","duration":30,"language":"en","tone":"friendly"}'
```

Outputs are saved in `outputs/` at the repo root. The response includes `srt_path`, which can be downloaded from `http://localhost:8000/<srt_path>`.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` to use the UI.
