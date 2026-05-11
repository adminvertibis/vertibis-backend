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
    gstin: Optional[str] = None
    credits_balance: int = 100

class PartnerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    firm_type: Optional[str] = None
    gstin: Optional[str] = None
    gstn_connected: Optional[bool] = None
    credits_balance: Optional[int] = None
    status: Optional[str] = None

class PartnerOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str
    phone: Optional[str] = None
    firm_type: Optional[str] = None
    gstin: Optional[str] = None
    gstn_connected: bool
    gstn_last_sync: Optional[datetime] = None
    credits_balance: int
    status: str
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
    id: uuid.UUID
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


# ─── Client schemas ───────────────────────────────────────────────────────────

class ClientCreate(BaseModel):
    name: str
    business_name: Optional[str] = None
    gstin: Optional[str] = None
    industry: Optional[str] = "trading"  # manufacturing / trading / services / it
    turnover: Optional[float] = None
    partner_id: uuid.UUID

class ClientUpdate(BaseModel):
    name: Optional[str] = None
    business_name: Optional[str] = None
    gstin: Optional[str] = None
    industry: Optional[str] = None
    turnover: Optional[float] = None
    data_source: Optional[str] = None
    gstn_enabled: Optional[bool] = None

class ClientOut(BaseModel):
    id: uuid.UUID
    partner_id: uuid.UUID
    name: str
    business_name: Optional[str] = None
    gstin: Optional[str] = None
    industry: Optional[str] = None
    turnover: Optional[float] = None
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
    gst_itc_score: Optional[float] = None
    filing_score: Optional[float] = None
    cashflow_score: Optional[float] = None
    completeness_score: Optional[float] = None

class HealthScoreOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    score_date: datetime
    total_score: float
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

    model_config = {"from_attributes": True}

class ScoreCalculateResponse(BaseModel):
    health_score: float
    score_components: ScoreComponentsOut
    issues: list
    advisory: str
    data_completeness_pct: float
    score_id: uuid.UUID


# ─── Credits schemas ──────────────────────────────────────────────────────────

class CreditTransactionOut(BaseModel):
    id: uuid.UUID
    partner_id: uuid.UUID
    transaction_type: str
    credits_amount: int
    related_client_id: Optional[uuid.UUID] = None
    description: Optional[str] = None
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
    total_clients: int
    total_reports: int
    avg_health_score: Optional[float] = None

class ScoreDistributionItem(BaseModel):
    range: str
    count: int

class ScoreDistribution(BaseModel):
    distribution: List[ScoreDistributionItem]

class AdminReportItem(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    partner_id: uuid.UUID
    partner_name: str
    total_score: float
    score_date: datetime
    advisory: Optional[str] = None

    model_config = {"from_attributes": True}

class AdminReportListOut(BaseModel):
    total: int
    page: int
    per_page: int
    items: List[AdminReportItem]
