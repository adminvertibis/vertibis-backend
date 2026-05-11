from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.database import create_tables
from app.routers import auth, partners, clients, uploads, scores, admin, upload_flow
from app.extractors import DataExtractor
from app.scoring_engine import ScoringEngine
from app.advisory_generator import AdvisoryGenerator

app = FastAPI(
    title="Vertibis API",
    description="MSME Business Health Scoring Platform for Indian CAs",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(partners.router)
app.include_router(auth.router)
app.include_router(clients.router)
app.include_router(uploads.router)
app.include_router(scores.router)
app.include_router(admin.router)
app.include_router(upload_flow.router)

# ── Static files ──────────────────────────────────────────────────────────────
import os
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


@app.on_event("startup")
def on_startup():
    create_tables()


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
