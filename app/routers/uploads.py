import uuid
import os
import re
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.auth_utils import get_current_partner
from app.database import get_db
from app.models import Client, FileUpload, DataPoint, HealthScore, GSTReturnNormalizedData, Partner, CreditTransaction
from app.schemas import FileUploadOut, ScoreCalculateResponse, ScoreComponentsOut
from app.extractors import DataExtractor
from app.scoring_engine import ScoringEngine
from app.advisory_generator import AdvisoryGenerator
from app.pricing_config import get_credit_rule, get_size_band, normalize_report_slug
from app.upload_security import safe_upload_filename, validate_upload_bytes

router = APIRouter(prefix="/api/v1/clients", tags=["File Uploads"])

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "/tmp/vertibis_uploads" if os.getenv("VERCEL") else "uploads")

FILE_TYPE_MAP = {
    "gstr1": "GSTR1",
    "gstr3b": "GSTR3B",
    "gstr2a": "GSTR2A",
    "itr": "ITR",
    "banking": "Banking",
}

DATA_CATEGORY_MAP = {
    "gstr1": "GST",
    "gstr3b": "GST",
    "gstr2a": "GST",
    "itr": "ITR",
    "banking": "Banking",
}

REPORT_PRODUCTS = {
    "quick_snapshot": {"label": "Quick Business Health Snapshot", "required_gst_files": 0, "required_itr_files": 1, "prefix": "QR"},
    "annual": {"label": "Annual Business Health Report", "required_gst_files": 0, "required_itr_files": 1, "prefix": "AR"},
    "detailed_2y": {"label": "Detailed 2-Year Trend Report", "required_gst_files": 0, "required_itr_files": 2, "prefix": "DR"},
    "premium_advisory": {"label": "Premium Advisory Report", "required_gst_files": 0, "required_itr_files": 2, "prefix": "PR"},
    "loan_readiness": {"label": "Loan Readiness / NBFC-Focused Report", "required_gst_files": 0, "required_itr_files": 2, "prefix": "LR"},
}



GSTIN_RE = re.compile(r"\b[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")


def _normalize_gstin(value: object) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(value or "").upper())


def _detect_gstins(filename: str, content_text: str) -> set[str]:
    haystack = f"{filename}\n{content_text}".upper()
    return {_normalize_gstin(match.group(0)) for match in GSTIN_RE.finditer(haystack)}


def _has_valid_consent(client: Client) -> bool:
    status_value = str(getattr(client, "consent_status", "") or "").lower()
    if status_value not in {"signed", "active", "approved"}:
        return False
    expires_at = getattr(client, "consent_expires_at", None)
    return expires_at is None or expires_at >= datetime.utcnow()

def _infer_upload_key(filename: str) -> str:
    normalized = filename.lower().replace("-", "_").replace(" ", "_")
    aliases = [
        ("gstr1", ("gstr1", "gstr_1", "r1", "sales")),
        ("gstr3b", ("gstr3b", "gstr_3b", "3b")),
        ("gstr2a", ("gstr2b", "gstr_2b", "gstr2a", "gstr_2a", "2b", "2a")),
        ("itr", ("itr", "income_tax")),
        ("banking", ("bank", "statement", "cashflow")),
    ]
    for key, names in aliases:
        if any(name in normalized for name in names):
            return key
    return "gstr1"


def _infer_gst_key(filename: str) -> str:
    key = _infer_upload_key(filename)
    return key if key in {"gstr1", "gstr3b", "gstr2a"} else "gstr1"


def _merge_extracted(target: dict, partial: dict, key: str, index: int) -> None:
    for name, value in partial.items():
        if name in ("data_completeness_pct", "fy_year"):
            continue
        target[name] = value
        target[f"{key}_{index}_{name}"] = value


def _latest_gst_return_summary(db: Session, client_id: uuid.UUID) -> dict:
    rows = (
        db.query(GSTReturnNormalizedData)
        .filter(GSTReturnNormalizedData.client_id == client_id)
        .order_by(GSTReturnNormalizedData.fetched_at.desc())
        .limit(36)
        .all()
    )
    if not rows:
        return {}

    summary: dict = {
        "gst_return_api_signal_available": True,
        "gstr1_total_sales": 0,
        "gstr1_invoice_count": 0,
        "gstr3b_total_sales": 0,
        "gstr3b_itc_availed": 0,
        "gstr3b_gst_payment": 0,
        "gstr2a_itc_received": 0,
        "gstr2a_supplier_count": 0,
    }
    seen_period_returns: set[tuple[str, str]] = set()
    for row in rows:
        key = (row.period, row.return_type)
        if key in seen_period_returns:
            continue
        seen_period_returns.add(key)
        data = row.normalized_json or {}
        if row.return_type == "gstr1":
            summary["gstr1_total_sales"] += float(data.get("b2b_taxable_value") or 0)
            summary["gstr1_invoice_count"] += int(data.get("invoice_count") or 0)
        elif row.return_type == "gstr3b":
            summary["gstr3b_total_sales"] += float(data.get("outward_taxable_value") or 0)
            summary["gstr3b_itc_availed"] += float(data.get("eligible_itc") or 0)
            summary["gstr3b_gst_payment"] += float(data.get("cash_paid") or data.get("output_tax") or 0)
        elif row.return_type == "gstr2b":
            summary["gstr2a_itc_received"] += float(data.get("eligible_itc") or 0)
            summary["gstr2a_supplier_count"] += int(data.get("supplier_count") or 0)
    return summary


def _merge_gst_return_summary(target: dict, summary: dict) -> None:
    if not summary:
        return
    target.update(summary)
    target["gst_data_source"] = "gst_return_api"
    target["latest_data_source"] = "gst_return_api"


def _store_api_data_points(db: Session, client_id: uuid.UUID, summary: dict) -> None:
    for key, value in summary.items():
        if value in (None, ""):
            continue
        numeric_value = value if isinstance(value, (int, float)) else None
        db.add(DataPoint(
            client_id=client_id,
            file_upload_id=None,
            data_type=key,
            data_category="GST",
            data_date=datetime.utcnow(),
            data_value=float(numeric_value) if numeric_value is not None else None,
            data_value_str=None if numeric_value is not None else str(value),
            data_unit="count" if key.endswith("_count") else "INR",
            source="gst_return_api",
            verified=True,
        ))


def _save_file(content: bytes, filename: str, client_id: uuid.UUID) -> tuple[str, str]:
    client_dir = os.path.join(UPLOAD_DIR, str(client_id))
    os.makedirs(client_dir, exist_ok=True)
    stored_filename = safe_upload_filename(filename)
    path = os.path.join(client_dir, stored_filename)
    with open(path, "wb") as f:
        f.write(content)
    return path, stored_filename


def _normalize_report_type(value: object) -> str:
    return normalize_report_slug(value)


def _client_size_band(value: object, turnover: float | None = None) -> str | None:
    band = get_size_band(value, turnover)
    return band.name if band else None


def _report_economics(report_type: str, client_size_band: str | None, turnover: float | None) -> tuple[int, int, int | None, int | None]:
    rule = get_credit_rule(report_type, client_size_band, turnover)
    credits_required = int(rule.credits_required or 0) if rule and rule.credits_required is not None else 0
    suggested_min = rule.suggested_fee_min if rule else None
    suggested_max = rule.suggested_fee_max if rule else None
    report_price = int(suggested_min or 0)
    return report_price, credits_required, suggested_min, suggested_max


def _report_number(report_type: str, client: Client) -> str:
    prefix = REPORT_PRODUCTS[report_type]["prefix"]
    return f"{prefix}-{datetime.utcnow():%Y%m}-{str(client.id)[:8].upper()}-{uuid.uuid4().hex[:5].upper()}"


def _store_data_points(
    db: Session,
    client_id: uuid.UUID,
    file_upload_id: uuid.UUID,
    extracted: dict,
    file_key: str,
) -> None:
    category = DATA_CATEGORY_MAP.get(file_key, "Custom")

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

        dp = DataPoint(
            client_id=client_id,
            file_upload_id=file_upload_id,
            data_type=data_type,
            data_category=category,
            data_date=data_date,
            data_value=data_value,
            data_value_str=data_value_str,
            data_unit=data_unit,
            source="manual_upload",
        )
        db.add(dp)


def _run_pipeline(
    db: Session,
    client: Client,
    all_extracted: dict,
    report_type: str,
    client_size_band: str | None,
    report_price: int,
    credits_required: int,
    suggested_fee_min: int | None,
    suggested_fee_max: int | None,
    branding_mode: str,
    scoring_profile: str,
) -> HealthScore:
    industry = client.industry or "trading"
    turnover = client.turnover or all_extracted.get("gstr1_total_sales", 1_000_000)

    scores = ScoringEngine.calculate_score(all_extracted, industry, turnover, scoring_profile=scoring_profile)
    advisory = AdvisoryGenerator.generate_advisory(all_extracted, scores, industry, client.name)

    components = scores.get("components", {})
    hs = HealthScore(
        client_id=client.id,
        total_score=scores["total_score"],
        report_number=_report_number(report_type, client),
        report_type=report_type,
        report_variant=REPORT_PRODUCTS[report_type]["label"],
        turnover_band=client_size_band,
        client_size_band=client_size_band,
        report_price=report_price,
        credits_required=credits_required,
        credits_used=0,
        suggested_fee_min=suggested_fee_min,
        suggested_fee_max=suggested_fee_max,
        scoring_version=scores.get("scoring_version", ScoringEngine.VERSION),
        scoring_profile=scores.get("scoring_profile", scoring_profile),
        branding_mode=branding_mode,
        report_status="locked",
        gst_integrity_score=components.get("gst_integrity_score"),
        itr_consistency_score=components.get("itr_consistency_score"),
        compliance_behaviour_score=components.get("compliance_behaviour_score"),
        cashflow_health_score=components.get("cashflow_health_score"),
        data_credibility_score=components.get("data_credibility_score"),
        issues=scores.get("issues", []),
        advisory=advisory,
        data_completeness_pct=all_extracted.get("data_completeness_pct"),
        gst_data_source=all_extracted.get("gst_data_source") or "manual",
    )
    db.add(hs)

    client.latest_data_date = datetime.utcnow()
    client.latest_data_source = "manual_upload"

    db.commit()
    db.refresh(hs)
    return hs


@router.post(
    "/{client_id}/upload",
    response_model=ScoreCalculateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload files and get health score in one step",
)
async def upload_files(
    client_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_partner: Partner = Depends(get_current_partner),
):
    client = db.get(Client, client_id)
    if not client or client.partner_id != current_partner.id:
        raise HTTPException(status_code=404, detail="Client not found")

    if not _has_valid_consent(client):
        raise HTTPException(
            status_code=422,
            detail="Client consent is pending or expired. Record signed consent before processing documents.",
        )

    partner = current_partner
    partner_id = current_partner.id

    form = await request.form()
    fy_year = str(form.get("fy_year") or "2024-25")
    report_type = _normalize_report_type(form.get("report_type") or form.get("upload_mode") or "quick")
    upload_mode = report_type
    scoring_profile = str(form.get("scoring_profile") or "core").strip().lower()
    branding_mode = str(form.get("branding_mode") or "co_branded").strip().lower()
    gst_source = str(form.get("gst_source") or "").strip().lower()
    band = _client_size_band(form.get("client_size_band") or form.get("turnover_band"), client.turnover)
    price, credits_required, suggested_fee_min, suggested_fee_max = _report_economics(report_type, band, client.turnover)

    def form_files(field: str) -> list[UploadFile]:
        values = form.getlist(field)
        return [value for value in values if getattr(value, "filename", None) and hasattr(value, "read")]

    upload_entries: list[tuple[str, UploadFile]] = []
    for key in ("gstr1", "gstr3b", "gstr2a", "itr", "banking"):
        upload_entries.extend((key, upload) for upload in form_files(key))

    upload_entries.extend((_infer_gst_key(upload.filename or ""), upload) for upload in form_files("gst_files"))
    upload_entries.extend(("itr", upload) for upload in form_files("itr_files"))
    upload_entries.extend(("banking", upload) for upload in form_files("banking_files"))
    upload_entries.extend((_infer_upload_key(upload.filename or ""), upload) for upload in form_files("files"))

    # Frontend sends both grouped fields and a generic files field for compatibility.
    # De-duplicate by UploadFile object identity so each selected file is processed once.
    deduped_entries: list[tuple[str, UploadFile]] = []
    seen_uploads: set[tuple[str, str]] = set()
    for key, upload in upload_entries:
        identity = (key, upload.filename or "")
        if identity in seen_uploads:
            continue
        seen_uploads.add(identity)
        deduped_entries.append((key, upload))

    if not deduped_entries:
        raise HTTPException(status_code=400, detail="No files provided")

    product = REPORT_PRODUCTS[report_type]
    gst_api_requested = gst_source in {"api", "gst_api", "gstn"} or str(form.get("gst_fetch_requested") or "").lower() == "true"
    required_gst_count = 0 if gst_api_requested else int(product["required_gst_files"])
    required_itr_count = int(product["required_itr_files"])
    gst_count = sum(1 for key, _ in deduped_entries if key in {"gstr1", "gstr3b", "gstr2a"})
    itr_count = sum(1 for key, _ in deduped_entries if key == "itr")
    if gst_count < required_gst_count or itr_count < required_itr_count:
        raise HTTPException(
            status_code=422,
            detail=f"{product['label']} requires at least {required_gst_count} GST files and {required_itr_count} ITR JSON file(s)",
        )

    all_extracted: dict = {
        "upload_mode": upload_mode,
        "report_type": report_type,
        "turnover_band": band,
        "client_size_band": band,
        "report_price": price,
        "credits_required": credits_required,
        "suggested_fee_min": suggested_fee_min,
        "suggested_fee_max": suggested_fee_max,
        "scoring_profile": scoring_profile,
        "gst_data_source": "gst_api" if gst_api_requested else "manual",
        "gst_fetch_requested": gst_api_requested,
        "gst_api_request_id": str(form.get("gst_api_request_id") or ""),
        "gst_return_period_from": str(form.get("gst_return_period_from") or ""),
        "gst_return_period_to": str(form.get("gst_return_period_to") or ""),
        "gst_return_batch_id": str(form.get("gst_return_batch_id") or ""),
        "gst_return_periods": str(form.get("gst_return_periods") or ""),
        "gst_file_count": gst_count,
        "itr_file_count": itr_count,
        "banking_file_count": sum(1 for key, _ in deduped_entries if key == "banking"),
    }
    api_summary = _latest_gst_return_summary(db, client_id) if gst_api_requested else {}
    _merge_gst_return_summary(all_extracted, api_summary)
    detected_gstins: set[str] = set()
    prepared_files: list[tuple[str, str, bytes, str, dict]] = []

    for index, (key, upload) in enumerate(deduped_entries, start=1):
        content_bytes = await upload.read()
        filename = upload.filename or f"{key}_{index}.dat"
        validate_upload_bytes(content_bytes, filename)
        content_text = DataExtractor.content_to_text(content_bytes, filename)
        if key in {"gstr1", "gstr3b", "gstr2a"}:
            detected_gstins.update(_detect_gstins(filename, content_text))
        partial = DataExtractor.extract_all({key: content_text}, fy_year)
        prepared_files.append((key, filename, content_bytes, content_text, partial))

    client_gstin = _normalize_gstin(client.gstin)
    if len(detected_gstins) > 1:
        raise HTTPException(
            status_code=422,
            detail=f"Uploaded GST files contain multiple GSTINs: {', '.join(sorted(detected_gstins))}.",
        )
    if detected_gstins and not client_gstin:
        raise HTTPException(
            status_code=422,
            detail="Client GSTIN is required to verify GST uploads before report generation.",
        )
    if client_gstin and detected_gstins and client_gstin not in detected_gstins:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Uploaded GST files belong to GSTIN {', '.join(sorted(detected_gstins))}, "
                f"but selected client GSTIN is {client_gstin}. Select the correct client or update the client GSTIN."
            ),
        )

    for index, (key, filename, content_bytes, _content_text, partial) in enumerate(prepared_files, start=1):
        saved_path, stored_filename = _save_file(content_bytes, filename, client_id)
        fu = FileUpload(
            client_id=client_id,
            partner_id=partner_id,
            file_name=stored_filename,
            file_type=FILE_TYPE_MAP[key],
            file_path=saved_path,
            file_size=len(content_bytes),
            upload_method="manual_upload",
            processing_status="processed",
        )
        db.add(fu)
        db.flush()

        _merge_extracted(all_extracted, partial, key, index)
        _store_data_points(db, client_id, fu.id, partial, key)

    if api_summary:
        _store_api_data_points(db, client_id, api_summary)

    all_extracted["detected_gstins"] = sorted(detected_gstins)
    all_extracted["data_completeness_pct"] = DataExtractor._calculate_completeness(all_extracted)
    all_extracted["fy_year"] = fy_year

    hs = _run_pipeline(
        db,
        client,
        all_extracted,
        report_type,
        band,
        price,
        credits_required,
        suggested_fee_min,
        suggested_fee_max,
        branding_mode,
        scoring_profile,
    )
    db.commit()

    return ScoreCalculateResponse(
        health_score=hs.total_score,
        score_components=ScoreComponentsOut(
            gst_integrity_score=hs.gst_integrity_score,
            itr_consistency_score=hs.itr_consistency_score,
            compliance_behaviour_score=hs.compliance_behaviour_score,
            cashflow_health_score=hs.cashflow_health_score,
            data_credibility_score=hs.data_credibility_score,
            gst_itc_score=hs.gst_integrity_score,
            filing_score=hs.compliance_behaviour_score,
            cashflow_score=hs.cashflow_health_score,
            completeness_score=hs.data_credibility_score,
        ),
        score_breakdown={
            "GST Integrity": hs.gst_integrity_score or 0,
            "ITR Consistency": hs.itr_consistency_score or 0,
            "Cashflow Health": hs.cashflow_health_score or 0,
            "Compliance Behaviour": hs.compliance_behaviour_score or 0,
            "Data Credibility": hs.data_credibility_score or 0,
        },
        issues=hs.issues or [],
        advisory=hs.advisory or "",
        data_completeness_pct=hs.data_completeness_pct or 0,
        score_id=hs.id,
        report_number=hs.report_number,
        report_type=hs.report_type,
        report_variant=hs.report_variant,
        turnover_band=hs.turnover_band,
        client_size_band=hs.client_size_band,
        report_price=hs.report_price,
        credits_required=hs.credits_required,
        credits_used=hs.credits_used,
        suggested_fee_min=hs.suggested_fee_min,
        suggested_fee_max=hs.suggested_fee_max,
        scoring_version=hs.scoring_version,
        report_status=hs.report_status,
        report_url=f"/api/v1/reports/{hs.id}/download",
        download_url=f"/api/v1/reports/{hs.id}/download",
    )


@router.get("/{client_id}/uploads", response_model=List[FileUploadOut],
            summary="List all file uploads for a client")
def list_uploads(client_id: uuid.UUID, db: Session = Depends(get_db), current_partner: Partner = Depends(get_current_partner)):
    client = db.get(Client, client_id)
    if not client or client.partner_id != current_partner.id:
        raise HTTPException(status_code=404, detail="Client not found")

    return (
        db.query(FileUpload)
        .filter(FileUpload.client_id == client_id)
        .order_by(FileUpload.created_at.desc())
        .all()
    )
