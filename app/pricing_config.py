from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DashboardPackage:
    slug: str
    name: str
    client_limit: Optional[int]
    monthly_price: Optional[int]
    annual_price: Optional[int]
    included_credits: int = 0


@dataclass(frozen=True)
class ClientSizeBand:
    id: str
    name: str
    label: str
    min_turnover: Optional[float]
    max_turnover: Optional[float]


@dataclass(frozen=True)
class ReportType:
    id: str
    slug: str
    name: str
    required_itr_files: int
    required_gst_files: int = 0
    preview_allowed: bool = True
    downloadable: bool = True


@dataclass(frozen=True)
class ReportCreditRule:
    report_type_id: str
    client_size_band_id: str
    credits_required: Optional[int]
    suggested_fee_min: Optional[int] = None
    suggested_fee_max: Optional[int] = None


DASHBOARD_PACKAGES = [
    DashboardPackage("starter", "Starter", 25, 999, 9999),
    DashboardPackage("growth", "Growth", 100, 2999, 29999),
    DashboardPackage("scale", "Scale", 250, 6999, 69999),
    DashboardPackage("firm", "Firm", 500, 11999, 119999),
    DashboardPackage("network", "Network", None, None, None),
    DashboardPackage("founding-lite", "Founding Partner Lite", 25, None, 5999, 20),
    DashboardPackage("founding-pro", "Founding Partner Pro", 100, None, 11999, 60),
    DashboardPackage("founding-elite", "Founding Partner Elite", 250, None, 24999, 150),
]

CLIENT_SIZE_BANDS = [
    ClientSizeBand("size-small", "small", "Micro / Small", 0, 50_000_000),
    ClientSizeBand("size-medium", "medium", "Medium", 50_000_000, 250_000_000),
    ClientSizeBand("size-large", "large", "Large", 250_000_000, 1_000_000_000),
    ClientSizeBand("size-enterprise", "enterprise", "Enterprise", 1_000_000_000, None),
]

REPORT_TYPES = [
    ReportType("report-quick", "quick_snapshot", "Quick Business Health Snapshot", 1, 0),
    ReportType("report-annual", "annual", "Annual Business Health Report", 1, 0),
    ReportType("report-detailed-2y", "detailed_2y", "Detailed 2-Year Trend Report", 2, 0),
    ReportType("report-premium-advisory", "premium_advisory", "Premium Advisory Report", 2, 0),
    ReportType("report-loan-readiness", "loan_readiness", "Loan Readiness / NBFC-Focused Report", 2, 0),
]

REPORT_CREDIT_RULES = [
    ReportCreditRule("report-quick", "size-small", 0),
    ReportCreditRule("report-quick", "size-medium", 0),
    ReportCreditRule("report-quick", "size-large", 0),
    ReportCreditRule("report-quick", "size-enterprise", 0),
    ReportCreditRule("report-annual", "size-small", 1, 999, 1999),
    ReportCreditRule("report-annual", "size-medium", 2, 2499, 4999),
    ReportCreditRule("report-annual", "size-large", 4, 5000, 10000),
    ReportCreditRule("report-annual", "size-enterprise", None),
    ReportCreditRule("report-detailed-2y", "size-small", 3, 2499, 4999),
    ReportCreditRule("report-detailed-2y", "size-medium", 5, 5000, 10000),
    ReportCreditRule("report-detailed-2y", "size-large", 10, 10000, 25000),
    ReportCreditRule("report-detailed-2y", "size-enterprise", None),
    ReportCreditRule("report-premium-advisory", "size-small", 6, 5000, 10000),
    ReportCreditRule("report-premium-advisory", "size-medium", 10, 10000, 25000),
    ReportCreditRule("report-premium-advisory", "size-large", 25, 25000, 75000),
    ReportCreditRule("report-premium-advisory", "size-enterprise", None),
    ReportCreditRule("report-loan-readiness", "size-small", 6, 5000, 15000),
    ReportCreditRule("report-loan-readiness", "size-medium", 12, 15000, 40000),
    ReportCreditRule("report-loan-readiness", "size-large", 25, 40000, 100000),
    ReportCreditRule("report-loan-readiness", "size-enterprise", None),
]

CREDIT_PACKS = [
    {"id": "credit-starter", "name": "Starter Credit Pack", "credits": 25, "price": 4999},
    {"id": "credit-growth", "name": "Growth Credit Pack", "credits": 60, "price": 9999},
    {"id": "credit-scale", "name": "Scale Credit Pack", "credits": 150, "price": 19999},
    {"id": "credit-firm", "name": "Firm Credit Pack", "credits": 400, "price": 49999},
]


def normalize_report_slug(value: object) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"quick", "quick_snapshot", "snapshot", "quick-business-health-snapshot"}:
        return "quick_snapshot"
    if raw in {"fy", "annual", "financial_year", "financial-year", "annual_business_health_report"}:
        return "annual"
    if raw in {"detailed", "detailed_2y", "detailed-2y", "detailed_2_year"}:
        return "detailed_2y"
    if raw in {"premium", "premium_advisory", "premium-advisory"}:
        return "premium_advisory"
    if raw in {"loan", "loan_readiness", "loan-readiness", "nbfc"}:
        return "loan_readiness"
    return "quick_snapshot"


def get_report_type(value: object) -> ReportType:
    slug = normalize_report_slug(value)
    return next((item for item in REPORT_TYPES if item.slug == slug), REPORT_TYPES[0])


def normalize_client_size(value: object) -> Optional[str]:
    raw = str(value or "").strip().lower()
    if raw in {"small", "micro", "micro_small", "micro/small", "upto_1cr"}:
        return "small"
    if raw in {"medium", "1_5cr", "5_25cr"}:
        return "medium"
    if raw in {"large", "25_100cr"}:
        return "large"
    if raw in {"enterprise", "above_100cr", "above_5cr"}:
        return "enterprise"
    return None


def classify_client_size(turnover: Optional[float]) -> Optional[str]:
    if turnover is None or turnover <= 0:
        return None
    for band in CLIENT_SIZE_BANDS:
        min_turnover = band.min_turnover or 0
        max_turnover = band.max_turnover
        if turnover >= min_turnover and (max_turnover is None or turnover <= max_turnover):
            return band.name
    return None


def get_size_band(value: object = None, turnover: Optional[float] = None) -> Optional[ClientSizeBand]:
    name = normalize_client_size(value) or classify_client_size(turnover)
    if not name:
        return None
    return next((item for item in CLIENT_SIZE_BANDS if item.name == name), None)


def get_credit_rule(report_type_value: object, size_value: object = None, turnover: Optional[float] = None) -> Optional[ReportCreditRule]:
    report_type = get_report_type(report_type_value)
    band = get_size_band(size_value, turnover)
    if not band:
        return None
    return next(
        (item for item in REPORT_CREDIT_RULES if item.report_type_id == report_type.id and item.client_size_band_id == band.id),
        None,
    )


def get_dashboard_package(slug: object) -> DashboardPackage:
    normalized = str(slug or "starter").strip().lower()
    return next((item for item in DASHBOARD_PACKAGES if item.slug == normalized), DASHBOARD_PACKAGES[0])


def serialize_pricing_config() -> dict:
    return {
        "dashboard_packages": [item.__dict__ for item in DASHBOARD_PACKAGES],
        "client_size_bands": [item.__dict__ for item in CLIENT_SIZE_BANDS],
        "report_types": [item.__dict__ for item in REPORT_TYPES],
        "report_credit_rules": [item.__dict__ for item in REPORT_CREDIT_RULES],
        "credit_packs": CREDIT_PACKS,
        "mode": "default_config_adapter",
    }
