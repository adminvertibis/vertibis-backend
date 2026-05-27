import uuid
import os
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.auth_utils import require_admin
from app.database import get_db
from app.models import Partner, Client, HealthScore, CreditTransaction
from app.pricing_config import serialize_pricing_config
from app.schemas import (
    AdminStats, ScoreDistribution, ScoreDistributionItem,
    ClientListOut, AdminReportListOut, AdminReportItem,
    CreditsBalanceOut, CreditsAddRequest, CreditTransactionOut,
)

router = APIRouter(prefix="/api/admin", tags=["Admin Dashboard"], dependencies=[Depends(require_admin)])


@router.get("/stats", response_model=AdminStats, summary="Overall platform stats")
def get_stats(db: Session = Depends(get_db)):
    total_partners = db.query(func.count(Partner.id)).scalar() or 0
    active_partners = db.query(func.count(Partner.id)).filter(Partner.status == "active").scalar() or 0
    pending_approvals = db.query(func.count(Partner.id)).filter(Partner.status == "pending").scalar() or 0
    total_clients = db.query(func.count(Client.id)).scalar() or 0
    total_reports = db.query(func.count(HealthScore.id)).scalar() or 0
    avg_row = db.query(func.avg(HealthScore.total_score)).scalar()
    avg_score = round(float(avg_row), 1) if avg_row else None
    at_risk_clients = (
        db.query(func.count(HealthScore.id))
        .filter(HealthScore.total_score < 50)
        .scalar() or 0
    )
    credits_remaining = db.query(func.coalesce(func.sum(Partner.credits_balance), 0)).scalar() or 0
    credits_used = (
        db.query(func.coalesce(func.sum(CreditTransaction.credits_amount), 0))
        .filter(CreditTransaction.credits_amount < 0)
        .scalar() or 0
    )

    return AdminStats(
        total_partners=total_partners,
        active_partners=active_partners,
        pending_approvals=pending_approvals,
        total_clients=total_clients,
        total_reports=total_reports,
        avg_health_score=avg_score,
        average_score=avg_score,
        at_risk_clients=at_risk_clients,
        credits_remaining=int(credits_remaining),
        credits_used=abs(int(credits_used)),
    )


@router.get("/users", summary="Admin users visible to the admin panel")
def list_admin_users():
    return [
        {
            "id": "admin",
            "name": "Vertibis Admin",
            "email": os.getenv("ADMIN_EMAIL", "admin@vertibis.in"),
            "role": "admin",
        }
    ]


@router.get("/clients", response_model=ClientListOut,
            summary="All clients across all partners (paginated)")
def list_all_clients(
    partner_id: uuid.UUID = None,
    industry: str = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = db.query(Client)
    if partner_id:
        q = q.filter(Client.partner_id == partner_id)
    if industry:
        q = q.filter(Client.industry == industry)

    total = q.count()
    items = q.order_by(Client.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return ClientListOut(total=total, page=page, per_page=per_page, items=items)


@router.get("/reports", response_model=AdminReportListOut,
            summary="All health score reports across all clients (paginated)")
def list_all_reports(
    partner_id: uuid.UUID = None,
    min_score: float = None,
    max_score: float = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    q = (
        db.query(HealthScore, Client, Partner)
        .join(Client, HealthScore.client_id == Client.id)
        .join(Partner, Client.partner_id == Partner.id)
    )
    if partner_id:
        q = q.filter(Partner.id == partner_id)
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
            partner_name=partner.name,
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
        for hs, client, partner in rows
    ]

    return AdminReportListOut(total=total, page=page, per_page=per_page, items=items)


@router.get("/scores/distribution", response_model=ScoreDistribution,
            summary="Score distribution for dashboard charts")
def score_distribution(db: Session = Depends(get_db)):
    bands = [
        ("0-20", 0, 20),
        ("21-40", 21, 40),
        ("41-60", 41, 60),
        ("61-80", 61, 80),
        ("81-100", 81, 100),
    ]
    distribution = []
    for label, low, high in bands:
        count = (
            db.query(func.count(HealthScore.id))
            .filter(HealthScore.total_score >= low, HealthScore.total_score <= high)
            .scalar() or 0
        )
        distribution.append(ScoreDistributionItem(range=label, count=count))

    return ScoreDistribution(distribution=distribution)


@router.get("/payments", summary="Credit transactions for admin revenue screens")
def list_payments(db: Session = Depends(get_db)):
    rows = (
        db.query(CreditTransaction, Partner)
        .join(Partner, CreditTransaction.partner_id == Partner.id)
        .order_by(CreditTransaction.timestamp.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": str(tx.id),
            "caId": str(partner.id),
            "caName": partner.name,
            "type": tx.transaction_type or ("credit_purchase" if tx.credits_amount > 0 else "report_unlock"),
            "amount": 0,
            "credits": tx.credits_amount,
            "balanceAfter": tx.balance_after,
            "date": tx.timestamp,
            "status": tx.status,
            "method": "credits",
            "remarks": tx.remarks or tx.description,
        }
        for tx, partner in rows
    ]


@router.get("/pricing-config", summary="Default pricing and entitlement config adapter")
def pricing_config():
    return serialize_pricing_config()


@router.get("/credit-ledger", summary="Credit ledger across all partners")
def credit_ledger(db: Session = Depends(get_db)):
    rows = (
        db.query(CreditTransaction, Partner)
        .join(Partner, CreditTransaction.partner_id == Partner.id)
        .order_by(CreditTransaction.timestamp.desc())
        .limit(500)
        .all()
    )
    return [
        {
            "transaction_id": str(tx.id),
            "partner_id": str(partner.id),
            "partner_name": partner.name,
            "transaction_type": tx.transaction_type,
            "credits": tx.credits_amount,
            "balance_after": tx.balance_after,
            "related_report_id": str(tx.related_health_score_id) if tx.related_health_score_id else None,
            "related_client_id": str(tx.related_client_id) if tx.related_client_id else None,
            "remarks": tx.remarks or tx.description,
            "created_by": tx.created_by,
            "created_at": tx.timestamp,
        }
        for tx, partner in rows
    ]


@router.get("/report-unlocks", summary="Report unlock history")
def report_unlocks(db: Session = Depends(get_db)):
    rows = (
        db.query(HealthScore, Client, Partner)
        .join(Client, HealthScore.client_id == Client.id)
        .join(Partner, Client.partner_id == Partner.id)
        .filter(HealthScore.credits_used > 0)
        .order_by(HealthScore.unlocked_at.desc().nullslast(), HealthScore.updated_at.desc())
        .limit(500)
        .all()
    )
    return [
        {
            "partner": partner.name,
            "partner_id": str(partner.id),
            "client": client.name,
            "client_id": str(client.id),
            "client_size": hs.client_size_band or hs.turnover_band,
            "report_type": hs.report_variant or hs.report_type,
            "report_id": str(hs.id),
            "credits_consumed": hs.credits_used,
            "unlocked_by": str(partner.id),
            "unlocked_at": hs.unlocked_at,
            "downloaded_at": hs.downloaded_at,
            "shared_at": hs.shared_at,
            "suggested_fee_min": hs.suggested_fee_min,
            "suggested_fee_max": hs.suggested_fee_max,
            "status": hs.report_status,
        }
        for hs, client, partner in rows
    ]


@router.get("/website-leads", summary="Website leads placeholder until CRM integration is enabled")
def list_website_leads():
    return []


@router.get("/partners/{partner_id}/credits", response_model=CreditsBalanceOut,
            summary="Get credit balance and transaction history for a partner")
def get_credits(
    partner_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    partner = db.get(Partner, partner_id)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")

    transactions = (
        db.query(CreditTransaction)
        .filter(CreditTransaction.partner_id == partner_id)
        .order_by(CreditTransaction.timestamp.desc())
        .limit(limit)
        .all()
    )

    return CreditsBalanceOut(
        partner_id=partner_id,
        credits_balance=partner.credits_balance,
        transactions=transactions,
    )


@router.post("/partners/{partner_id}/credits/add", response_model=CreditsBalanceOut,
             summary="Add credits to a partner account")
def add_credits(
    partner_id: uuid.UUID,
    payload: CreditsAddRequest,
    db: Session = Depends(get_db),
):
    partner = db.get(Partner, partner_id)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")

    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    partner.credits_balance += payload.amount
    tx = CreditTransaction(
        partner_id=partner_id,
        transaction_type="admin_adjustment",
        credits_amount=payload.amount,
        balance_after=partner.credits_balance,
        description=payload.description,
        remarks=payload.description,
        created_by="admin",
        status="completed",
    )
    db.add(tx)
    db.commit()
    db.refresh(partner)

    recent_txs = (
        db.query(CreditTransaction)
        .filter(CreditTransaction.partner_id == partner_id)
        .order_by(CreditTransaction.timestamp.desc())
        .limit(20)
        .all()
    )

    return CreditsBalanceOut(
        partner_id=partner_id,
        credits_balance=partner.credits_balance,
        transactions=recent_txs,
    )
