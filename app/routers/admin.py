import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import Partner, Client, HealthScore, CreditTransaction
from app.schemas import (
    AdminStats, ScoreDistribution, ScoreDistributionItem,
    ClientListOut, AdminReportListOut, AdminReportItem,
    CreditsBalanceOut, CreditsAddRequest, CreditTransactionOut,
)

router = APIRouter(prefix="/api/admin", tags=["Admin Dashboard"])


@router.get("/stats", response_model=AdminStats, summary="Overall platform stats")
def get_stats(db: Session = Depends(get_db)):
    total_partners = db.query(func.count(Partner.id)).scalar() or 0
    total_clients = db.query(func.count(Client.id)).scalar() or 0
    total_reports = db.query(func.count(HealthScore.id)).scalar() or 0
    avg_row = db.query(func.avg(HealthScore.total_score)).scalar()
    avg_score = round(float(avg_row), 1) if avg_row else None

    return AdminStats(
        total_partners=total_partners,
        total_clients=total_clients,
        total_reports=total_reports,
        avg_health_score=avg_score,
    )


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
            partner_id=client.partner_id,
            partner_name=partner.name,
            total_score=hs.total_score,
            score_date=hs.score_date,
            advisory=hs.advisory,
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
        transaction_type="purchase",
        credits_amount=payload.amount,
        description=payload.description,
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
