import uuid
import os
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth_utils import get_current_partner
from app.database import get_db
from app.models import Client, GSTNSyncLog, Partner
from app.pricing_config import get_dashboard_package
from app.schemas import ClientBulkCreateOut, ClientBulkCreateRequest, ClientCreate, ClientUpdate, ClientOut, ClientListOut, ConsentRequestOut
from app.email_service import send_client_consent_email
from app.taxpro_ewb_client import TaxProEWBClient, TaxProEWBConfigError, TaxProEWBRemoteError

router = APIRouter(prefix="/api/v1/clients", tags=["Clients"])


def _client_limit(partner: Partner) -> int | None:
    if partner.client_limit_override is not None:
        return partner.client_limit_override
    return get_dashboard_package(partner.plan).client_limit


def _ensure_client_capacity(db: Session, partner: Partner, incoming: int = 1) -> None:
    limit = _client_limit(partner)
    if limit is None:
        return
    current_count = db.query(Client).filter(Client.partner_id == partner.id).count()
    if current_count + incoming > limit:
        raise HTTPException(
            status_code=402,
            detail=f"Client limit reached for {partner.plan} plan. Limit {limit}, current {current_count}. Upgrade plan or ask admin to increase limit.",
        )


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED,
             summary="Create a new MSME client")
def create_client(payload: ClientCreate, db: Session = Depends(get_db), current_partner: Partner = Depends(get_current_partner)):
    _ensure_client_capacity(db, current_partner)
    client = Client(**payload.model_dump(), partner_id=current_partner.id)
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
    current_partner: Partner = Depends(get_current_partner),
):
    q = db.query(Client).filter(Client.partner_id == current_partner.id)
    if industry:
        q = q.filter(Client.industry == industry)

    total = q.count()
    items = q.order_by(Client.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
    return ClientListOut(total=total, page=page, per_page=per_page, items=items)


@router.get("/{client_id}", response_model=ClientOut, summary="Get a client by ID")
def get_client(client_id: uuid.UUID, db: Session = Depends(get_db), current_partner: Partner = Depends(get_current_partner)):
    client = db.get(Client, client_id)
    if not client or client.partner_id != current_partner.id:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.put("/{client_id}", response_model=ClientOut, summary="Update a client")
def update_client(
    client_id: uuid.UUID,
    payload: ClientUpdate,
    db: Session = Depends(get_db),
    current_partner: Partner = Depends(get_current_partner),
):
    client = db.get(Client, client_id)
    if not client or client.partner_id != current_partner.id:
        raise HTTPException(status_code=404, detail="Client not found")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(client, field, value)

    db.commit()
    db.refresh(client)
    return client


@router.post("/{client_id}/gst/fetch", summary="Record GST API test fetch for report generation")
def fetch_client_gst_data(
    client_id: uuid.UUID,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    current_partner: Partner = Depends(get_current_partner),
):
    client = db.get(Client, client_id)
    if not client or client.partner_id != current_partner.id:
        raise HTTPException(status_code=404, detail="Client not found")
    if not client.gstin:
        raise HTTPException(status_code=422, detail="Client GSTIN is required before GST API fetch")

    payload = payload or {}
    requested_gstin = str(payload.get("gstin") or "").strip().upper()
    client_gstin = str(client.gstin or "").strip().upper()
    if requested_gstin and requested_gstin != client_gstin:
        raise HTTPException(
            status_code=422,
            detail=f"Requested GSTIN {requested_gstin} does not match client GSTIN {client_gstin}",
        )

    now = datetime.utcnow()
    request_id = str(
        payload.get("request_id")
        or f"GSTAPI-{now.strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(3).upper()}"
    )
    period_from = str(payload.get("period_from") or "")
    period_to = str(payload.get("period_to") or "")
    fy_year = str(payload.get("fy_year") or "")
    test_date = str(payload.get("test_date") or payload.get("ewb_date") or "")

    taxpro_client = TaxProEWBClient()
    remote_result = {
        "provider": "taxpro_charteredinfo",
        "mode": taxpro_client.mode,
        "remote_status": "not_enabled",
        "summary": {
            "ewb_document_count": 0,
            "ewb_active_count": 0,
            "ewb_cancelled_count": 0,
            "ewb_rejected_count": 0,
            "ewb_total_invoice_value": 0,
            "ewb_taxable_value": 0,
        },
        "message": "TaxPro EWB remote fetch is not enabled. Set TAXPRO_EWB_REMOTE_ENABLED=true after adding ASP credentials.",
    }
    if taxpro_client.is_remote_enabled():
        try:
            remote_result = taxpro_client.fetch_report_signal(client_gstin, test_date or None)
        except TaxProEWBConfigError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        except TaxProEWBRemoteError as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    client.gstn_enabled = True
    client.gstn_last_fetch = now
    client.latest_data_date = now
    client.latest_data_source = "taxpro_ewb_api"
    client.data_source = "taxpro_ewb_api"

    summary = remote_result.get("summary") if isinstance(remote_result, dict) else {}
    records_fetched = int((summary or {}).get("ewb_document_count") or 0)
    db.add(GSTNSyncLog(
        client_id=client.id,
        partner_id=current_partner.id,
        sync_type="taxpro_ewb_report_signal",
        gstr_type="ewaybill",
        response_status=str(remote_result.get("remote_status") or "recorded"),
        records_fetched=records_fetched,
        records_processed=records_fetched,
        records_failed=0,
        error_details={
            "request_id": request_id,
            "period_from": period_from,
            "period_to": period_to,
            "fy_year": fy_year,
            "test_date": test_date,
            "source": payload.get("source") or "partner_report_generation",
            "provider": remote_result.get("provider"),
            "mode": remote_result.get("mode"),
            "server": remote_result.get("data_server") or remote_result.get("auth_server"),
            "summary": summary or {},
        },
    ))

    db.commit()

    return {
        "status": "fetched",
        "message": remote_result.get("message") or "TaxPro EWB/GST signal fetched. Upload ITR/banking files to generate the report preview.",
        "request_id": request_id,
        "gstin": client_gstin,
        "period_from": period_from,
        "period_to": period_to,
        "fy_year": fy_year,
        "test_date": test_date,
        "fetched_at": now.isoformat(),
        "provider": remote_result.get("provider"),
        "mode": remote_result.get("mode"),
        "remote_status": remote_result.get("remote_status"),
        "server": remote_result.get("data_server") or remote_result.get("auth_server"),
        "records_fetched": records_fetched,
        "summary": summary or {},
        "client": {
            "id": str(client.id),
            "gstn_enabled": True,
            "latest_data_date": now.isoformat(),
            "latest_data_source": "taxpro_ewb_api",
            "data_source": "taxpro_ewb_api",
        },
    }

@router.post("/bulk", response_model=ClientBulkCreateOut, status_code=status.HTTP_201_CREATED,
             summary="Create multiple MSME clients")
def bulk_create_clients(payload: ClientBulkCreateRequest, db: Session = Depends(get_db), current_partner: Partner = Depends(get_current_partner)):
    _ensure_client_capacity(db, current_partner, len(payload.clients))
    created: list[Client] = []
    failed: list[dict] = []

    for index, item in enumerate(payload.clients, start=1):
        try:
            client = Client(**item.model_dump(), partner_id=current_partner.id)
            db.add(client)
            db.flush()
            created.append(client)
        except Exception as exc:
            db.rollback()
            failed.append({"row": index, "name": item.name, "error": str(exc)})

    db.commit()
    for client in created:
        db.refresh(client)

    return ClientBulkCreateOut(created=created, failed=failed)


def _consent_url(token: str) -> str:
    base = (
        os.getenv("CLIENT_CONSENT_BASE_URL")
        or os.getenv("FRONTEND_CONSENT_URL")
        or os.getenv("API_PUBLIC_BASE_URL")
        or ""
    ).rstrip("/")
    if base:
        return f"{base}/consent/{token}"
    return f"/api/v1/clients/consent/accept/{token}"


def _whatsapp_url(phone: str | None, message: str) -> str | None:
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 10:
        digits = f"91{digits}"
    if not digits:
        return None
    from urllib.parse import quote
    return f"https://wa.me/{digits}?text={quote(message)}"


@router.post("/{client_id}/consent/request", response_model=ConsentRequestOut, summary="Create WhatsApp client consent request")
def request_client_consent(
    client_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_partner: Partner = Depends(get_current_partner),
):
    client = db.get(Client, client_id)
    if not client or client.partner_id != current_partner.id:
        raise HTTPException(status_code=404, detail="Client not found")
    if not client.phone and not client.email:
        raise HTTPException(status_code=422, detail="Client phone or email is required to send consent request")

    token = secrets.token_urlsafe(32)
    consent_url = _consent_url(token)
    whatsapp_message = (
        f"Hello {client.name}, {current_partner.name} requests your consent to process GST, ITR, "
        f"and banking data for your Vertibis MSME Business Health Report. Please approve here: {consent_url}"
    )
    client.consent_token = token
    client.consent_status = "requested"
    client.consent_requested_at = datetime.utcnow()
    client.consent_signed_at = None
    client.consent_expires_at = None
    db.commit()
    db.refresh(client)

    email_queued = False
    if client.email:
        background_tasks.add_task(send_client_consent_email, client, current_partner, consent_url)
        email_queued = True

    return ConsentRequestOut(
        client=client,
        consent_url=consent_url,
        whatsapp_url=_whatsapp_url(client.phone, whatsapp_message),
        whatsapp_message=whatsapp_message,
        email_queued=email_queued,
    )


@router.post("/{client_id}/consent/sign", response_model=ClientOut, summary="Record signed client consent")
def sign_client_consent(
    client_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_partner: Partner = Depends(get_current_partner),
):
    client = db.get(Client, client_id)
    if not client or client.partner_id != current_partner.id:
        raise HTTPException(status_code=404, detail="Client not found")

    client.consent_status = "signed"
    client.consent_token = None
    client.consent_signed_at = datetime.utcnow()
    client.consent_expires_at = datetime.utcnow() + timedelta(days=365)
    db.commit()
    db.refresh(client)
    return client


@router.get("/consent/accept/{token}", summary="Accept client consent from email link")
@router.post("/consent/accept/{token}", summary="Accept client consent from email link")
def accept_client_consent(token: str, db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.consent_token == token).first()
    if not client:
        raise HTTPException(status_code=404, detail="Consent link is invalid or already used")

    client.consent_status = "signed"
    client.consent_token = None
    client.consent_signed_at = datetime.utcnow()
    client.consent_expires_at = datetime.utcnow() + timedelta(days=365)
    db.commit()

    return {
        "message": "Consent accepted successfully",
        "client_id": str(client.id),
        "client_name": client.name,
        "expires_at": client.consent_expires_at,
    }
