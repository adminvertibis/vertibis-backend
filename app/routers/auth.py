import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth_utils import get_jwt_secret
from app.database import get_db
from app.email_service import send_partner_registration_emails
from app.models import Partner
from app.schemas import AuthResponse, AuthUserOut, LoginRequest, PartnerRegisterRequest, RegisterPendingResponse

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 150_000)
    return f"pbkdf2_sha256$150000${salt}${digest.hex()}"


def _verify_password(password: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False

    try:
        algorithm, iterations, salt, expected = stored_hash.split("$", 3)
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations))
    return hmac.compare_digest(digest.hex(), expected)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _create_role_token(sub: str, email: str, role: str, expires_hours: int, extra: dict | None = None) -> str:
    secret = get_jwt_secret()
    now = datetime.utcnow()
    expires = now + timedelta(hours=expires_hours)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": sub,
        "email": email,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
    }
    if extra:
        payload.update(extra)

    signing_input = f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}.{_b64url(json.dumps(payload, separators=(',', ':')).encode())}"
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(signature)}"


def _create_access_token(partner: Partner) -> str:
    return _create_role_token(
        sub=str(partner.id),
        email=partner.email,
        role=partner.role or "ca_partner",
        expires_hours=int(os.getenv("JWT_EXPIRE_HOURS", "24")),
    )


def _auth_response(partner: Partner) -> AuthResponse:
    return AuthResponse(
        access_token=_create_access_token(partner),
        user=AuthUserOut(
            id=str(partner.id),
            name=partner.contact_name or partner.name,
            email=partner.email,
            role=partner.role or "ca_partner",
            firm_name=partner.name,
            profession=partner.profession or partner.firm_type,
            phone=partner.phone,
            membership_no=partner.membership_no,
        ),
    )


def _admin_auth_response(payload: LoginRequest) -> AuthResponse | None:
    admin_email = os.getenv("ADMIN_EMAIL", "admin@vertibis.in").lower()
    if payload.email.lower() != admin_email:
        return None

    admin_password = os.getenv("ADMIN_PASSWORD")
    if not admin_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin credentials are not configured",
        )

    if not hmac.compare_digest(payload.password, admin_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    return AuthResponse(
        access_token=_create_role_token(
            sub="admin",
            email=admin_email,
            role="admin",
            expires_hours=int(os.getenv("ADMIN_JWT_EXPIRE_HOURS", "8")),
            extra={"aud": "vertibis-admin"},
        ),
        user=AuthUserOut(
            id="admin",
            name="Vertibis Admin",
            email=admin_email,
            role="admin",
            firm_name="Vertibis",
        ),
    )


@router.post("/register", response_model=RegisterPendingResponse, status_code=status.HTTP_201_CREATED)
def register_partner(payload: PartnerRegisterRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if payload.role and payload.role != "ca_partner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized partner access")

    existing = db.query(Partner).filter(Partner.email == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    partner = Partner(
        name=payload.firm_name,
        contact_name=payload.name,
        email=payload.email.lower(),
        phone=payload.phone,
        firm_type=payload.profession,
        profession=payload.profession,
        membership_no=payload.membership_no,
        password_hash=_hash_password(payload.password),
        role="ca_partner",
        credits_balance=50,
        status="pending",
    )
    db.add(partner)
    db.commit()
    db.refresh(partner)

    background_tasks.add_task(send_partner_registration_emails, partner)

    return RegisterPendingResponse(
        message="Registration submitted for approval",
        user=AuthUserOut(
            id=str(partner.id),
            name=partner.contact_name or partner.name,
            email=partner.email,
            role=partner.role or "ca_partner",
            firm_name=partner.name,
            profession=partner.profession or partner.firm_type,
            phone=partner.phone,
            membership_no=partner.membership_no,
        ),
    )


@router.post("/admin/login")
def login_admin(payload: LoginRequest):
    response = _admin_auth_response(payload)
    if response is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return response


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    admin_response = _admin_auth_response(payload)
    if admin_response is not None:
        return admin_response

    partner = db.query(Partner).filter(Partner.email == payload.email.lower()).first()
    if not partner or not _verify_password(payload.password, partner.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if (partner.role or "ca_partner") != "ca_partner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized partner access")

    if partner.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Your partner account is pending approval")

    return _auth_response(partner)
