"""FastAPI entrypoint: API + SSE + the built React app, as one deployable."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import auth, datasets, products
from .config import get_settings
from .db import init_db, session
from .model_check import check_models, format_report
from .samples import ensure_sample_dataset

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sarenakh")

VERSION = "0.2.0"


async def _recheck_until_ok(app: FastAPI) -> None:
    """In degraded mode (transient OpenAI failure at boot), retry in the background."""
    delay = 30
    while not app.state.model_status.get("ok"):
        await asyncio.sleep(delay)
        report = await check_models()
        app.state.model_status = report
        log.warning(format_report(report))
        delay = min(delay * 2, 600)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    init_db()
    with session() as db:
        ensure_sample_dataset(db)
    app.state.model_status = {"ok": None, "skipped": True, "results": []}
    recheck: asyncio.Task | None = None
    if s.model_check != "off":
        report = await check_models(s)
        app.state.model_status = report
        log.info(format_report(report))
        if not report["ok"]:
            if s.model_check == "strict" and report["fatal"]:
                log.critical("Model check failed with a non-retryable error; refusing to start: %s", report["error"])
                raise RuntimeError(f"Model check failed: {report['error']}")
            log.error("Model check failed; starting in DEGRADED mode (new runs disabled): %s", report["error"])
            recheck = asyncio.create_task(_recheck_until_ok(app))
    yield
    if recheck:
        recheck.cancel()


app = FastAPI(title="Sarenakh", version=VERSION, lifespan=lifespan)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    """Return the first validation message in plain Persian (our validators raise Persian text)."""
    err = exc.errors()[0] if exc.errors() else {}
    msg = str(err.get("msg", "")).removeprefix("Value error, ")
    if not any("؀" <= ch <= "ۿ" for ch in msg):
        field = ".".join(str(p) for p in err.get("loc", [])[1:]) or "ورودی"
        msg = f"مقدار «{field}» معتبر نیست."
    return JSONResponse({"detail": msg}, status_code=422)


@app.exception_handler(Exception)
async def unhandled_error(_: Request, exc: Exception):
    log.exception("unhandled error: %s", exc)
    return JSONResponse({"detail": "خطای غیرمنتظره در سرور. لطفا دوباره تلاش کنید."}, status_code=500)


@app.get("/health")
@app.get("/api/health")
async def health():
    ms = app.state.model_status
    return {
        "status": "ok" if ms.get("ok") or ms.get("skipped") else "degraded",
        "version": VERSION,
        "models": [
            {"model": r["model"], "kind": r["kind"], "ok": r["ok"], "error": r["error"]}
            for r in ms.get("results", [])
        ],
        "model_check": "skipped" if ms.get("skipped") else ("ok" if ms.get("ok") else ms.get("error")),
    }


app.include_router(auth.router)
app.include_router(products.router)
app.include_router(datasets.router)


# --- Static frontend (built by Vite into frontend/dist); must stay last ------------------------

_static = get_settings().static_dir
if (_static / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=_static / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
async def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "Not found")
    candidate = (_static / path).resolve()
    if path and candidate.is_file() and _static.resolve() in candidate.parents:
        return FileResponse(candidate)
    index = _static / "index.html"
    if index.is_file():
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
    return {"app": "sarenakh", "note": "frontend not built — run `npm run build` in frontend/"}
