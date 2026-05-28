import uuid
import base64
import hashlib
import os
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth_utils import get_current_partner
from app.database import get_db
from app.models import (
    Client,
    GSTAPIFetchLog,
    GSTAuthSession,
    GSTFetchBatch,
    GSTReturnNormalizedData,
    GSTReturnRawData,
    Partner,
)
from app.pricing_config import get_dashboard_package
from app.schemas import ClientBulkCreateOut, ClientBulkCreateRequest, ClientCreate, ClientUpdate, ClientOut, ClientListOut, ConsentRequestOut
from app.email_service import send_client_consent_email
from app.services.gst_return_api.auth import generate_auth_token, request_otp
from app.services.gst_return_api.client import mask_value
from app.services.gst_return_api.errors import GSTAPIConfigError
from app.services.gst_return_api.gstr1 import get_gstr1_b2b, get_gstr1_summary
from app.services.gst_return_api.gstr2b import get_gstr2b
from app.services.gst_return_api.gstr3b import get_gstr3b_auto_liability, get_gstr3b_summary
from app.services.gst_return_api.normalizers import normalize_gstr1, normalize_gstr2b, normalize_gstr3b

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


def _has_valid_consent(client: Client) -> bool:
    status_value = str(getattr(client, "consent_status", "") or "").lower()
    if status_value not in {"signed", "active", "approved", "accepted"}:
        return False
    expires_at = getattr(client, "consent_expires_at", None)
    return expires_at is None or expires_at >= datetime.utcnow()


def _normalize_gstin(value: object) -> str:
    return "".join(ch for ch in str(value or "").upper() if ch.isalnum())


def _token_key() -> bytes:
    secret = os.getenv("GST_TOKEN_SECRET") or os.getenv("JWT_SECRET") or "vertibis-local-gst-token-secret"
    return hashlib.sha256(secret.encode("utf-8")).digest()


def _protect_token(token: str) -> str:
    raw = token.encode("utf-8")
    key = _token_key()
    protected = bytes(byte ^ key[index % len(key)] for index, byte in enumerate(raw))
    return base64.urlsafe_b64encode(protected).decode("ascii")


def _unprotect_token(value: str) -> str:
    raw = base64.urlsafe_b64decode(value.encode("ascii"))
    key = _token_key()
    token = bytes(byte ^ key[index % len(key)] for index, byte in enumerate(raw))
    return token.decode("utf-8")


def _client_or_404(db: Session, client_id: uuid.UUID, partner: Partner) -> Client:
    client = db.get(Client, client_id)
    if not client or client.partner_id != partner.id:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


def _require_gst_fetch_ready(client: Client) -> None:
    if not _has_valid_consent(client):
        raise HTTPException(status_code=422, detail="Client consent is required before GST return data can be fetched.")
    if not client.gstin:
        raise HTTPException(status_code=422, detail="Client GSTIN is required before GST return data fetch.")


def _period_from_month(value: str) -> str:
    value = str(value or "").strip()
    if len(value) == 6 and value.isdigit():
        return value
    if len(value) >= 7 and value[4] == "-":
        year, month = value[:4], value[5:7]
        return f"{month}{year}"
    return value


def _month_range(start_period: str, end_period: str) -> list[str]:
    start = _period_from_month(start_period)
    end = _period_from_month(end_period)
    if len(start) != 6 or len(end) != 6:
        return [period for period in (start, end) if period]
    start_month, start_year = int(start[:2]), int(start[2:])
    end_month, end_year = int(end[:2]), int(end[2:])
    periods = []
    year, month = start_year, start_month
    while (year, month) <= (end_year, end_month):
        periods.append(f"{month:02d}{year}")
        month += 1
        if month == 13:
            month = 1
            year += 1
    return periods


def _periods_from_payload(payload: dict) -> list[str]:
    direct_periods = payload.get("periods")
    if isinstance(direct_periods, list):
        periods = [_period_from_month(str(period)) for period in direct_periods if period]
        if periods:
            return periods
    single = payload.get("ret_period") or payload.get("period")
    if single:
        return [_period_from_month(str(single))]
    return _month_range(str(payload.get("period_from") or ""), str(payload.get("period_to") or ""))


def _active_gst_session(db: Session, client: Client) -> GSTAuthSession | None:
    return (
        db.query(GSTAuthSession)
        .filter(
            GSTAuthSession.client_id == client.id,
            GSTAuthSession.status == "active",
            GSTAuthSession.auth_token_encrypted.isnot(None),
        )
        .order_by(GSTAuthSession.created_at.desc())
        .first()
    )


def _safe_return_types(value: object) -> list[str]:
    allowed = {"gstr1", "gstr3b", "gstr2b"}
    if isinstance(value, list):
        selected = [str(item).lower() for item in value if str(item).lower() in allowed]
        return selected or ["gstr1", "gstr3b", "gstr2b"]
    return ["gstr1", "gstr3b", "gstr2b"]


def _fetch_specs(return_type: str):
    if return_type == "gstr1":
        return [("RETSUM", get_gstr1_summary), ("B2B", get_gstr1_b2b)]
    if return_type == "gstr3b":
        return [("RETSUM", get_gstr3b_summary), ("AUTOLIAB", get_gstr3b_auto_liability)]
    if return_type == "gstr2b":
        return [("GET2B", get_gstr2b)]
    return []


def _normalize_return_payload(gstin: str, period: str, return_type: str, raw_sections: dict) -> dict:
    if return_type == "gstr1":
        return normalize_gstr1(gstin, period, raw_sections)
    if return_type == "gstr3b":
        return normalize_gstr3b(gstin, period, raw_sections)
    if return_type == "gstr2b":
        return normalize_gstr2b(gstin, period, raw_sections)
    return {}


@router.post("/{client_id}/gst/request-otp", summary="Request GST portal OTP for read-only return fetch")
def request_client_gst_otp(
    client_id: uuid.UUID,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    current_partner: Partner = Depends(get_current_partner),
):
    client = _client_or_404(db, client_id, current_partner)
    _require_gst_fetch_ready(client)
    payload = payload or {}
    gstin = _normalize_gstin(payload.get("gstin") or client.gstin)
    username = str(payload.get("username") or client.gst_username or "").strip()
    if not username:
        raise HTTPException(status_code=422, detail="GST portal username is required to request OTP.")

    if gstin != _normalize_gstin(client.gstin):
        raise HTTPException(status_code=422, detail=f"Requested GSTIN {mask_value(gstin, 3)} does not match selected client GSTIN.")

    try:
        result = request_otp(gstin, username)
    except GSTAPIConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    client.gst_username = username
    session = GSTAuthSession(
        client_id=client.id,
        partner_id=current_partner.id,
        gstin=gstin,
        gst_username=username,
        status="otp_requested" if result.success else "otp_failed",
    )
    db.add(session)
    db.commit()

    if not result.success:
        raise HTTPException(status_code=502, detail=result.error or "GST OTP request failed.")
    return {
        "status": "otp_requested",
        "message": "OTP requested on GST portal registered channel.",
        "gstin": mask_value(gstin, 3),
        "username": username,
        "session_id": str(session.id),
    }


@router.post("/{client_id}/gst/auth-token", summary="Generate GST API auth token using OTP")
def generate_client_gst_auth_token(
    client_id: uuid.UUID,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    current_partner: Partner = Depends(get_current_partner),
):
    client = _client_or_404(db, client_id, current_partner)
    _require_gst_fetch_ready(client)
    payload = payload or {}
    gstin = _normalize_gstin(payload.get("gstin") or client.gstin)
    username = str(payload.get("username") or client.gst_username or "").strip()
    otp = str(payload.get("otp") or "").strip()
    if not username:
        raise HTTPException(status_code=422, detail="GST portal username is required.")
    if not otp:
        raise HTTPException(status_code=422, detail="OTP is required.")
    if gstin != _normalize_gstin(client.gstin):
        raise HTTPException(status_code=422, detail=f"Requested GSTIN {mask_value(gstin, 3)} does not match selected client GSTIN.")

    try:
        result = generate_auth_token(gstin, username, otp)
    except GSTAPIConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    if not result.success:
        raise HTTPException(status_code=502, detail=result.error or "GST auth token generation failed.")

    authtoken = str((result.data or {}).get("authtoken") or "")
    if not authtoken:
        raise HTTPException(status_code=502, detail="GST API did not return an auth token. Please request OTP again.")

    db.query(GSTAuthSession).filter(GSTAuthSession.client_id == client.id, GSTAuthSession.status == "active").update({"status": "expired"})
    client.gst_username = username
    client.gstn_enabled = True
    client.gstn_last_fetch = datetime.utcnow()
    session = GSTAuthSession(
        client_id=client.id,
        partner_id=current_partner.id,
        gstin=gstin,
        gst_username=username,
        auth_token_encrypted=_protect_token(authtoken),
        status="active",
        expires_at=datetime.utcnow() + timedelta(hours=6),
    )
    db.add(session)
    db.commit()
    return {
        "status": "active",
        "message": "GST auth token generated. You can fetch returns now.",
        "gstin": mask_value(gstin, 3),
        "username": username,
        "session_id": str(session.id),
    }


@router.post("/{client_id}/gst/fetch", summary="Fetch read-only GST returns for report generation")
def fetch_client_gst_data(
    client_id: uuid.UUID,
    payload: dict | None = None,
    db: Session = Depends(get_db),
    current_partner: Partner = Depends(get_current_partner),
):
    client = _client_or_404(db, client_id, current_partner)
    _require_gst_fetch_ready(client)
    payload = payload or {}
    gstin = _normalize_gstin(payload.get("gstin") or client.gstin)
    if gstin != _normalize_gstin(client.gstin):
        raise HTTPException(status_code=422, detail=f"Requested GSTIN {mask_value(gstin, 3)} does not match selected client GSTIN.")

    session = _active_gst_session(db, client)
    if not session or not session.auth_token_encrypted:
        raise HTTPException(status_code=401, detail="GST session expired. Please request OTP again.")
    if session.expires_at and session.expires_at < datetime.utcnow():
        session.status = "expired"
        db.commit()
        raise HTTPException(status_code=401, detail="GST session expired. Please request OTP again.")

    username = str(payload.get("username") or session.gst_username or client.gst_username or "").strip()
    authtoken = _unprotect_token(session.auth_token_encrypted)
    periods = _periods_from_payload(payload)
    if not periods:
        raise HTTPException(status_code=422, detail="Select at least one GST return period.")

    return_types = _safe_return_types(payload.get("return_types"))
    cost_per_call = float(os.getenv("GST_API_COST_PER_CALL", "10") or 10)
    expected_calls = sum(len(_fetch_specs(return_type)) for return_type in return_types) * len(periods)
    now = datetime.utcnow()
    batch = GSTFetchBatch(
        client_id=client.id,
        partner_id=current_partner.id,
        financial_year=str(payload.get("fy_year") or ""),
        period_from=periods[0],
        period_to=periods[-1],
        fetch_mode=str(payload.get("fetch_mode") or ("single" if len(periods) == 1 else "batch")),
        total_periods=len(periods),
        total_api_calls=expected_calls,
        estimated_cost=expected_calls * cost_per_call,
        status="processing",
    )
    db.add(batch)
    db.flush()

    period_results: list[dict] = []
    successful_calls = 0
    failed_calls = 0
    normalized_count = 0

    for period in periods:
        period_status = {"period": period, "calls": [], "normalized": []}
        raw_by_type: dict[str, dict] = {}
        for return_type in return_types:
            raw_by_type.setdefault(return_type, {})
            for action, fetcher in _fetch_specs(return_type):
                result = fetcher(gstin, username, authtoken, period)
                if result.success:
                    successful_calls += 1
                    raw_by_type[return_type][action] = result.raw
                    db.add(GSTReturnRawData(
                        batch_id=batch.id,
                        client_id=client.id,
                        gstin=gstin,
                        period=period,
                        return_type=return_type,
                        action=action,
                        raw_json=result.raw if isinstance(result.raw, dict) else {"data": result.raw},
                        provider="charteredinfo_gst_return",
                    ))
                else:
                    failed_calls += 1
                db.add(GSTAPIFetchLog(
                    batch_id=batch.id,
                    client_id=client.id,
                    gstin=gstin,
                    gst_username=username,
                    return_type=return_type,
                    action=action,
                    period=period,
                    endpoint=result.endpoint,
                    success=result.success,
                    status_code=result.status_code,
                    error_message=result.error[:500] if result.error else None,
                    estimated_cost=cost_per_call,
                ))
                period_status["calls"].append({
                    "return_type": return_type,
                    "action": action,
                    "success": result.success,
                    "error": result.error,
                    "estimated_cost": cost_per_call,
                })

        for return_type, raw_sections in raw_by_type.items():
            if not raw_sections:
                continue
            normalized = _normalize_return_payload(gstin, period, return_type, raw_sections)
            if not normalized:
                continue
            normalized_count += 1
            db.add(GSTReturnNormalizedData(
                batch_id=batch.id,
                client_id=client.id,
                gstin=gstin,
                period=period,
                return_type=return_type,
                normalized_json=normalized,
            ))
            period_status["normalized"].append(return_type)
        period_results.append(period_status)

    batch.successful_calls = successful_calls
    batch.failed_calls = failed_calls
    batch.status = "completed" if failed_calls == 0 else ("partial" if successful_calls else "failed")
    batch.completed_at = datetime.utcnow()
    client.gstn_enabled = True
    client.gstn_last_fetch = now
    client.latest_data_date = now
    client.latest_data_source = "gst_return_api"
    client.data_source = "gst_return_api"

    db.commit()

    return {
        "status": batch.status,
        "message": "GST return data fetch completed. Vertibis uses this data for analysis only and does not file, save, or modify returns.",
        "request_id": str(batch.id),
        "batch_id": str(batch.id),
        "gstin": mask_value(gstin, 3),
        "periods": periods,
        "return_types": return_types,
        "fetched_at": now.isoformat(),
        "provider": "charteredinfo_gst_return",
        "records_fetched": normalized_count,
        "total_api_calls": expected_calls,
        "successful_calls": successful_calls,
        "failed_calls": failed_calls,
        "estimated_cost": batch.estimated_cost,
        "period_results": period_results,
        "client": {
            "id": str(client.id),
            "gstn_enabled": True,
            "latest_data_date": now.isoformat(),
            "latest_data_source": "gst_return_api",
            "data_source": "gst_return_api",
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
