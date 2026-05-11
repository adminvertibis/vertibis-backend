import uuid
import os
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Client, FileUpload, DataPoint, HealthScore, Partner, CreditTransaction
from app.schemas import FileUploadOut, ScoreCalculateResponse, ScoreComponentsOut
from app.extractors import DataExtractor
from app.scoring_engine import ScoringEngine
from app.advisory_generator import AdvisoryGenerator

router = APIRouter(prefix="/api/v1/clients", tags=["File Uploads"])

UPLOAD_DIR = os.getenv("UPLOAD_DIR", "uploads")

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


def _save_file(content: bytes, filename: str, client_id: uuid.UUID) -> str:
    client_dir = os.path.join(UPLOAD_DIR, str(client_id))
    os.makedirs(client_dir, exist_ok=True)
    path = os.path.join(client_dir, filename)
    with open(path, "wb") as f:
        f.write(content)
    return path


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


def _run_pipeline(db: Session, client: Client, all_extracted: dict) -> HealthScore:
    industry = client.industry or "trading"
    turnover = client.turnover or all_extracted.get("gstr1_total_sales", 1_000_000)

    scores = ScoringEngine.calculate_score(all_extracted, industry, turnover)
    advisory = AdvisoryGenerator.generate_advisory(all_extracted, scores, industry, client.name)

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
        data_completeness_pct=all_extracted.get("data_completeness_pct"),
        gst_data_source="manual",
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
    partner_id: uuid.UUID = Form(...),
    fy_year: str = Form("2024-25"),
    gstr1: Optional[UploadFile] = File(None),
    gstr3b: Optional[UploadFile] = File(None),
    gstr2a: Optional[UploadFile] = File(None),
    itr: Optional[UploadFile] = File(None),
    banking: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    partner = db.get(Partner, partner_id)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")

    if partner.credits_balance < 1:
        raise HTTPException(status_code=402, detail="Insufficient credits")

    upload_inputs = {"gstr1": gstr1, "gstr3b": gstr3b, "gstr2a": gstr2a, "itr": itr, "banking": banking}
    files_dict: dict = {}
    file_upload_ids: dict = {}

    for key, upload in upload_inputs.items():
        if upload is None:
            continue
        content_bytes = await upload.read()
        files_dict[key] = content_bytes.decode("utf-8", errors="replace")

        saved_path = _save_file(content_bytes, upload.filename or f"{key}.dat", client_id)
        fu = FileUpload(
            client_id=client_id,
            partner_id=partner_id,
            file_name=upload.filename or f"{key}.dat",
            file_type=FILE_TYPE_MAP[key],
            file_path=saved_path,
            file_size=len(content_bytes),
            upload_method="manual_upload",
            processing_status="processed",
        )
        db.add(fu)
        db.flush()
        file_upload_ids[key] = fu.id

    if not files_dict:
        raise HTTPException(status_code=400, detail="No files provided")

    all_extracted = DataExtractor.extract_all(files_dict, fy_year)

    for key in files_dict:
        partial = DataExtractor.extract_all({key: files_dict[key]}, fy_year)
        _store_data_points(db, client_id, file_upload_ids[key], partial, key)

    # Deduct 1 credit and log the transaction
    partner.credits_balance -= 1
    tx = CreditTransaction(
        partner_id=partner_id,
        transaction_type="usage",
        credits_amount=-1,
        related_client_id=client_id,
        description=f"Health score for {client.name}",
    )
    db.add(tx)

    hs = _run_pipeline(db, client, all_extracted)
    tx.related_health_score_id = hs.id
    db.commit()

    return ScoreCalculateResponse(
        health_score=hs.total_score,
        score_components=ScoreComponentsOut(
            gst_itc_score=hs.gst_integrity_score,
            filing_score=hs.compliance_behaviour_score,
            cashflow_score=hs.cashflow_health_score,
            completeness_score=hs.data_credibility_score,
        ),
        issues=hs.issues or [],
        advisory=hs.advisory or "",
        data_completeness_pct=hs.data_completeness_pct or 0,
        score_id=hs.id,
    )


@router.get("/{client_id}/uploads", response_model=List[FileUploadOut],
            summary="List all file uploads for a client")
def list_uploads(client_id: uuid.UUID, db: Session = Depends(get_db)):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    return (
        db.query(FileUpload)
        .filter(FileUpload.client_id == client_id)
        .order_by(FileUpload.created_at.desc())
        .all()
    )
