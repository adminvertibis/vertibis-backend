import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Client, HealthScore, DataPoint
from app.schemas import HealthScoreOut, ScoreCalculateResponse, ScoreComponentsOut
from app.scoring_engine import ScoringEngine
from app.advisory_generator import AdvisoryGenerator

router = APIRouter(prefix="/api/v1/clients", tags=["Health Scores"])


def _reconstruct_extracted(db: Session, client_id: uuid.UUID) -> dict:
    """Rebuild the extracted_data dict from stored DataPoint rows."""
    rows = db.query(DataPoint).filter(DataPoint.client_id == client_id).all()
    result: dict = {}
    for dp in rows:
        if dp.data_date is not None and dp.data_value is None:
            result[dp.data_type] = dp.data_date
        elif dp.data_value is not None:
            result[dp.data_type] = dp.data_value
        elif dp.data_value_str is not None:
            result[dp.data_type] = dp.data_value_str
    return result


@router.post("/{client_id}/score", response_model=ScoreCalculateResponse,
             status_code=status.HTTP_201_CREATED,
             summary="Recalculate health score from stored data points")
def calculate_score(client_id: uuid.UUID, db: Session = Depends(get_db)):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    extracted = _reconstruct_extracted(db, client_id)
    if not extracted:
        raise HTTPException(
            status_code=422,
            detail="No data found for this client. Upload files first."
        )

    industry = client.industry or "trading"
    turnover = client.turnover or extracted.get("gstr1_total_sales", 1_000_000)

    scores = ScoringEngine.calculate_score(extracted, industry, turnover)
    advisory = AdvisoryGenerator.generate_advisory(extracted, scores, industry, client.name)

    components = scores.get("components", {})
    hs = HealthScore(
        client_id=client_id,
        total_score=scores["total_score"],
        gst_integrity_score=components.get("gst_itc_score"),
        compliance_behaviour_score=components.get("filing_score"),
        cashflow_health_score=components.get("cashflow_score"),
        data_credibility_score=components.get("completeness_score"),
        issues=scores.get("issues", []),
        advisory=advisory,
        data_completeness_pct=extracted.get("data_completeness_pct"),
        gst_data_source="manual",
    )
    db.add(hs)
    db.commit()
    db.refresh(hs)

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


@router.get("/{client_id}/scores", response_model=List[HealthScoreOut],
            summary="List all scores for a client")
def list_scores(client_id: uuid.UUID, db: Session = Depends(get_db)):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    return (
        db.query(HealthScore)
        .filter(HealthScore.client_id == client_id)
        .order_by(HealthScore.score_date.desc())
        .all()
    )


@router.get("/{client_id}/score/latest", response_model=HealthScoreOut,
            summary="Get the latest health score for a client")
def get_latest_score(client_id: uuid.UUID, db: Session = Depends(get_db)):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    hs = (
        db.query(HealthScore)
        .filter(HealthScore.client_id == client_id)
        .order_by(HealthScore.score_date.desc())
        .first()
    )
    if not hs:
        raise HTTPException(status_code=404, detail="No scores found for this client")
    return hs
