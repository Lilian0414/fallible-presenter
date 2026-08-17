# Fallible Presenter

Fallible Presenter is an interruptible presentation exercise built from text that
you provide. Most of the report is grounded in that text, while a small number of
server-tracked claims are deliberately changed. The listener decides independently
when to interrupt; only after the presentation does the application reveal caught
errors, missed errors, false challenges, explanations, and evidence.

Unlike conventional erroneous-example exercises, the user is not told where or how
many errors exist. The AI behaves as a continuous presenter. The user independently
decides when to interrupt and challenge the presentation. The system measures both
missed errors and false challenges.

## Architecture and data flow

The FastAPI backend extracts atomic claims, selects 20–30% of eligible claims,
creates one controlled error per selected claim, generates and verifies a 6–12 part
presentation, and keeps the complete answer key in an in-memory session store.
Explicit public DTOs are used before completion. The React/Vite client only stores
public segments and challenge feedback. It requests the result after the last
segment.

`LLMProvider` isolates model calls. Deterministic mock mode is the default and needs
no credentials. The OpenAI-compatible provider requests structured JSON and retries
one malformed response. Verification rejects uncontrolled presentation content.

## Setup

Python 3.12+ and Node 20+ are recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env

cd frontend
npm install
```

Run the API from the repository root:

```bash
uvicorn backend.app.main:app --reload --port 8000
```

Run the UI in a second terminal:

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`. The UI uses `http://localhost:8000` unless
`VITE_API_BASE_URL` is set.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_PROVIDER` | `mock` | Set to `openai` for an OpenAI-compatible endpoint. |
| `LLM_API_KEY` | empty | Bearer token required in real mode. |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | Compatible API base URL. |
| `LLM_MODEL` | `gpt-4o-mini` | Chat-completions model name. |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated browser origins. |
| `VITE_API_BASE_URL` | `http://localhost:8000` | Frontend API origin. |

Mock mode is deliberately deterministic: sentence-like source lines become claims,
a predictable subset is corrupted, and keyword-based challenges are scored without
outside lookup. Real mode sends only the supplied source and constrained prompts to
the configured provider.

## Verification

```bash
pytest backend/tests
cd frontend
npm run typecheck
npm run build
```

## Current limitations

- Sessions disappear when the server restarts and do not work across server replicas.
- Source input is plain text only; there is no PDF ingestion, RAG, or authentication.
- Mock extraction uses sentence boundaries and is intended for development rather
  than nuanced prose.
- Real-provider compatibility currently targets the chat-completions JSON shape.
- Presentation verification is conservative and may reject unusual model wording.
