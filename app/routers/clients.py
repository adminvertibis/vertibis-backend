import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Client, Partner
from app.schemas import ClientCreate, ClientUpdate, ClientOut, ClientListOut

router = APIRouter(prefix="/api/v1/clients", tags=["Clients"])


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED,
             summary="Create a new MSME client")
def create_client(payload: ClientCreate, db: Session = Depends(get_db)):
    partner = db.get(Partner, payload.partner_id)
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")

    client = Client(**payload.model_dump())
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@router.get("", response_model=ClientListOut, summary="List clients (paginated)")
def list_clients(
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


@router.get("/{client_id}", response_model=ClientOut, summary="Get a client by ID")
def get_client(client_id: uuid.UUID, db: Session = Depends(get_db)):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.put("/{client_id}", response_model=ClientOut, summary="Update a client")
def update_client(
    client_id: uuid.UUID,
    payload: ClientUpdate,
    db: Session = Depends(get_db),
):
    client = db.get(Client, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, field, value)

    db.commit()
    db.refresh(client)
    return client
