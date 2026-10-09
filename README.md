# سرنخ — Sarenakh

> سرنخ مشتری‌ات را در دل گفتگوها پیدا کن

An agent that reads community chats (Telegram exports), finds people who genuinely need your product,
proves it with evidence, and drafts a help-first reply — while showing exactly what each check cost.

*(Full docs land in phase 9.)*

## Local development

```bash
python -m venv .venv && .venv/Scripts/pip install -r backend/requirements.txt   # Windows
cp .env.example .env    # then put your OPENAI_API_KEY in .env
```

Verify the configured models work with your key (one tool call + one JSON-schema call per model, < $0.001):

```bash
cd backend && ../.venv/Scripts/python -m app.model_check
```

Run backend and frontend (Vite proxies `/api` to :8000):

```bash
.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --reload --port 8000
npm --prefix frontend install && npm --prefix frontend run dev
```

## Deploy (one Docker host outside Iran)

Requirements on the server: Docker with the compose plugin, ports 80/443 open, a domain (or `<ip-with-dashes>.sslip.io`)
pointing at the server.

1. First time: put a production `.env` on the server (`~/sarenakh/.env`) with `SITE_ADDRESS=your.domain`,
   `COOKIE_SECURE=true`, a long random `SESSION_SECRET`, and your `OPENAI_API_KEY`.
2. From your machine: `scripts/deploy.sh user@server` — ships the committed tree via `git archive` (never `.env`),
   then `docker compose up -d --build`. Caddy obtains the TLS certificate automatically.
3. Check: `https://your.domain/health`.

If the server already runs nginx on 80/443, start only the app (`docker compose up -d app`) and proxy to
`127.0.0.1:8000` with `proxy_buffering off;` (needed for the live SSE feed).

The SQLite database lives in `~/sarenakh/data` on the host and survives rebuilds.
