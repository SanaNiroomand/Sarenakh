# Sarenakh — build task list

Legend: `[x]` done · `[~]` in progress · `[ ]` todo · `[-]` cut

## Phase 0 — Scaffold & hello-world deploy
- [x] Repo, .gitignore, .env.example, TASKS.md
- [x] Config: model IDs per role, reasoning effort, price table (USD/1M, from OpenAI pricing page), PRICES_JSON override
- [x] LLM wrapper on the Responses API (tool calling is Responses-only for these models) + per-call cost from `usage`
- [x] Startup model check: forced tool call + strict JSON schema per chat model, one embedding; strict/warn/off
- [x] `/health` + SPA static serving
- [x] Frontend scaffold: React 19 + Vite 8 + Tailwind 4, RTL, bundled Vazirmatn UI FD (Persian digits)
- [x] Dockerfile (multi-stage), docker-compose (app + Caddy auto-HTTPS), deploy script
- [x] Model check with the real key: gpt-6-luna, gpt-6.1-sol, text-embedding-3-small all OK ($0.001)
- [ ] Deploy to the server (waiting for a VPS outside Iran)

## Phase 1 — Data
- [x] Sample chat: 391 msgs / 40 people / 7 days, Telegram Desktop JSON, Finglish + code-switching
- [x] Real products: Quera College beginner Python (9 leads + 11 decoys); Novin Optic blue-cut glasses on Basalam (5 + 5)
- [x] Ground truth (per person) + products.json (facts for grounding)
- [x] Parser (Telegram export, full-account export, pasted text), Persian normalization, ChatIndex
- [ ] Persian notes in ground truth (shown on the evaluation page)

## Phase 2 — Auth, DB, inputs
- [x] SQLite models, bcrypt (SHA-256 pre-hash) + server-side session cookies, rate limits
- [x] Products, datasets (upload / paste / shared sample), Persian errors

## Phase 3 — Agents
- [x] Profile agent (1–2 questions) → sample profiles built by the agent
- [x] Embedding pre-filter with reply-context scoring
- [x] Triage (gpt-6-luna, batches of 25, split-and-retry)
- [x] Investigator tool loop (6 tools, ≤5 steps), evidence-first Verdict, hard rules in Python
- [x] Critic for borderline fits; help-first drafter with fact retrieval, check, one revision
- [x] Budget reservations, global cap, spend log, stage cache, dynamic few-shot from feedback

## Phase 4 — Orchestrator & streaming
- [x] Runs API with spend guards, SSE (backlog + live), results payload, feedback, evaluation
- [x] Free paced replay of cached sample runs (works even at the global cap)

## Phase 5 — Frontend
- [x] Landing, sign up, log in, dashboard with one-click sample runs
- [x] Product setup: agent chat + editable profile with ideal-shape radar
- [x] Data step: sample / upload / paste + budget selector
- [x] Live feed grouped per followed person, budget meter, live counters
- [x] Results: KPIs, lead cards with radar + ideal overlay, evidence chips → chat drawer, replies with copy,
      👍/👎, compare up to 3, funnel with stage cost, opportunity map, burn line, why-not panel
- [x] Lead detail (scores, reasoning, critic, tool path, evidence), evaluation page
- [x] Mobile: no horizontal overflow at 375px; chart pages lazy-loaded

## Phase 6 — Eval & tuning
- [x] scripts/eval.py (precision, recall, cost, cost/lead) — 9/9 and 5/5, 0 false positives
- [ ] Repeat runs for variance numbers; golden cache shipped with the image (replay works without OpenAI)

## Phase 7 — Production deploy + end-to-end test (incl. phone)
## Phase 8 — Polish
## Phase 9 — Docs (README, technical, business plan, pitch, video script)
