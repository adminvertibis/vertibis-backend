"""
Vertibis Scoring Engine V2.0.

Implements the five-component model from Vertibis_Scoring_Model_V2:
GST Integrity, ITR Consistency, Cashflow Health, Compliance Behaviour,
and Data Credibility.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Tuple


class Industry(str, Enum):
    MANUFACTURING = "manufacturing"
    TRADING = "trading"
    SERVICES = "services"
    IT = "it"


class ScoringEngine:
    VERSION = "V2.0"

    COMPONENT_WEIGHTS = {
        "core": {
            "gst_integrity_score": 0.25,
            "itr_consistency_score": 0.20,
            "cashflow_health_score": 0.20,
            "compliance_behaviour_score": 0.20,
            "data_credibility_score": 0.15,
        },
        "lending": {
            "gst_integrity_score": 0.15,
            "itr_consistency_score": 0.30,
            "cashflow_health_score": 0.40,
            "compliance_behaviour_score": 0.10,
            "data_credibility_score": 0.05,
        },
        "vendor": {
            "gst_integrity_score": 0.35,
            "itr_consistency_score": 0.20,
            "cashflow_health_score": 0.30,
            "compliance_behaviour_score": 0.10,
            "data_credibility_score": 0.05,
        },
        "compliance": {
            "gst_integrity_score": 0.25,
            "itr_consistency_score": 0.20,
            "cashflow_health_score": 0.15,
            "compliance_behaviour_score": 0.35,
            "data_credibility_score": 0.05,
        },
    }

    PROFIT_BENCHMARKS = {
        Industry.MANUFACTURING: {"min": 3, "good": 8, "excellent": 12},
        Industry.TRADING: {"min": 5, "good": 12, "excellent": 18},
        Industry.SERVICES: {"min": 15, "good": 25, "excellent": 35},
        Industry.IT: {"min": 20, "good": 30, "excellent": 40},
    }

    @staticmethod
    def calculate_score(
        extracted_data: Dict[str, Any],
        industry: str,
        turnover: float,
        scoring_profile: str = "core",
    ) -> Dict[str, Any]:
        try:
            industry_enum = Industry(str(industry or "").lower())
        except ValueError:
            industry_enum = Industry.TRADING

        profile = scoring_profile if scoring_profile in ScoringEngine.COMPONENT_WEIGHTS else "core"
        metrics = ScoringEngine._derive_metrics(extracted_data, turnover)

        gst_score, gst_issues = ScoringEngine._score_gst_integrity(metrics)
        itr_score, itr_issues = ScoringEngine._score_itr_consistency(metrics, industry_enum)
        cashflow_score, cashflow_issues = ScoringEngine._score_cashflow_health(metrics)
        compliance_score, compliance_issues = ScoringEngine._score_compliance_behaviour(metrics)
        credibility_score, credibility_issues = ScoringEngine._score_data_credibility(metrics, extracted_data)

        components = {
            "gst_integrity_score": round(gst_score, 1),
            "itr_consistency_score": round(itr_score, 1),
            "cashflow_health_score": round(cashflow_score, 1),
            "compliance_behaviour_score": round(compliance_score, 1),
            "data_credibility_score": round(credibility_score, 1),
            # Legacy aliases retained for existing frontend/backend contracts.
            "gst_itc_score": round(gst_score, 1),
            "filing_score": round(compliance_score, 1),
            "cashflow_score": round(cashflow_score, 1),
            "completeness_score": round(credibility_score, 1),
        }

        weights = ScoringEngine.COMPONENT_WEIGHTS[profile]
        total_score = sum(components[key] * weight for key, weight in weights.items())

        return {
            "total_score": round(min(100, max(0, total_score)), 1),
            "components": components,
            "issues": gst_issues + itr_issues + cashflow_issues + compliance_issues + credibility_issues,
            "metrics": metrics,
            "industry": industry_enum.value,
            "scoring_version": ScoringEngine.VERSION,
            "scoring_profile": profile,
        }

    @staticmethod
    def _derive_metrics(data: Dict[str, Any], turnover: float) -> Dict[str, Any]:
        gstr1_sales = float(data.get("gstr1_total_sales") or 0)
        gstr3b_sales = float(data.get("gstr3b_total_sales") or 0)
        itr_turnover = float(data.get("itr_total_turnover") or 0)
        effective_turnover = float(turnover or gstr1_sales or gstr3b_sales or itr_turnover or 0)
        monthly_turnover = effective_turnover / 12 if effective_turnover else 0

        gstr3b_itc = float(data.get("gstr3b_itc_availed") or 0)
        gstr2a_itc = float(data.get("gstr2a_itc_received") or 0)
        avg_balance = float(data.get("banking_avg_balance") or 0)
        bounce_count = int(data.get("banking_bounce_count") or 0)

        filing_delays = ScoringEngine._filing_delay_days(data)
        filing_count = max(1, sum(1 for key in ("gstr1_filing_date", "gstr3b_filing_date", "itr_filing_date") if data.get(key)))
        late_count = sum(1 for days in filing_delays if days > 0)
        avg_delay = sum(max(0, days) for days in filing_delays) / filing_count

        turnover_base = max(gstr3b_sales, gstr1_sales, itr_turnover, effective_turnover, 1)
        return {
            "gstr1_3b_variance_pct": ScoringEngine._pct(abs(gstr1_sales - gstr3b_sales), max(gstr3b_sales, gstr1_sales, 1)),
            "excess_itc_over_2b_pct": ScoringEngine._pct(max(0, gstr3b_itc - gstr2a_itc), turnover_base),
            "filing_delay_count_12m": late_count,
            "avg_filing_delay_days": avg_delay,
            "gst_itr_turnover_gap_pct": ScoringEngine._pct(abs(gstr3b_sales - itr_turnover), max(itr_turnover, gstr3b_sales, 1)),
            "net_profit_margin_pct": float(data.get("itr_profit_margin_pct") or 0),
            "bank_gst_gap_pct": ScoringEngine._pct(abs((avg_balance * 12) - gstr3b_sales), max(gstr3b_sales, 1)) if avg_balance and gstr3b_sales else None,
            "cash_buffer_months": avg_balance / monthly_turnover if monthly_turnover else 0,
            "bounce_rate_pct": min(100, bounce_count * 2),
            "payment_discipline_score": max(0, 100 - (bounce_count * 10)),
            "gst_filing_punctuality_score": max(0, 100 - (late_count * 10) - avg_delay),
            "amendment_frequency_pct": float(data.get("gstr1_amendments_count") or 0),
            "yoy_growth_trend_pct": float(data.get("yoy_growth_trend_pct") or data.get("growth_trend_pct") or 0),
            "volatility_score": float(data.get("volatility_score") or data.get("yoy_turnover_volatility_pct") or 20),
            "notice_response_days": float(data.get("notice_response_days") or 0),
            "compliance_notice_count_12m": int(data.get("compliance_notice_count_12m") or 0),
            "invoice_quality_index": max(
                0,
                100
                - (float(data.get("gstr1_amendments_count") or 0) * 5)
                - (float(data.get("gstr2a_discrepancies_count") or 0) * 10),
            ),
            "data_completeness_pct": float(data.get("data_completeness_pct") or 0),
        }

    @staticmethod
    def _score_gst_integrity(metrics: Dict[str, Any]) -> Tuple[float, list[str]]:
        parts = [
            (ScoringEngine._lower_is_better(metrics["gstr1_3b_variance_pct"], 2, 20), 8),
            (ScoringEngine._lower_is_better(metrics["excess_itc_over_2b_pct"], 0.5, 10), 7),
            (ScoringEngine._lower_is_better(metrics["filing_delay_count_12m"], 0, 6), 6),
            (ScoringEngine._lower_is_better(metrics["amendment_frequency_pct"], 2, 12), 5),
            (ScoringEngine._higher_is_better(metrics["invoice_quality_index"], 95, 70), 6),
        ]
        issues = []
        if metrics["gstr1_3b_variance_pct"] > 5:
            issues.append(f"GSTR-1 vs GSTR-3B variance is {metrics['gstr1_3b_variance_pct']:.1f}%")
        if metrics["excess_itc_over_2b_pct"] > 0.5:
            issues.append(f"ITC claimed above 2B by {metrics['excess_itc_over_2b_pct']:.1f}% of turnover")
        if metrics["amendment_frequency_pct"] > 2:
            issues.append("GST amendment frequency is above the clean-invoice threshold")
        return ScoringEngine._weighted_average(parts), issues

    @staticmethod
    def _score_itr_consistency(metrics: Dict[str, Any], industry: Industry) -> Tuple[float, list[str]]:
        benchmark = ScoringEngine.PROFIT_BENCHMARKS[industry]
        parts = [
            (ScoringEngine._lower_is_better(metrics["gst_itr_turnover_gap_pct"], 5, 35), 8),
            (ScoringEngine._higher_is_better(metrics["net_profit_margin_pct"], benchmark["good"], benchmark["min"]), 8),
            (ScoringEngine._higher_is_better(metrics["yoy_growth_trend_pct"], 5, -10), 6),
            (ScoringEngine._lower_is_better(metrics["volatility_score"], 15, 45), 6),
        ]
        issues = []
        if metrics["gst_itr_turnover_gap_pct"] > 5:
            issues.append(f"GST and ITR turnover differ by {metrics['gst_itr_turnover_gap_pct']:.1f}%")
        if metrics["net_profit_margin_pct"] and metrics["net_profit_margin_pct"] < benchmark["min"]:
            issues.append("Net profit margin is below the industry safety band")
        return ScoringEngine._weighted_average(parts), issues

    @staticmethod
    def _score_cashflow_health(metrics: Dict[str, Any]) -> Tuple[float, list[str]]:
        bank_gap = metrics["bank_gst_gap_pct"]
        bank_gap_score = 60 if bank_gap is None else ScoringEngine._lower_is_better(bank_gap, 5, 40)
        parts = [
            (bank_gap_score, 7),
            (ScoringEngine._higher_is_better(metrics["cash_buffer_months"], 3, 0.5), 7),
            (ScoringEngine._lower_is_better(metrics["bounce_rate_pct"], 0, 10), 6),
            (ScoringEngine._lower_is_better(metrics["volatility_score"], 15, 45), 6),
        ]
        issues = []
        if metrics["cash_buffer_months"] < 1:
            issues.append("Cash buffer is below one month of turnover")
        if metrics["bounce_rate_pct"] > 0:
            issues.append("Banking bounce events reduce repayment confidence")
        return ScoringEngine._weighted_average(parts), issues

    @staticmethod
    def _score_compliance_behaviour(metrics: Dict[str, Any]) -> Tuple[float, list[str]]:
        response_days = metrics["notice_response_days"]
        response_score = 85 if response_days <= 0 else ScoringEngine._lower_is_better(response_days, 30, 120)
        culture_score = (
            metrics["payment_discipline_score"]
            + metrics["gst_filing_punctuality_score"]
            + response_score
        ) / 3
        parts = [
            (metrics["payment_discipline_score"], 8),
            (metrics["gst_filing_punctuality_score"], 7),
            (response_score, 5),
            (culture_score, 8),
        ]
        issues = []
        if metrics["filing_delay_count_12m"] > 0:
            issues.append(f"{metrics['filing_delay_count_12m']} late filing event(s) detected")
        if metrics["compliance_notice_count_12m"] > 0:
            issues.append("Compliance notices need tracked closure")
        return ScoringEngine._weighted_average(parts), issues

    @staticmethod
    def _score_data_credibility(metrics: Dict[str, Any], data: Dict[str, Any]) -> Tuple[float, list[str]]:
        completeness = metrics["data_completeness_pct"]
        source = str(data.get("gst_data_source") or data.get("latest_data_source") or data.get("upload_mode") or "manual").lower()
        source_weight = 100 if "api" in source or "gstn" in source else 75
        score = (completeness * 0.70) + (source_weight * 0.30)
        issues = []
        if completeness < 80:
            issues.append(f"Data completeness is {completeness:.0f}%; report confidence is limited")
        return score, issues

    @staticmethod
    def _filing_delay_days(data: Dict[str, Any]) -> list[int]:
        checks = [
            ("gstr1_filing_date", 11),
            ("gstr3b_filing_date", 20),
            ("itr_filing_date", 31),
        ]
        delays = []
        for key, due_day in checks:
            date = data.get(key)
            if not isinstance(date, datetime):
                continue
            if key == "itr_filing_date":
                due_date = date.replace(month=7, day=31)
            else:
                due_date = date.replace(day=due_day)
            delays.append((date - due_date).days)
        return delays

    @staticmethod
    def _pct(numerator: float, denominator: float) -> float:
        return (numerator / denominator * 100) if denominator else 0

    @staticmethod
    def _lower_is_better(value: float, good: float, bad: float) -> float:
        if value <= good:
            return 100
        if value >= bad:
            return 0
        return 100 - ((value - good) / (bad - good) * 100)

    @staticmethod
    def _higher_is_better(value: float, good: float, bad: float) -> float:
        if value >= good:
            return 100
        if value <= bad:
            return 0
        return ((value - bad) / (good - bad)) * 100

    @staticmethod
    def _weighted_average(parts: list[Tuple[float, int]]) -> float:
        total_weight = sum(weight for _, weight in parts) or 1
        return sum(max(0, min(100, score)) * weight for score, weight in parts) / total_weight
