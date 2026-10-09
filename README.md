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

The SQLite database lives in the `app_data` Docker volume and survives rebuilds
(backup: `docker compose cp app:/app/data ./backup`).

**Without building on the server:** set `SARENAKH_IMAGE=ghcr.io/<owner>/sarenakh:latest` in the server's `.env`,
then `docker compose pull app && docker compose up -d`. (A small 1 GB VPS is then enough — no Node build there.)

## Container image (GitHub Container Registry)

Every push to `main` runs `.github/workflows/ci.yml`:

| job | what it does |
|---|---|
| `test` | backend pytest, frontend typecheck + build |
| `chart` | `helm lint --strict`, renders the chart (defaults / ingress+TLS / existing secret), checks the single-replica guard, validates with kubeconform |
| `image` | builds the Dockerfile and pushes `ghcr.io/<owner>/sarenakh:{latest, <appVersion>, sha-<commit>}` (and `<x.y.z>` for `v*` tags) using the built-in `GITHUB_TOKEN` |
| `chart-publish` | packages the Helm chart and pushes it to `oci://ghcr.io/<owner>/charts/sarenakh` |

The image runs as non-root (uid 10001); `/app/data` is the only writable path. New GHCR packages are private:
make `sarenakh` public in the package settings, or use an image pull secret.

## Kubernetes (Helm)

The chart is in [`deploy/helm/sarenakh`](deploy/helm/sarenakh). Sarenakh deliberately runs as **one pod**
(SQLite + in-process agent runs + SSE live feed); the chart enforces `replicaCount: 1`, uses the `Recreate`
strategy and a `ReadWriteOnce` PVC that is kept on uninstall. The cluster must be outside Iran (OpenAI).

```bash
kubectl create namespace sarenakh
kubectl -n sarenakh create secret generic sarenakh-secrets \
  --from-literal=OPENAI_API_KEY=sk-... --from-literal=SESSION_SECRET="$(openssl rand -base64 48)"

helm install sarenakh oci://ghcr.io/<owner>/charts/sarenakh -n sarenakh \
  --set secret.existingSecret=sarenakh-secrets \
  --set ingress.enabled=true \
  --set ingress.hosts[0].host=sarenakh.example.com --set ingress.hosts[0].paths[0].path=/ \
  --set ingress.hosts[0].paths[0].pathType=Prefix \
  --set ingress.tls[0].secretName=sarenakh-tls --set ingress.tls[0].hosts[0]=sarenakh.example.com

helm test sarenakh -n sarenakh        # GET /health from inside the cluster
```

Useful values: `image.tag` (default = chart `appVersion`), `config.*` (models, budgets, `MODEL_CHECK`, spend caps),
`persistence.size/storageClass`, `ingress.annotations` (SSE-friendly nginx defaults included), `imagePullSecrets`
for a private package, `extraEnv` (e.g. `HTTPS_PROXY`). Pod security: non-root, read-only root filesystem,
all capabilities dropped, no service-account token. Without ingress:
`kubectl -n sarenakh port-forward svc/sarenakh 8080:80`.
