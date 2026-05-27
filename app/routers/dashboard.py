from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth_utils import get_current_partner
from app.database import get_db
from app.models import Client, HealthScore, Partner, CreditTransaction
from app.schemas import AdminReportItem, AdminReportListOut, AdminStats

router = APIRouter(prefix="/api/v1/dashboard", tags=["Partner Dashboard"])


@router.get("/stats", response_model=AdminStats, summary="Partner-scoped dashboard stats")
def get_partner_stats(
    db: Session = Depends(get_db),
    current_partner: Partner = Depends(get_current_partner),
):
    total_clients = db.query(func.count(Client.id)).filter(Client.partner_id == current_partner.id).scalar() or 0
    score_query = db.query(HealthScore).join(Client, HealthScore.client_id == Client.id).filter(Client.partner_id == current_partner.id)
    total_reports = score_query.count()
    avg_row = db.query(func.avg(HealthScore.total_score)).join(Client, HealthScore.client_id == Client.id).filter(Client.partner_id == current_partner.id).scalar()
    avg_score = round(float(avg_row), 1) if avg_row else None
    at_risk_clients = score_query.filter(HealthScore.total_score < 50).count()
    credits_used = (
        db.query(func.coalesce(func.sum(CreditTransaction.credits_amount), 0))
        .filter(CreditTransaction.partner_id == current_partner.id, CreditTransaction.credits_amount < 0)
        .scalar() or 0
    )

    return AdminStats(
        total_partners=1,
        active_partners=1,
        total_clients=total_clients,
        total_reports=total_reports,
        avg_health_score=avg_score,
        average_score=avg_score,
        at_risk_clients=at_risk_clients,
        credits_remaining=current_partner.credits_balance,
        credits_used=abs(int(credits_used)),
    )


@router.get("/reports", response_model=AdminReportListOut, summary="Partner-scoped report list")
def list_partner_reports(
    min_score: float = None,
    max_score: float = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_partner: Partner = Depends(get_current_partner),
):
    q = (
        db.query(HealthScore, Client)
        .join(Client, HealthScore.client_id == Client.id)
        .filter(Client.partner_id == current_partner.id)
    )
    if min_score is not None:
        q = q.filter(HealthScore.total_score >= min_score)
    if max_score is not None:
        q = q.filter(HealthScore.total_score <= max_score)

    total = q.count()
    rows = q.order_by(HealthScore.score_date.desc()).offset((page - 1) * per_page).limit(per_page).all()
    items = [
        AdminReportItem(
            id=hs.id,
            client_id=hs.client_id,
            client_name=client.name,
            gstin=client.gstin,
            partner_id=client.partner_id,
            partner_name=current_partner.name,
            total_score=hs.total_score,
            health_score=hs.total_score,
            score_date=hs.score_date,
            generated_at=hs.score_date,
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
            advisory=hs.advisory,
            issues=hs.issues or [],
            report_url=f"/api/v1/reports/{hs.id}/download",
            download_url=f"/api/v1/reports/{hs.id}/download",
        )
        for hs, client in rows
    ]
    return AdminReportListOut(total=total, page=page, per_page=per_page, items=items, reports=items)
