from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.database import create_tables, ensure_runtime_schema
from app.routers import auth, partners, clients, uploads, scores, admin, upload_flow, dashboard, reports
from app.extractors import DataExtractor
from app.scoring_engine import ScoringEngine
from app.advisory_generator import AdvisoryGenerator

import os

app = FastAPI(
    title="Vertibis API",
    description="MSME Business Health Scoring Platform for Indian CAs",
    version="2.0.0",
)

allowed_origins = [origin.strip() for origin in os.getenv(
    "CORS_ORIGINS",
    "https://admin.vertibis.com,https://partner.vertibis.com,https://vertibis.com,http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001,http://localhost:3002,http://127.0.0.1:3002",
).split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(partners.router)
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(clients.router)
app.include_router(uploads.router)
app.include_router(scores.router)
app.include_router(reports.router)
app.include_router(admin.router)
if os.getenv("ENABLE_LEGACY_UPLOAD_FLOW", "false").lower() in {"1", "true", "yes", "on"}:
    app.include_router(upload_flow.router)


MAX_REQUEST_BYTES = int(os.getenv("MAX_REQUEST_BYTES", os.getenv("MAX_UPLOAD_BYTES", str(15 * 1024 * 1024))))


@app.middleware("http")
async def apply_security_headers(request, call_next):
    content_length = request.headers.get("content-length")
    try:
        request_size = int(content_length or 0)
    except ValueError:
        request_size = 0
    if request_size > MAX_REQUEST_BYTES:
        return JSONResponse(
            status_code=413,
            content={"detail": f"Request body exceeds the {MAX_REQUEST_BYTES // (1024 * 1024)} MB limit."},
        )

    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response

# ── Static files ──────────────────────────────────────────────────────────────
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
def on_startup():
    create_tables()
    ensure_runtime_schema()


# ── Utility endpoints ─────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health_check():
    return {"status": "ok", "version": "2.0.0"}


@app.get("/dashboard", include_in_schema=False)
async def serve_dashboard():
    return FileResponse("static/index.html")


@app.get("/", tags=["System"])
def root():
    return {
        "message": "Vertibis API v2.0 — MSME Health Scoring Platform",
        "docs": "/docs",
        "endpoints": {
            "partners":     "POST/GET /api/admin/partners",
            "clients":      "POST/GET /api/v1/clients",
            "upload+score": "POST /api/v1/clients/{id}/upload",
            "scores":       "GET  /api/v1/clients/{id}/scores",
            "admin_stats":  "GET  /api/admin/stats",
            "credits":      "GET  /api/admin/partners/{id}/credits",
        },
    }


@app.get("/api/v1/ca/sample-report", tags=["System"],
         summary="Demo report — no database required")
def get_sample_report():
    files_dict = {
        "gstr1":   '{"filing_date": "2024-04-20", "total_taxable_supplies": 6200000, "total_itc_claimed": 4500000, "amendments_count": 1}',
        "gstr3b":  '{"filing_date": "2024-04-22", "total_sales": 6000000, "total_itc_availed": 4200000, "gst_payment": 240000}',
        "gstr2a":  '{"supplier_count": 45, "itc_received": 4200000, "discrepancies_count": 1}',
        "itr":     '{"filing_date": "2024-07-15", "total_turnover": 5500000, "net_profit": 550000, "profit_margin_pct": 10.0}',
        "banking": "date,balance,bounce_count\n2024-01-01,500000,0\n2024-02-01,620000,0\n2024-03-01,580000,1\n2024-04-01,710000,0",
    }

    extracted = DataExtractor.extract_all(files_dict, "2024-25")
    scores = ScoringEngine.calculate_score(extracted, "trading", 6_200_000)
    advisory = AdvisoryGenerator.generate_advisory(extracted, scores, "trading", "Test Business")

    return {
        "status": "success",
        "report": {
            "health_score": scores["total_score"],
            "score_breakdown": scores["components"],
            "issues": scores["issues"],
            "advisory": advisory,
            "data_completeness_pct": extracted.get("data_completeness_pct", 0),
        },
    }
