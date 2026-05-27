import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


# ─── Partner schemas ─────────────────────────────────────────────────────────

class PartnerCreate(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    firm_type: Optional[str] = None  # CA, CS
    contact_name: Optional[str] = None
    profession: Optional[str] = None
    membership_no: Optional[str] = None
    gstin: Optional[str] = None
    credits_balance: int = 100
    status: Optional[str] = "active"
    plan: Optional[str] = "starter"
    client_limit_override: Optional[int] = None

class PartnerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    firm_type: Optional[str] = None
    contact_name: Optional[str] = None
    profession: Optional[str] = None
    membership_no: Optional[str] = None
    gstin: Optional[str] = None
    gstn_connected: Optional[bool] = None
    credits_balance: Optional[int] = None
    status: Optional[str] = None
    plan: Optional[str] = None
    client_limit_override: Optional[int] = None

class PartnerOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    phone: Optional[str] = None
    firm_type: Optional[str] = None
    contact_name: Optional[str] = None
    profession: Optional[str] = None
    membership_no: Optional[str] = None
    gstin: Optional[str] = None
    gstn_connected: bool
    gstn_last_sync: Optional[datetime] = None
    credits_balance: int
    status: str
    plan: str
    client_limit_override: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# Auth schemas

class PartnerRegisterRequest(BaseModel):
    name: str
    firm_name: str
    profession: str
    email: str
    password: str
    phone: Optional[str] = None
    membership_no: Optional[str] = None
    role: Optional[str] = "ca_partner"


class LoginRequest(BaseModel):
    email: str
    password: str


class AuthUserOut(BaseModel):
    id: str
    name: Optional[str] = None
    email: str
    role: str
    firm_name: str
    profession: Optional[str] = None
    phone: Optional[str] = None
    membership_no: Optional[str] = None


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUserOut


class RegisterPendingResponse(BaseModel):
    message: str
    user: AuthUserOut
    email_queued: bool = True


# ─── Client schemas ───────────────────────────────────────────────────────────

class ClientCreate(BaseModel):
    name: str
    business_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    gstin: Optional[str] = None
    industry: Optional[str] = "trading"  # manufacturing / trading / services / it
    turnover: Optional[float] = None

class ClientUpdate(BaseModel):
    name: Optional[str] = None
    business_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    gstin: Optional[str] = None
    industry: Optional[str] = None
    turnover: Optional[float] = None
    consent_status: Optional[str] = None
    consent_signed_at: Optional[datetime] = None
    consent_expires_at: Optional[datetime] = None
    data_source: Optional[str] = None
    gstn_enabled: Optional[bool] = None

class ClientOut(BaseModel):
    id: uuid.UUID
    partner_id: uuid.UUID
    name: str
    business_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    gstin: Optional[str] = None
    industry: Optional[str] = None
    turnover: Optional[float] = None
    consent_status: str
    consent_requested_at: Optional[datetime] = None
    consent_signed_at: Optional[datetime] = None
    consent_expires_at: Optional[datetime] = None
    data_source: str
    gstn_enabled: bool
    latest_data_date: Optional[datetime] = None
    latest_data_source: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class ClientListOut(BaseModel):
    total: int
    page: int
    per_page: int
    items: List[ClientOut]

class ClientBulkCreateRequest(BaseModel):
    clients: List[ClientCreate]

class ClientBulkCreateOut(BaseModel):
    created: List[ClientOut]
    failed: List[dict] = []

class ConsentRequestOut(BaseModel):
    client: ClientOut
    consent_url: str
    whatsapp_url: Optional[str] = None
    whatsapp_message: str
    email_queued: bool = False


# ─── File upload schemas ──────────────────────────────────────────────────────

class FileUploadOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    partner_id: uuid.UUID
    file_name: str
    file_type: str
    file_size: Optional[int] = None
    upload_method: str
    processing_status: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Health score schemas ─────────────────────────────────────────────────────

class ScoreComponentsOut(BaseModel):
    gst_integrity_score: Optional[float] = None
    itr_consistency_score: Optional[float] = None
    cashflow_health_score: Optional[float] = None
    compliance_behaviour_score: Optional[float] = None
    data_credibility_score: Optional[float] = None
    gst_itc_score: Optional[float] = None
    filing_score: Optional[float] = None
    cashflow_score: Optional[float] = None
    completeness_score: Optional[float] = None

class HealthScoreOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    score_date: datetime
    total_score: float
    report_number: Optional[str] = None
    report_type: Optional[str] = None
    report_variant: Optional[str] = None
    turnover_band: Optional[str] = None
    client_size_band: Optional[str] = None
    report_price: Optional[int] = None
    credits_required: Optional[int] = None
    credits_used: Optional[int] = None
    suggested_fee_min: Optional[int] = None
    suggested_fee_max: Optional[int] = None
    scoring_version: Optional[str] = None
    scoring_profile: Optional[str] = None
    branding_mode: Optional[str] = None
    report_status: Optional[str] = None
    gst_integrity_score: Optional[float] = None
    itr_consistency_score: Optional[float] = None
    cashflow_health_score: Optional[float] = None
    compliance_behaviour_score: Optional[float] = None
    data_credibility_score: Optional[float] = None
    issues: Optional[list] = None
    advisory: Optional[str] = None
    data_completeness_pct: Optional[float] = None
    gst_data_source: Optional[str] = None
    created_at: datetime
    unlocked_at: Optional[datetime] = None
    downloaded_at: Optional[datetime] = None
    shared_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

class ScoreCalculateResponse(BaseModel):
    health_score: float
    score_components: ScoreComponentsOut
    score_breakdown: Optional[dict] = None
    issues: list
    advisory: str
    data_completeness_pct: float
    score_id: uuid.UUID
    report_number: Optional[str] = None
    report_type: Optional[str] = None
    report_variant: Optional[str] = None
    turnover_band: Optional[str] = None
    client_size_band: Optional[str] = None
    report_price: Optional[int] = None
    credits_required: int = 0
    credits_used: int = 0
    suggested_fee_min: Optional[int] = None
    suggested_fee_max: Optional[int] = None
    scoring_version: str = "V2.0"
    report_status: Optional[str] = None
    report_url: Optional[str] = None
    download_url: Optional[str] = None

class ReportUnlockOut(BaseModel):
    report_id: uuid.UUID
    report_status: str
    credits_remaining: int
    credits_required: int = 0
    credits_used: int = 0
    client_size_band: Optional[str] = None
    suggested_fee_min: Optional[int] = None
    suggested_fee_max: Optional[int] = None
    download_url: str

class ReportUnlockRequest(BaseModel):
    client_size_band: Optional[str] = None


# ─── Credits schemas ──────────────────────────────────────────────────────────

class CreditTransactionOut(BaseModel):
    id: uuid.UUID
    partner_id: uuid.UUID
    transaction_type: str
    credits_amount: int
    balance_after: Optional[int] = None
    related_client_id: Optional[uuid.UUID] = None
    related_health_score_id: Optional[uuid.UUID] = None
    description: Optional[str] = None
    remarks: Optional[str] = None
    created_by: Optional[str] = None
    status: str
    timestamp: datetime

    model_config = {"from_attributes": True}

class CreditsBalanceOut(BaseModel):
    partner_id: uuid.UUID
    credits_balance: int
    transactions: List[CreditTransactionOut]

class CreditsAddRequest(BaseModel):
    amount: int
    description: Optional[str] = "Manual credit top-up"


# ─── Admin dashboard schemas ──────────────────────────────────────────────────

class AdminStats(BaseModel):
    total_partners: int
    active_partners: int = 0
    pending_approvals: int = 0
    total_clients: int
    total_reports: int
    avg_health_score: Optional[float] = None
    average_score: Optional[float] = None
    at_risk_clients: int = 0
    credits_remaining: int = 0
    credits_used: int = 0

class ScoreDistributionItem(BaseModel):
    range: str
    count: int

class ScoreDistribution(BaseModel):
    distribution: List[ScoreDistributionItem]

class AdminReportItem(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    gstin: Optional[str] = None
    partner_id: uuid.UUID
    partner_name: str
    total_score: float
    health_score: Optional[float] = None
    score_date: datetime
    generated_at: Optional[datetime] = None
    report_number: Optional[str] = None
    report_type: Optional[str] = None
    report_variant: Optional[str] = None
    turnover_band: Optional[str] = None
    client_size_band: Optional[str] = None
    report_price: Optional[int] = None
    credits_required: Optional[int] = None
    credits_used: Optional[int] = None
    suggested_fee_min: Optional[int] = None
    suggested_fee_max: Optional[int] = None
    scoring_version: Optional[str] = None
    report_status: Optional[str] = None
    advisory: Optional[str] = None
    issues: Optional[list] = None
    report_url: Optional[str] = None
    download_url: Optional[str] = None

    model_config = {"from_attributes": True}

class AdminReportListOut(BaseModel):
    total: int
    page: int
    per_page: int
    items: List[AdminReportItem]
    reports: Optional[List[AdminReportItem]] = None
