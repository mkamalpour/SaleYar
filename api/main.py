"""
api/main.py

FastAPI production server.
"""

import json
import logging
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import console  # noqa: F401  — forces UTF-8 stdout before anything prints

import config
from models import loader
from output import reporter
from pipeline import runner, stage7_optimizer, stage5_basket, stage6_risk

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ============================================================================
# JSON SERIALIZATION FIX (handles numpy, pandas types)
# ============================================================================
import numpy as np
import pandas as pd

class SafeJSONEncoder(json.JSONEncoder):
    """Safe JSON encoder that handles numpy, pandas, and datetime types."""
    def default(self, obj):
        if isinstance(obj, (np.integer, np.int8, np.int16, np.int32, np.int64)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float16, np.float32, np.float64)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        if hasattr(obj, 'isoformat'):
            return obj.isoformat()
        if isinstance(obj, pd.Series):
            return obj.to_list()
        return str(obj)

def safe_json_serialize(obj):
    """Convert any object to JSON-serializable format."""
    return json.loads(json.dumps(obj, cls=SafeJSONEncoder))

# ============================================================================

os.makedirs("logs", exist_ok=True)
os.makedirs("saved_reports", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        logging.FileHandler("logs/app.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# Origins allowed to call the API. Defaults to localhost only — set
# SALEYAR_CORS_ORIGINS to a comma-separated list to widen it deliberately.
_cors_raw = os.getenv("SALEYAR_CORS_ORIGINS", "").strip()
ALLOWED_ORIGINS = (
    [o.strip() for o in _cors_raw.split(",") if o.strip()]
    if _cors_raw
    else [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    loader.load_all()
    logger.info("Server started — all models loaded")
    yield


app = FastAPI(
    title="SaleYar — Offline Shop Intelligence API",
    description="Business intelligence for Iranian shops. Reads Holoo invoice exports.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)

_jobs: dict = {}
# Latest report per shop, so /report/{shop_id} and /health/{shop_id} work even
# when SAVE_REPORTS_TO_DISK is off. Bounded by MAX_REPORT_SHOPS.
_reports: dict = {}
MAX_REPORT_SHOPS = 50
_executor = ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT_JOBS)
SERVER_START = datetime.now().isoformat()
MAX_UPLOAD_BYTES = config.MAX_FILE_SIZE_MB * 1024 * 1024


def _store_report(shop_id: str, report: dict) -> None:
    """Cache the newest report for a shop, evicting the oldest shop if full."""
    if shop_id in _reports:
        _reports.pop(shop_id)
    elif len(_reports) >= MAX_REPORT_SHOPS:
        _reports.pop(next(iter(_reports)))
    _reports[shop_id] = report


def _load_report(shop_id: str):
    """Read a report from the in-memory cache, falling back to disk."""
    if shop_id in _reports:
        return _reports[shop_id]
    return reporter.load_latest(shop_id)


def _prune_jobs() -> None:
    """Drop finished job payloads older than the TTL so memory stays bounded."""
    cutoff = time.time() - config.JOB_RESULT_TTL_SECONDS
    stale = [
        job_id
        for job_id, job in _jobs.items()
        if job["status"] != "running" and job["started"] < cutoff
    ]
    for job_id in stale:
        _jobs.pop(job_id, None)
    if stale:
        logger.info(f"Pruned {len(stale)} expired job result(s)")


def _require_key(x_api_key: Optional[str]):
    # Constant-time comparison so the key cannot be recovered by timing the API.
    import hmac

    if not x_api_key or not hmac.compare_digest(x_api_key, config.API_KEY):
        raise HTTPException(status_code=403, detail="Invalid or missing API key.")


async def _read_upload(file: UploadFile) -> bytes:
    """Read an upload, rejecting anything over MAX_FILE_SIZE_MB."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file has no name.")

    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File is larger than the {config.MAX_FILE_SIZE_MB} MB limit.",
        )
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    return data


def _validate_upload(file: UploadFile):
    allowed_extensions = {".csv", ".xlsx", ".xls", ".txt"}
    ext = os.path.splitext(file.filename or "")[-1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' is not supported. Please upload a CSV, Excel, or TXT file.",
        )


# ─────────────────────────────────────────────────────────────
# POST /analyze
# ─────────────────────────────────────────────────────────────

@app.post("/analyze", summary="Full pipeline — returns job_id immediately")
async def analyze(
    file:      UploadFile  = File(...),
    shop_id:   str         = Form("default"),
    budget:    float       = Form(1_000_000),
    goal:      str         = Form("maximize_profit"),
    language:  str         = Form("en"),
    x_api_key: Optional[str] = Header(None),
):
    _require_key(x_api_key)
    _validate_upload(file)

    file_bytes = await _read_upload(file)
    job_id = str(uuid.uuid4())
    _prune_jobs()
    _jobs[job_id] = {
        "status":  "running",
        "result":  None,
        "error":   None,
        "started": time.time(),
    }

    def _run():
        try:
            result = runner.run_pipeline(
                file_bytes, file.filename, budget, shop_id, goal, language
            )
            report = reporter.assemble_and_save(result, shop_id, save_to_disk=config.SAVE_REPORTS_TO_DISK)
            result["report"] = report
            _store_report(shop_id, report)
            _jobs[job_id]["result"] = safe_json_serialize(result)
            _jobs[job_id]["status"] = "done"
        except Exception as e:
            logger.error(f"Pipeline error for job {job_id}: {e}", exc_info=True)
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["error"]  = str(e)

    _executor.submit(_run)
    logger.info(f"Job {job_id} started | shop={shop_id} | file={file.filename}")

    return {
        "job_id":    job_id,
        "status":    "running",
        "poll_url":  f"/result/{job_id}",
        "message":   "Analysis started. Poll /result/{job_id} every 3 seconds.",
    }


# ─────────────────────────────────────────────────────────────
# GET /result/{job_id}
# ─────────────────────────────────────────────────────────────

@app.get("/result/{job_id}", summary="Poll for job result")
def get_result(job_id: str, x_api_key: Optional[str] = Header(None)):
    _require_key(x_api_key)

    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    if job["status"] == "running":
        elapsed = round(time.time() - job["started"], 1)
        return {"status": "running", "elapsed_seconds": elapsed}

    if job["status"] == "error":
        return JSONResponse(
            status_code=500,
            content={"status": "error", "error": job["error"]},
        )

    return {"status": "done", "result": job["result"]}


# ─────────────────────────────────────────────────────────────
# POST /optimize
# ─────────────────────────────────────────────────────────────

@app.post("/optimize", summary="Budget optimizer only — under 2 seconds")
async def optimize(
    file:      UploadFile  = File(...),
    shop_id:   str         = Form("default"),
    budget:    float       = Form(1_000_000),
    goal:      str         = Form("maximize_profit"),
    language:  str         = Form("en"),
    x_api_key: Optional[str] = Header(None),
):
    _require_key(x_api_key)
    _validate_upload(file)

    try:
        from pipeline import stage1_cleaner, stage2_metrics, stage4_segments, stage3_forecast
        from pipeline.runner import calculate_current_inventory

        file_bytes = await _read_upload(file)
        s1 = stage1_cleaner.run(file_bytes, file.filename, language)
        if not s1["passed"]:
            return JSONResponse(
                status_code=200,
                content={"error": s1["message"], "flagged": s1["flagged"]},
            )

        df = s1["df"]
        df_kpis = stage2_metrics.run(df)
        df_kpis = stage4_segments.run(df_kpis)
        
        # Add forecast
        forecasts = stage3_forecast.run(df, df_kpis)
        
        # Add inventory
        current_inventory = calculate_current_inventory(df, shop_id, use_transaction_type=True)
        current_inventory = {k: max(0, v) for k, v in current_inventory.items()}
        
        basket = stage5_basket.run(df, shop_id)
        df_kpis = stage6_risk.run(df_kpis, language)

        result = stage7_optimizer.run(
            df_kpis=df_kpis,
            budget=budget,
            goal=goal,
            basket_result=basket,
            current_inventory=current_inventory,
            forecasts=forecasts,
            language=language
        )
        return safe_json_serialize(result)

    except Exception as e:
        logger.error(f"/optimize error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────
# POST /basket
# ─────────────────────────────────────────────────────────────

@app.post("/basket", summary="Basket analysis only — under 8 seconds")
async def basket(
    file:      UploadFile  = File(...),
    shop_id:   str         = Form("default"),
    x_api_key: Optional[str] = Header(None),
):
    _require_key(x_api_key)
    _validate_upload(file)

    try:
        from pipeline import stage1_cleaner

        file_bytes = await _read_upload(file)
        s1 = stage1_cleaner.run(file_bytes, file.filename)
        if not s1["passed"]:
            return JSONResponse(
                status_code=200,
                content={"error": s1["message"]},
            )
        result = stage5_basket.run(s1["df"], shop_id)
        return safe_json_serialize(result)

    except Exception as e:
        logger.error(f"/basket error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────
# POST /risk
# ─────────────────────────────────────────────────────────────

@app.post("/risk", summary="Risk scoring only — under 3 seconds")
async def risk(
    file:      UploadFile  = File(...),
    shop_id:   str         = Form("default"),
    language:  str         = Form("en"),
    x_api_key: Optional[str] = Header(None),
):
    _require_key(x_api_key)
    _validate_upload(file)

    try:
        from pipeline import stage1_cleaner, stage2_metrics

        file_bytes = await _read_upload(file)
        s1 = stage1_cleaner.run(file_bytes, file.filename, language)
        if not s1["passed"]:
            return JSONResponse(
                status_code=200,
                content={"error": s1["message"]},
            )
        df_kpis = stage2_metrics.run(s1["df"])
        df_kpis = stage6_risk.run(df_kpis, language)
        result = df_kpis[["product", "risk_score", "risk_explanation"]].to_dict("records")
        return safe_json_serialize(result)

    except Exception as e:
        logger.error(f"/risk error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────
# GET /report/{shop_id}
# ─────────────────────────────────────────────────────────────

@app.get("/report/{shop_id}", summary="Latest saved report — instant")
def get_report(shop_id: str, x_api_key: Optional[str] = Header(None)):
    _require_key(x_api_key)

    report = _load_report(shop_id)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"No saved report found for shop '{shop_id}'. Run /analyze first.",
        )
    return safe_json_serialize(report)


# ─────────────────────────────────────────────────────────────
# GET /health/{shop_id}
# ─────────────────────────────────────────────────────────────

@app.get("/health/{shop_id}", summary="Shop health score — instant")
def get_health(shop_id: str, x_api_key: Optional[str] = Header(None)):
    _require_key(x_api_key)

    report = _load_report(shop_id)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"No report found for shop '{shop_id}'. Run /analyze first.",
        )
    return safe_json_serialize({
        "shop_id":      shop_id,
        "health_score": report.get("health_score"),
        "data_quality": report.get("data_quality"),
        "shop_roi":     report.get("shop_roi"),
        "vs_bank":      report.get("vs_bank"),
        "generated_at": report.get("generated_at"),
    })


# ─────────────────────────────────────────────────────────────
# GET /healthcheck
# ─────────────────────────────────────────────────────────────

@app.get("/healthcheck", summary="Server status")
def healthcheck(x_api_key: Optional[str] = Header(None)):
    _require_key(x_api_key)

    uptime = round(
        (datetime.now() - datetime.fromisoformat(SERVER_START)).total_seconds()
    )
    active_jobs = sum(1 for j in _jobs.values() if j["status"] == "running")

    return {
        "status":         "ok",
        "server_started": SERVER_START,
        "uptime_seconds": uptime,
        "active_jobs":    active_jobs,
        "loaded_models":  loader.get_status(),
        "ready":          loader.is_ready(),
    }


class LLMAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    report_summary: dict = Field(default_factory=dict)
    inventory: dict = Field(default_factory=dict)
    forecasts: dict = Field(default_factory=dict)
    language: str = Field("en", pattern="^(en|fa)$")
    talk: bool = True


@app.post("/llm/ask", summary="Ask the shop advisor")
async def llm_ask(
    data: LLMAskRequest,
    x_api_key: Optional[str] = Header(None),
):
    _require_key(x_api_key)
    from llm.agent import ask_llm

    answer = ask_llm(
        data.report_summary,
        data.question,
        data.language,
        data.talk,
        data.inventory,
        data.forecasts,
    )
    if answer is None:
        raise HTTPException(status_code=500, detail="LLM advisor is unavailable.")
    return {"answer": answer}