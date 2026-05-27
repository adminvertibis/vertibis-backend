import hashlib
import hmac
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal, create_tables, ensure_runtime_schema
from app.models import Partner

EMAIL = "sushant@vertibis.in"
PASSWORD = "Partner@123"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 150_000)
    return f"pbkdf2_sha256$150000${salt}${digest.hex()}"


def main() -> None:
    create_tables()
    ensure_runtime_schema()
    db = SessionLocal()
    try:
        partner = db.query(Partner).filter(Partner.email == EMAIL).first()
        if not partner:
            partner = Partner(
                name="Sushant CA Firm",
                contact_name="Sushant",
                email=EMAIL,
                phone="9876543210",
                firm_type="CA",
                profession="Chartered Accountant",
                role="ca_partner",
                credits_balance=500,
                status="active",
            )
            db.add(partner)

        partner.password_hash = hash_password(PASSWORD)
        partner.role = "ca_partner"
        partner.status = "active"
        if not partner.credits_balance:
            partner.credits_balance = 500

        db.commit()
        db.refresh(partner)
        print(f"Test partner ready: {partner.email}")
        print(f"Partner ID: {partner.id}")
        print(f"Password: {PASSWORD}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
