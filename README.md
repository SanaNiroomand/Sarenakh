# سرنخ — Sarenakh

**Find real customers inside Telegram group chats.**

Describe your product, give Sarenakh a group's messages, set a budget. An AI agent reads the conversations
and returns the people who actually need your product — with the messages that prove it, a score,
and a helpful reply you can copy. You see what every step cost.

## Run it on your computer

1. Copy `.env.example` to `.env` and put your OpenAI key in it.
2. Run `.\start.ps1` (Windows). It installs what's needed the first time and opens http://localhost:8000.
3. Sign up, then click **«امتحان سریع با داده نمونه»** to see a full run on sample data.

Needs Python 3.11+ and Node.js.

## Put it online

The server must be **outside Iran** (OpenAI blocks Iranian IPs).

- **One server:** `docker compose up -d` (see `docker-compose.yml`; set `SITE_ADDRESS` in `.env` for HTTPS).
- **Kubernetes:** see [deploy/helm/DEPLOY.md](deploy/helm/DEPLOY.md).

Every push to `main` builds the image `ghcr.io/sananiroomand/sarenakh`.

## Tests

```bash
cd backend && python -m pytest
```
