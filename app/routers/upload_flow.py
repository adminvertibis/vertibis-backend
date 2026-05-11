"""
Combined upload + score endpoint for the testing-phase wizard.

Single request:  client info + up to 9 files  →  creates client,
processes all files, calculates health score, returns result.
"""
import uuid
import os
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models import Client, FileUpload, DataPoint, HealthScore, Partner, CreditTransaction
from app.extractors import DataExtractor
from app.scoring_engine import ScoringEngine
from app.advisory_generator import AdvisoryGenerator

router = APIRouter(prefix="/api/v1", tags=["Upload Wizard"])

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")

# (file_type_label, data_category, extractor_key, fy_label, is_required)
FILE_META = {
    "gstr1_fy1":   ("GSTR1",   "GST",     "gstr1",   "2024-25", True),
    "gstr3b_fy1":  ("GSTR3B",  "GST",     "gstr3b",  "2024-25", True),
    "gstr2a_fy1":  ("GSTR2A",  "GST",     "gstr2a",  "2024-25", True),
    "gstr1_fy2":   ("GSTR1",   "GST",     "gstr1",   "2025-26", True),
    "gstr3b_fy2":  ("GSTR3B",  "GST",     "gstr3b",  "2025-26", True),
    "gstr2a_fy2":  ("GSTR2A",  "GST",     "gstr2a",  "2025-26", True),
    "banking_fy2": ("Banking", "Banking", "banking", "2025-26", False),
    "itr_prev":    ("ITR",     "ITR",     "itr",     "2023-24", True),
    "itr_curr":    ("ITR",     "ITR",     "itr",     "2024-25", True),
}


# ── Response schema ───────────────────────────────────────────────────────────

class UploadAndScoreResponse(BaseModel):
    client_id: str
    client_name: str
    files_processed: int
    files_missing: list
    health_score: float
    score_label: str          # CRITICAL / MODERATE / HEALTHY
    score_color: str          # hex color for UI
    score_components: dict
    issues: list
    advisory: str
    data_completeness_pct: float
    score_id: str
    credits_remaining: int


def _score_label(score: float) -> tuple[str, str]:
    if score >= 76:
        return "HEALTHY", "#10b981"
    if score >= 51:
        return "MODERATE", "#f59e0b"
    if score >= 26:
        return "AT RISK", "#f97316"
    return "CRITICAL", "#ef4444"


def _save_bytes(content: bytes, filename: str, client_id: uuid.UUID) -> str:
    d = os.path.join(UPLOAD_DIR, str(client_id))
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, filename)
    with open(path, "wb") as f:
        f.write(content)
    return path


def _store_data_points(
    db: Session,
    client_id: uuid.UUID,
    file_upload_id: uuid.UUID,
    extracted: dict,
    category: str,
):
    for data_type, value in extracted.items():
        if data_type in ("data_completeness_pct", "fy_year"):
            continue
        data_value: Optional[float] = None
        data_value_str: Optional[str] = None
        data_date: Optional[datetime] = None
        data_unit: Optional[str] = None

        if isinstance(value, datetime):
            data_date = value
        elif isinstance(value, (int, float)):
            data_value = float(value)
            if any(k in data_type for k in ("sales", "turnover", "balance", "profit", "payment", "itc")):
                data_unit = "INR"
            elif "pct" in data_type or "margin" in data_type:
                data_unit = "%"
        else:
            data_value_str = str(value) if value is not None else None

        db.add(DataPoint(
            client_id=client_id,
            file_upload_id=file_upload_id,
            data_type=data_type,
            data_category=category,
            data_date=data_date,
            data_value=data_value,
            data_value_str=data_value_str,
            data_unit=data_unit,
            source="manual_upload",
        ))


def _merge_for_scoring(extractions: dict) -> dict:
    """
    Merge per-file extractions into one flat dict for the scoring engine.
    Strategy: prefer FY 2025-26 GST data over 2024-25; prefer 2024-25 ITR over 2023-24.
    """
    # Priority order for each document type
    merged: dict = {}

    # GST: prefer FY2 (2025-26) over FY1 (2024-25)
    for ext_key in ("gstr2a", "gstr3b", "gstr1"):
        fy2 = extractions.get(f"{ext_key}_fy2", {})
        fy1 = extractions.get(f"{ext_key}_fy1", {})
        for k, v in fy2.items():
            if k not in ("data_completeness_pct", "fy_year") and v is not None:
                merged[k] = v
        for k, v in fy1.items():
            if k not in ("data_completeness_pct", "fy_year") and v is not None and k not in merged:
                merged[k] = v

    # ITR: prefer 2024-25 over 2023-24
    for itr_key in ("itr_curr", "itr_prev"):
        for k, v in extractions.get(itr_key, {}).items():
            if k not in ("data_completeness_pct", "fy_year") and v is not None and k not in merged:
                merged[k] = v

    # Banking
    for k, v in extractions.get("banking_fy2", {}).items():
        if k not in ("data_completeness_pct", "fy_year") and v is not None:
            merged[k] = v

    return merged


# ── Main endpoint ─────────────────────────────────────────────────────────────

@router.post(
    "/upload-and-score",
    response_model=UploadAndScoreResponse,
    summary="Create client + upload files + calculate health score in one request",
)
async def upload_and_score(
    # Client info
    client_name: str = Form(...),
    industry: str = Form("trading"),
    turnover: float = Form(0),
    gstin: str = Form(""),
    partner_id: str = Form(...),

    # FY 2024-25 GST
    gstr1_fy1: Optional[UploadFile] = File(None),
    gstr3b_fy1: Optional[UploadFile] = File(None),
    gstr2a_fy1: Optional[UploadFile] = File(None),

    # FY 2025-26 GST + Banking
    gstr1_fy2: Optional[UploadFile] = File(None),
    gstr3b_fy2: Optional[UploadFile] = File(None),
    gstr2a_fy2: Optional[UploadFile] = File(None),
    banking_fy2: Optional[UploadFile] = File(None),

    # ITR
    itr_prev: Optional[UploadFile] = File(None),
    itr_curr: Optional[UploadFile] = File(None),

    db: Session = Depends(get_db),
):
    # ── Validate partner ──────────────────────────────────────────────────────
    try:
        pid = uuid.UUID(partner_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid partner_id")

    partner = db.get(Partner, pid)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    if partner.credits_balance < 1:
        raise HTTPException(status_code=402, detail="Insufficient credits")

    # ── Create client ─────────────────────────────────────────────────────────
    client = Client(
        partner_id=pid,
        name=client_name.strip(),
        industry=industry,
        turnover=float(turnover) if turnover and float(turnover) > 0 else None,
        gstin=gstin.strip() or None,
    )
    db.add(client)
    db.flush()

    # ── Process each uploaded file ────────────────────────────────────────────
    file_uploads_map = {
        "gstr1_fy1": gstr1_fy1,
        "gstr3b_fy1": gstr3b_fy1,
        "gstr2a_fy1": gstr2a_fy1,
        "gstr1_fy2": gstr1_fy2,
        "gstr3b_fy2": gstr3b_fy2,
        "gstr2a_fy2": gstr2a_fy2,
        "banking_fy2": banking_fy2,
        "itr_prev": itr_prev,
        "itr_curr": itr_curr,
    }

    extractions: dict = {}          # key → extracted dict
    files_processed = 0
    files_missing = []

    for key, upload in file_uploads_map.items():
        file_type_label, category, ext_key, fy_label, is_required = FILE_META[key]

        if upload is None or upload.filename == "":
            if is_required:
                files_missing.append(f"{file_type_label} ({fy_label})")
            continue

        content_bytes = await upload.read()
        if not content_bytes:
            if is_required:
                files_missing.append(f"{file_type_label} ({fy_label})")
            continue

        content_str = content_bytes.decode("utf-8", errors="replace")
        saved_path = _save_bytes(content_bytes, upload.filename or f"{key}.dat", client.id)

        fu = FileUpload(
            client_id=client.id,
            partner_id=pid,
            file_name=upload.filename or f"{key}.dat",
            file_type=f"{file_type_label}_{fy_label}",
            file_path=saved_path,
            file_size=len(content_bytes),
            upload_method="manual_upload",
            processing_status="processed",
        )
        db.add(fu)
        db.flush()

        # Extract data for this file
        partial = DataExtractor.extract_all({ext_key: content_str}, fy_label)
        extractions[key] = partial

        # Persist data points
        _store_data_points(db, client.id, fu.id, partial, category)
        files_processed += 1

    if files_processed == 0:
        db.rollback()
        raise HTTPException(status_code=400, detail="No valid files were uploaded")

    # ── Merge data and score ──────────────────────────────────────────────────
    merged = _merge_for_scoring(extractions)
    merged["data_completeness_pct"] = DataExtractor._calculate_completeness(merged)

    eff_turnover = client.turnover or merged.get("gstr1_total_sales") or 1_000_000
    scores = ScoringEngine.calculate_score(merged, industry, eff_turnover)
    advisory = AdvisoryGenerator.generate_advisory(merged, scores, industry, client_name)

    components = scores.get("components", {})
    hs = HealthScore(
        client_id=client.id,
        total_score=scores["total_score"],
        gst_integrity_score=components.get("gst_itc_score"),
        compliance_behaviour_score=components.get("filing_score"),
        cashflow_health_score=components.get("cashflow_score"),
        data_credibility_score=components.get("completeness_score"),
        issues=scores.get("issues", []),
        advisory=advisory,
        data_completeness_pct=merged.get("data_completeness_pct"),
        gst_data_source="manual",
    )
    db.add(hs)

    # ── Deduct credit ─────────────────────────────────────────────────────────
    partner.credits_balance -= 1
    db.add(CreditTransaction(
        partner_id=pid,
        transaction_type="usage",
        credits_amount=-1,
        related_client_id=client.id,
        description=f"Score: {client_name}",
    ))

    client.latest_data_date = datetime.utcnow()
    client.latest_data_source = "manual_upload"
    db.commit()
    db.refresh(hs)
    db.refresh(partner)

    label, color = _score_label(hs.total_score)

    return UploadAndScoreResponse(
        client_id=str(client.id),
        client_name=client.name,
        files_processed=files_processed,
        files_missing=files_missing,
        health_score=round(hs.total_score, 1),
        score_label=label,
        score_color=color,
        score_components={
            "GST Integrity":        round(components.get("gst_itc_score") or 0, 1),
            "Filing Compliance":    round(components.get("filing_score") or 0, 1),
            "Cashflow Health":      round(components.get("cashflow_score") or 0, 1),
            "Data Completeness":    round(components.get("completeness_score") or 0, 1),
        },
        issues=scores.get("issues", []),
        advisory=advisory,
        data_completeness_pct=round(merged.get("data_completeness_pct") or 0, 1),
        score_id=str(hs.id),
        credits_remaining=partner.credits_balance,
    )
