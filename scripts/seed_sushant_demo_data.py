import hashlib
import secrets
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.database import SessionLocal, create_tables, ensure_runtime_schema
from app.models import Client, CreditTransaction, FileUpload, GSTNSyncLog, HealthScore, Partner

EMAIL = "sushant@vertibis.in"
PASSWORD = "Partner@123"
FIRM_NAME = "Sushant CA Firm"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 150_000)
    return f"pbkdf2_sha256$150000${salt}${digest.hex()}"


CLIENTS = [
    {
        "name": "Sharma Textiles",
        "business_name": "Sharma Textiles Pvt Ltd",
        "email": "accounts@sharmatextiles.in",
        "phone": "9876500101",
        "gstin": "27AAQCS1201F1Z5",
        "industry": "trading",
        "turnover": 18400000,
        "consent_status": "signed",
        "score": 42,
        "variant": "Quick MSME Health Report",
        "status": "generated_locked",
        "credits_used": 0,
        "issues": ["GSTR-2B ITC mismatch of Rs 48,200", "Delayed 3B filing pattern in two months", "Vendor reconciliation required"],
        "advisory": "Immediate GST reconciliation and vendor follow-up can prevent ITC leakage and create a billable compliance cleanup engagement.",
    },
    {
        "name": "Vardhaman Alloys",
        "business_name": "Vardhaman Alloys LLP",
        "email": "finance@vardhamanalloys.in",
        "phone": "9876500102",
        "gstin": "27AAQFV2302G1Z3",
        "industry": "manufacturing",
        "turnover": 61200000,
        "consent_status": "signed",
        "score": 86,
        "variant": "Detailed MSME Health Report",
        "status": "download_unlocked",
        "credits_used": 1,
        "issues": ["Turnover growth supports working capital review", "Banking cashflow trend is stable", "GST filing hygiene is strong"],
        "advisory": "Client is ready for a working-capital pitch. Prepare a lender-ready report and charge for loan documentation support.",
    },
    {
        "name": "Om Biotech Pharma",
        "business_name": "Om Biotech Pharma",
        "email": "tax@ombiotech.in",
        "phone": "9876500103",
        "gstin": "27AAQFO3403H1Z1",
        "industry": "manufacturing",
        "turnover": 42800000,
        "consent_status": "signed",
        "score": 63,
        "variant": "FY MSME Health Report",
        "status": "generated_locked",
        "credits_used": 0,
        "issues": ["Filing delay risk", "Cash conversion cycle needs review", "ITR and GST turnover variance needs explanation"],
        "advisory": "A monthly compliance monitoring retainer is recommended to reduce filing risk and improve cash visibility.",
    },
    {
        "name": "Ramesh Packaging",
        "business_name": "Ramesh Packaging Industries",
        "email": "owner@rameshpackaging.in",
        "phone": "9876500104",
        "gstin": "27AAQFR4504J1Z9",
        "industry": "manufacturing",
        "turnover": 9500000,
        "consent_status": "signed",
        "score": 71,
        "variant": "Quick MSME Health Report",
        "status": "generated_locked",
        "credits_used": 0,
        "issues": ["Moderate GST consistency", "Banking data optional but useful", "Quarterly margin movement should be reviewed"],
        "advisory": "Offer a quarterly business health review and GST clean-up session before year-end closing.",
    },
    {
        "name": "Jyoti Business Solutions",
        "business_name": "Jyoti Business Solutions Pvt Ltd",
        "email": "accounts@jyotibusiness.in",
        "phone": "9876500105",
        "gstin": "27AAQFJ5605K1Z7",
        "industry": "services",
        "turnover": 13200000,
        "consent_status": "signed",
        "score": None,
    },
    {
        "name": "Myntra Industrial Services",
        "business_name": "Myntra Industrial Services",
        "email": "tax@myntraindustrial.in",
        "phone": "9876500106",
        "gstin": "27AAQFM6706L1Z4",
        "industry": "services",
        "turnover": 22100000,
        "consent_status": "signed",
        "score": None,
    },
    {
        "name": "Kiran Foods",
        "business_name": "Kiran Foods and Agro",
        "email": "kiranfoods@example.in",
        "phone": "9876500107",
        "gstin": "27AAQFK7807M1Z2",
        "industry": "trading",
        "turnover": 7600000,
        "consent_status": "requested",
        "score": None,
    },
    {
        "name": "Mehta Fabricators",
        "business_name": "Mehta Fabricators",
        "email": "mehta.fabricators@example.in",
        "phone": "9876500108",
        "gstin": "27AAQFM8908N1Z8",
        "industry": "manufacturing",
        "turnover": 17600000,
        "consent_status": "requested",
        "score": None,
    },
    {
        "name": "Aarav Logistics",
        "business_name": "Aarav Logistics",
        "email": "compliance@aaravlogistics.in",
        "phone": "9876500109",
        "gstin": "27AAQFA9009P1Z6",
        "industry": "services",
        "turnover": 28600000,
        "consent_status": "signed_lapsed",
        "score": 54,
        "variant": "FY MSME Health Report",
        "status": "generated_locked",
        "credits_used": 0,
        "issues": ["Consent renewal required", "Moderate score with cashflow monitoring need", "Fuel and vendor GST reconciliation pending"],
        "advisory": "Renew consent and pitch a logistics cashflow monitoring engagement.",
    },
    {
        "name": "Nexa Retail Mart",
        "business_name": "Nexa Retail Mart",
        "email": "owner@nexaretail.in",
        "phone": "9876500110",
        "gstin": "27AAQFN0110Q1Z1",
        "industry": "trading",
        "turnover": 5200000,
        "consent_status": "pending",
        "score": None,
    },
]


def upsert_partner(db) -> Partner:
    partner = db.query(Partner).filter(Partner.email == EMAIL).first()
    if not partner:
        partner = Partner(email=EMAIL)
        db.add(partner)

    partner.name = FIRM_NAME
    partner.contact_name = "Sushant"
    partner.phone = "9876543210"
    partner.firm_type = "CA"
    partner.profession = "Chartered Accountant (CA)"
    partner.membership_no = partner.membership_no or "ICAI-DEMO-001"
    partner.role = "ca_partner"
    partner.status = "active"
    partner.plan = "firm"
    partner.credits_balance = max(partner.credits_balance or 0, 145)
    partner.password_hash = hash_password(PASSWORD)
    db.flush()
    return partner


def apply_consent(client: Client, status: str, now: datetime) -> None:
    if status == "signed":
        client.consent_status = "signed"
        client.consent_requested_at = now - timedelta(days=12)
        client.consent_signed_at = now - timedelta(days=10)
        client.consent_expires_at = now + timedelta(days=355)
        client.consent_token = None
    elif status == "signed_lapsed":
        client.consent_status = "signed"
        client.consent_requested_at = now - timedelta(days=390)
        client.consent_signed_at = now - timedelta(days=385)
        client.consent_expires_at = now - timedelta(days=20)
        client.consent_token = None
    elif status == "requested":
        client.consent_status = "requested"
        client.consent_requested_at = now - timedelta(days=2)
        client.consent_signed_at = None
        client.consent_expires_at = None
        client.consent_token = client.consent_token or secrets.token_urlsafe(24)
    else:
        client.consent_status = "pending"
        client.consent_requested_at = None
        client.consent_signed_at = None
        client.consent_expires_at = None
        client.consent_token = None


def upsert_client(db, partner: Partner, data: dict, now: datetime) -> Client:
    client = (
        db.query(Client)
        .filter(Client.partner_id == partner.id, Client.gstin == data["gstin"])
        .first()
    )
    if not client:
        client = Client(partner_id=partner.id, gstin=data["gstin"])
        db.add(client)

    for field in ("name", "business_name", "email", "phone", "industry", "turnover"):
        setattr(client, field, data[field])
    client.data_source = "gst_api_ready_demo"
    client.gstn_enabled = True
    client.gstn_last_fetch = now - timedelta(days=1)
    client.latest_data_date = now - timedelta(days=1)
    client.latest_data_source = "gst_api_demo"
    apply_consent(client, data["consent_status"], now)
    db.flush()
    return client


def upsert_upload(db, partner: Partner, client: Client, file_name: str, file_type: str, now: datetime) -> None:
    upload = (
        db.query(FileUpload)
        .filter(FileUpload.client_id == client.id, FileUpload.file_name == file_name)
        .first()
    )
    if not upload:
        upload = FileUpload(client_id=client.id, partner_id=partner.id, file_name=file_name)
        db.add(upload)

    upload.partner_id = partner.id
    upload.file_type = file_type
    upload.file_path = f"demo/{client.gstin}/{file_name}"
    upload.file_size = 185000
    upload.upload_method = "demo_seed"
    upload.processing_status = "processed"
    upload.created_at = now - timedelta(days=3)


def upsert_score(db, client: Client, data: dict, index: int, now: datetime) -> HealthScore | None:
    if data.get("score") is None:
        return None

    report_number = f"VBI-DEMO-{index:03d}"
    score = db.query(HealthScore).filter(HealthScore.report_number == report_number).first()
    if not score:
        score = HealthScore(client_id=client.id, report_number=report_number)
        db.add(score)

    total = float(data["score"])
    score.client_id = client.id
    score.score_date = now - timedelta(days=index)
    score.total_score = total
    score.report_type = "detailed" if total >= 80 else "quick"
    score.report_variant = data["variant"]
    score.turnover_band = "50L-2Cr" if (client.turnover or 0) < 20000000 else "2Cr+"
    score.report_price = 1499 if score.report_type == "detailed" else 499
    score.credits_used = int(data["credits_used"])
    score.scoring_version = "V2.0-demo"
    score.scoring_profile = "gst-api-ready"
    score.branding_mode = "co_branded"
    score.report_status = data["status"]
    score.gst_integrity_score = min(98, max(30, total + 4))
    score.itr_consistency_score = min(96, max(35, total - 3))
    score.cashflow_health_score = min(95, max(30, total + 1))
    score.compliance_behaviour_score = min(97, max(25, total - 7))
    score.data_credibility_score = 88 if total >= 75 else 72
    score.issues = data["issues"]
    score.advisory = data["advisory"]
    score.data_completeness_pct = 82 if total < 75 else 94
    score.gst_data_source = "gst_api_demo"
    return score


def upsert_gst_log(db, partner: Partner, client: Client, now: datetime) -> None:
    existing = (
        db.query(GSTNSyncLog)
        .filter(GSTNSyncLog.client_id == client.id, GSTNSyncLog.sync_type == "demo_monthly_fetch")
        .first()
    )
    if not existing:
        existing = GSTNSyncLog(client_id=client.id, partner_id=partner.id, sync_type="demo_monthly_fetch")
        db.add(existing)

    existing.partner_id = partner.id
    existing.gstr_type = "GSTR1_3B_2B"
    existing.request_timestamp = now - timedelta(days=1)
    existing.response_status = "success"
    existing.records_fetched = 6
    existing.records_processed = 6
    existing.records_failed = 0
    existing.error_message = None
    existing.error_details = None


def upsert_credit_tx(db, partner: Partner, amount: int, description: str, now: datetime, client: Client | None = None, score: HealthScore | None = None) -> None:
    tx = (
        db.query(CreditTransaction)
        .filter(CreditTransaction.partner_id == partner.id, CreditTransaction.description == description)
        .first()
    )
    if not tx:
        tx = CreditTransaction(partner_id=partner.id, description=description)
        db.add(tx)

    tx.transaction_type = "purchase" if amount > 0 else "report_unlock"
    tx.credits_amount = amount
    tx.related_client_id = client.id if client else None
    tx.related_health_score_id = score.id if score else None
    tx.status = "completed"
    tx.timestamp = now - timedelta(days=1 if amount < 0 else 20)


def main() -> None:
    create_tables()
    ensure_runtime_schema()
    now = datetime.utcnow()
    db = SessionLocal()
    try:
        partner = upsert_partner(db)
        score_count = 0
        created_clients: list[Client] = []

        for index, data in enumerate(CLIENTS, start=1):
            client = upsert_client(db, partner, data, now)
            created_clients.append(client)
            upsert_gst_log(db, partner, client, now)

            if data.get("score") is not None:
                upsert_upload(db, partner, client, f"{client.gstin}_GST_API_APR_MAY_2024.json", "gst_api", now)
                upsert_upload(db, partner, client, f"{client.gstin}_ITR_FY2024_25.json", "itr_json", now)
                upsert_upload(db, partner, client, f"{client.gstin}_BANKING_FY2025_26.csv", "banking", now)
                score = upsert_score(db, client, data, index, now)
                score_count += 1
                db.flush()
                if data["credits_used"]:
                    upsert_credit_tx(db, partner, -1, f"Demo report download credit used for {client.name}", now, client, score)

        upsert_credit_tx(db, partner, 150, "Demo credit grant for Sushant CA Firm assessment", now)
        partner.credits_balance = max(partner.credits_balance or 0, 145)

        db.commit()
        print("Demo data ready.")
        print(f"Partner: {partner.name} <{partner.email}>")
        print(f"Password: {PASSWORD}")
        print(f"Clients available: {len(created_clients)}")
        print(f"Reports available: {score_count}")
        print(f"Credits balance: {partner.credits_balance}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
