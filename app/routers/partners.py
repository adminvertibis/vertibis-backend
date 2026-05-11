import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Partner
from app.schemas import PartnerCreate, PartnerUpdate, PartnerOut

router = APIRouter(prefix="/api/admin/partners", tags=["Partners"])


@router.post("", response_model=PartnerOut, status_code=status.HTTP_201_CREATED,
             summary="Create a new CA/CS partner")
def create_partner(payload: PartnerCreate, db: Session = Depends(get_db)):
    existing = db.query(Partner).filter(Partner.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    partner = Partner(**payload.model_dump())
    db.add(partner)
    db.commit()
    db.refresh(partner)
    return partner


@router.get("", response_model=List[PartnerOut], summary="List all partners")
def list_partners(
    status: str = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    q = db.query(Partner)
    if status:
        q = q.filter(Partner.status == status)
    return q.order_by(Partner.created_at.desc()).offset(skip).limit(limit).all()


@router.get("/{partner_id}", response_model=PartnerOut, summary="Get a partner by ID")
def get_partner(partner_id: uuid.UUID, db: Session = Depends(get_db)):
    partner = db.get(Partner, partner_id)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")
    return partner


@router.put("/{partner_id}", response_model=PartnerOut, summary="Update a partner")
def update_partner(
    partner_id: uuid.UUID,
    payload: PartnerUpdate,
    db: Session = Depends(get_db),
):
    partner = db.get(Partner, partner_id)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(partner, field, value)

    db.commit()
    db.refresh(partner)
    return partner
