# Deploying Sarenakh on Kubernetes with Helm

Sarenakh (سرنخ) is a web app (FastAPI + React) that uses the OpenAI API. It runs as **one pod** with a small
SQLite database on a persistent volume. The chart enforces a single replica — that is by design, not a limit
to tune.

**You need**

| | |
|---|---|
| Kubernetes | 1.25+, **located outside Iran** — pods must reach `api.openai.com` (OpenAI rejects Iranian IPs) |
| Helm | 3.8+ (`helm version`) |
| Ingress | ingress-nginx recommended (any controller works if it does not buffer responses — the live feed is Server-Sent Events) |
| TLS | cert-manager with a ClusterIssuer, or your own TLS secret |
| Storage | a StorageClass that can provide a 2 Gi `ReadWriteOnce` volume |
| From the project owner | the **OpenAI API key** (sent privately — never in chat groups or files) and the **domain** to use |
| Image | `ghcr.io/sananiroomand/sarenakh:0.2.0` (public, or see step 3) |

Files in this kit: `sarenakh-0.1.0.tgz` (the chart), `values-production.example.yaml`, this guide.

---

## 1. Namespace

```bash
kubectl create namespace sarenakh
```

## 2. Secret with the OpenAI key

```bash
kubectl -n sarenakh create secret generic sarenakh-secrets \
  --from-literal=OPENAI_API_KEY='sk-...' \
  --from-literal=SESSION_SECRET="$(openssl rand -base64 48)"
```

(Type the key in your own terminal. To avoid it landing in shell history, prefix the command with a space or
use `--from-file`.)

## 3. Only if the image is private

Check: `docker pull ghcr.io/sananiroomand/sarenakh:0.2.0` without logging in. If that fails with
"unauthorized", either ask the owner to make the package public (GitHub → Packages → sarenakh → Package
settings → Change visibility), or create a pull secret with a GitHub token that has `read:packages`:

```bash
kubectl -n sarenakh create secret docker-registry ghcr \
  --docker-server=ghcr.io --docker-username=<github-user> --docker-password=<token>
```

and uncomment `imagePullSecrets` in your values file.

## 4. Values

```bash
cp values-production.example.yaml values-production.yaml
```

Edit the lines marked `# EDIT`: the domain (twice), the ingress class, the cert-manager ClusterIssuer, and the
StorageClass if the cluster has no default one.

## 5. Install

```bash
helm install sarenakh ./sarenakh-0.1.0.tgz -n sarenakh -f values-production.yaml
```

Point the domain's DNS **A record** at the ingress controller's external IP
(`kubectl -n ingress-nginx get svc ingress-nginx-controller`).

## 6. Check it

```bash
kubectl -n sarenakh get pods -w                     # 1/1 Running within ~1 minute
kubectl -n sarenakh logs deploy/sarenakh | head -20 # shows "=== Sarenakh model check ===" with OK lines
helm test sarenakh -n sarenakh                      # calls /health from inside the cluster
curl https://<domain>/health                        # {"status":"ok", ...}
```

Then open `https://<domain>` in a browser, sign up, and click **«امتحان سریع با داده نمونه»** (try sample data):
a live agent feed runs for ~15 seconds and ends on a results dashboard. Please also open the site **from a phone
on an Iranian connection** — that is how the judges will use it.

`/health` says `"status": "degraded"` (and the logs say why) if the OpenAI key or models failed the startup
check. The site still runs and the sample flow still works; new paid runs are refused until the check passes
(it retries in the background).

---

## Day-2 operations

**Upgrade to a newer image** (CI publishes `latest`, the app version, and `sha-<commit>`):

```bash
helm upgrade sarenakh ./sarenakh-0.1.0.tgz -n sarenakh -f values-production.yaml --set image.tag=sha-abc1234
```

The pod is recreated (never two at once — the database volume is single-writer); expect a few seconds of downtime.

**Change the OpenAI key:** update the secret, then restart:

```bash
kubectl -n sarenakh create secret generic sarenakh-secrets --from-literal=OPENAI_API_KEY='sk-...' \
  --from-literal=SESSION_SECRET="$(openssl rand -base64 48)" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n sarenakh rollout restart deploy/sarenakh
```

(A new SESSION_SECRET is harmless — logins are stored server-side.)

**Backup the database** (consistent copy via SQLite's backup API, then copy it out):

```bash
kubectl -n sarenakh exec deploy/sarenakh -- python -c \
  "import sqlite3; sqlite3.connect('/app/data/sarenakh.sqlite3').backup(sqlite3.connect('/tmp/backup.sqlite3'))"
kubectl -n sarenakh cp $(kubectl -n sarenakh get pod -l app.kubernetes.io/name=sarenakh -o name | cut -d/ -f2):/tmp/backup.sqlite3 ./sarenakh-backup.sqlite3
```

**Uninstall:** `helm uninstall sarenakh -n sarenakh`. The data volume `sarenakh-data` is **kept** on purpose;
delete it with `kubectl -n sarenakh delete pvc sarenakh-data` if you really want the data gone.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `ImagePullBackOff` | the GHCR package is private → step 3 |
| pod `Pending` | no StorageClass → set `persistence.storageClass` |
| `/health` degraded, logs: `403` / "region" | the cluster's egress IP is in a region OpenAI blocks → run outside Iran |
| `/health` degraded, logs: `401` | wrong key in `sarenakh-secrets` |
| live feed stays empty, results appear only at the end | the ingress buffers responses → keep `proxy-buffering: "off"` (ingress-nginx) or disable buffering in your controller |
| upload fails with 413 | raise `nginx.ingress.kubernetes.io/proxy-body-size` (app limit is 15 MB) |
| login works on http but not https (or the reverse) | `cookieSecure` is automatic when `ingress.tls` is set; force it with `--set cookieSecure=true` |

## Useful values

| value | default | meaning |
|---|---|---|
| `image.tag` | chart appVersion (`0.2.0`) | image version |
| `config.MODEL_CHECK` | `warn` | `strict` = refuse to start if the key/models fail |
| `config.GLOBAL_SPEND_CAP_USD` | `20` | hard cap on total OpenAI spend |
| `config.USER_DAILY_CAP_USD` | `1.50` | paid spend per user per 24 h (sample replays are free) |
| `persistence.size` | `2Gi` | database volume |
| `extraEnv` | `[]` | extra variables, e.g. `HTTPS_PROXY` if egress must go through a proxy |
| `ingress.*`, `resources`, `nodeSelector`, `tolerations`, `affinity` | | the usual |

Security defaults: runs as uid 10001, read-only root filesystem, all capabilities dropped, no service-account
token, seccomp `RuntimeDefault`.
