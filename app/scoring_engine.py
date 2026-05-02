"""
Scoring Engine - Calculate health scores
Copy entire content to: C:\vertibis-backend\app\scoring_engine.py
"""

from typing import Dict, Any, Tuple
from enum import Enum
from datetime import datetime


class Industry(str, Enum):
    MANUFACTURING = "manufacturing"
    TRADING = "trading"
    SERVICES = "services"
    IT = "it"


class TurnoverSize(str, Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class ScoringEngine:
    
    PROFIT_BENCHMARKS = {
        Industry.MANUFACTURING: {"min": 3, "good": 8, "excellent": 12},
        Industry.TRADING: {"min": 5, "good": 12, "excellent": 18},
        Industry.SERVICES: {"min": 15, "good": 25, "excellent": 35},
        Industry.IT: {"min": 20, "good": 30, "excellent": 40},
    }
    
    BALANCE_BENCHMARKS = {
        Industry.MANUFACTURING: 12,
        Industry.TRADING: 10,
        Industry.SERVICES: 15,
        Industry.IT: 20,
    }
    
    GAP_TOLERANCE = {
        Industry.MANUFACTURING: 5,
        Industry.TRADING: 3,
        Industry.SERVICES: 2,
        Industry.IT: 1,
    }
    
    @staticmethod
    def calculate_score(
        extracted_data: Dict[str, Any],
        industry: str,
        turnover: float
    ) -> Dict[str, Any]:
        
        try:
            industry_enum = Industry(industry.lower())
        except:
            industry_enum = Industry.TRADING
        
        if turnover < 5000000:
            size_enum = TurnoverSize.SMALL
        elif turnover < 500000000:
            size_enum = TurnoverSize.MEDIUM
        else:
            size_enum = TurnoverSize.LARGE
        
        scores = {}
        issues = []
        
        # GST-ITR Match
        gst_itc_score, gap_issues = ScoringEngine._score_gst_itc_match(
            extracted_data, industry_enum
        )
        scores['gst_itc_score'] = gst_itc_score
        issues.extend(gap_issues)
        
        # Filing Timeliness
        filing_score, filing_issues = ScoringEngine._score_filing_timeliness(
            extracted_data
        )
        scores['filing_score'] = filing_score
        issues.extend(filing_issues)
        
        # Cashflow Health
        cashflow_score, cashflow_issues = ScoringEngine._score_cashflow_health(
            extracted_data, industry_enum
        )
        scores['cashflow_score'] = cashflow_score
        issues.extend(cashflow_issues)
        
        # Completeness
        completeness_score = ScoringEngine._score_completeness(extracted_data)
        scores['completeness_score'] = completeness_score
        
        total_score = (
            gst_itc_score + filing_score + cashflow_score + completeness_score
        )
        
        return {
            'total_score': min(100, max(0, total_score)),
            'components': scores,
            'issues': issues,
            'industry': industry_enum.value,
        }
    
    @staticmethod
    def _score_gst_itc_match(
        data: Dict[str, Any],
        industry: Industry
    ) -> Tuple[float, list]:
        issues = []
        
        gstr3b_sales = data.get('gstr3b_total_sales', 0)
        itr_turnover = data.get('itr_total_turnover', 0)
        
        if not gstr3b_sales or not itr_turnover:
            return 15, ["Missing GST or ITR sales data"]
        
        gap_pct = abs(gstr3b_sales - itr_turnover) / itr_turnover * 100
        tolerance = ScoringEngine.GAP_TOLERANCE.get(industry, 5)
        
        if gap_pct <= tolerance:
            score = 25
        elif gap_pct <= tolerance * 2:
            score = 20
        elif gap_pct <= tolerance * 5:
            score = 10
            gap_amount = abs(gstr3b_sales - itr_turnover)
            issues.append(f"GST-ITR gap ₹{gap_amount:,.0f} ({gap_pct:.1f}%)")
        else:
            score = 0
            gap_amount = abs(gstr3b_sales - itr_turnover)
            issues.append(f"Major GST-ITR gap ₹{gap_amount:,.0f} ({gap_pct:.1f}%)")
        
        return score, issues
    
    @staticmethod
    def _score_filing_timeliness(data: Dict[str, Any]) -> Tuple[float, list]:
        issues = []
        total_delay_days = 0
        filing_count = 0
        
        gstr1_date = data.get('gstr1_filing_date')
        if gstr1_date:
            due_date = gstr1_date.replace(day=11)
            delay = (gstr1_date - due_date).days
            filing_count += 1
            if delay > 0:
                total_delay_days += delay
                issues.append(f"GSTR-1 filed {delay} days late")
        
        gstr3b_date = data.get('gstr3b_filing_date')
        if gstr3b_date:
            due_date = gstr3b_date.replace(day=20)
            delay = (gstr3b_date - due_date).days
            filing_count += 1
            if delay > 0:
                total_delay_days += delay
                issues.append(f"GSTR-3B filed {delay} days late")
        
        itr_date = data.get('itr_filing_date')
        if itr_date:
            due_date = itr_date.replace(month=7, day=31)
            delay = (itr_date - due_date).days
            filing_count += 1
            if delay > 0:
                total_delay_days += delay
                issues.append(f"ITR filed {delay} days late")
        
        if filing_count == 0:
            return 15, ["Filing dates not provided"]
        
        avg_delay = total_delay_days / filing_count
        
        if avg_delay <= 0:
            score = 25
        elif avg_delay <= 5:
            score = 20
        elif avg_delay <= 15:
            score = 10
        else:
            score = 0
        
        return score, issues
    
    @staticmethod
    def _score_cashflow_health(
        data: Dict[str, Any],
        industry: Industry
    ) -> Tuple[float, list]:
        issues = []
        
        avg_balance = data.get('banking_avg_balance', 0)
        gstr3b_sales = data.get('gstr3b_total_sales', 0)
        
        if not avg_balance or not gstr3b_sales:
            return 15, ["Banking or sales data missing"]
        
        monthly_sales = gstr3b_sales / 12
        benchmark_pct = ScoringEngine.BALANCE_BENCHMARKS.get(industry, 12)
        required_balance = monthly_sales * (benchmark_pct / 100)
        
        balance_ratio = avg_balance / required_balance if required_balance > 0 else 0
        
        if balance_ratio >= 1.0:
            score = 25
        elif balance_ratio >= 0.75:
            score = 20
        elif balance_ratio >= 0.5:
            score = 10
            issues.append(f"Low bank balance: ₹{avg_balance:,.0f} (need ₹{required_balance:,.0f})")
        else:
            score = 0
            issues.append(f"Critical: Bank balance ₹{avg_balance:,.0f} (need ₹{required_balance:,.0f})")
        
        bounces = data.get('banking_bounce_count', 0)
        if bounces > 0:
            score = max(0, score - (bounces * 2))
            issues.append(f"{bounces} cheque bounce(s)")
        
        return score, issues
    
    @staticmethod
    def _score_completeness(data: Dict[str, Any]) -> float:
        required_fields = [
            'gstr1_filing_date', 'gstr1_total_sales',
            'gstr3b_filing_date', 'gstr3b_total_sales',
            'itr_filing_date', 'itr_net_profit',
            'banking_avg_balance'
        ]
        
        filled = sum(1 for field in required_fields if data.get(field))
        completeness_ratio = filled / len(required_fields)
        
        return completeness_ratio * 25