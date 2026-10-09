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
- [ ] Run model check with real key (needs `.env`)
- [ ] Deploy hello-world to the server (needs server details)

## Phase 1 — Data
- [x] Sample chat: 391 msgs / 40 people / 7 days, Telegram Desktop JSON, Finglish + code-switching,
      stickers, edits, forwards (source script `samples/source/python_iran.chat` → `samples/build_sample.py`)
- [x] PyStart course: 9 leads + 11 decoys (senior, already enrolled, sarcasm, competitor ad, free-only,
      tutor ad, debugging-only, wrong language, changed mind via history, meme, too advanced)
- [x] Cheshm-Aram glasses (2nd product): 5 leads + 5 decoys (idiom, already owns, medical, gaming monitor, ad)
- [x] `samples/ground_truth.json` (leads counted per person) + `samples/products.json` (facts for grounding)
- [x] Parser: Telegram export (single chat or full-account), pasted text (Telegram copy / "Name: msg" / lines)
- [x] Persian normalization (ي/ك, digits, ZWNJ, emoji spam, letter runs) + Finglish detection
- [x] ChatIndex: reply threads, descendants, author history, nearby, keyword search, prompt rendering
- [x] 16 pytest tests (thread-only lead, resolved-in-thread decoy, changed-mind-in-history decoy)

## Phase 2 — Auth, DB, input endpoints
## Phase 3 — Agents (profile, pre-filter, triage, investigator, critic, drafter) + cost/budget
## Phase 4 — Orchestrator, event log, SSE
## Phase 5 — Frontend pages, live feed, dashboard (radar, funnel, opportunity map)
## Phase 6 — Eval script + evaluation page, prompt tuning
## Phase 7 — Production deploy + end-to-end test (incl. phone)
## Phase 8 — Polish
## Phase 9 — Docs (README, technical, business plan, pitch, video script)
