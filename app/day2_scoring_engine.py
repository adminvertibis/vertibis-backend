"""
DAY 2 PART 2: SCORING ENGINE
File: app/scoring_engine.py

Calculates health score with industry-aware logic and benchmarks.
Industry: Manufacturing, Trading, Services, IT
Turnover: Small (<50L), Medium (50L-5Cr), Large (>5Cr)
"""

from datetime import datetime
from typing import Dict, Any, Tuple
from enum import Enum

class Industry(str, Enum):
    MANUFACTURING = "manufacturing"
    TRADING = "trading"
    SERVICES = "services"
    IT = "it"

class TurnoverSize(str, Enum):
    SMALL = "small"      # <50L
    MEDIUM = "medium"    # 50L-5Cr
    LARGE = "large"      # >5Cr

class ScoringEngine:
    """Calculate business health score with industry awareness."""
    
    # Profit margin benchmarks (% of turnover)
    PROFIT_BENCHMARKS = {
        Industry.MANUFACTURING: {"min": 3, "good": 8, "excellent": 12},
        Industry.TRADING: {"min": 5, "good": 12, "excellent": 18},
        Industry.SERVICES: {"min": 15, "good": 25, "excellent": 35},
        Industry.IT: {"min": 20, "good": 30, "excellent": 40},
    }
    
    # Bank balance as % of monthly sales (how many months of buffer)
    BALANCE_BENCHMARKS = {
        Industry.MANUFACTURING: 12,  # 12% of monthly sales
        Industry.TRADING: 10,
        Industry.SERVICES: 15,
        Industry.IT: 20,
    }
    
    # GST-ITR gap tolerance %
    GAP_TOLERANCE = {
        Industry.MANUFACTURING: 5,
        Industry.TRADING: 3,
        Industry.SERVICES: 2,
        Industry.IT: 1,
    }
    
    @staticmethod
    def calculate_score(
        extracted_data: Dict[str, Any],
        industry: Industry,
        turnover_size: TurnoverSize
    ) -> Dict[str, Any]:
        """
        Calculate comprehensive health score (0-100).
        
        Returns:
            {
                'total_score': 0-100,
                'gst_itc_score': 0-25,
                'filing_score': 0-25,
                'cashflow_score': 0-25,
                'completeness_score': 0-25,
                'components': {...},
                'issues': [...]
            }
        """
        
        scores = {}
        issues = []
        
        # Component 1: GST-ITR Consistency (0-25 points)
        gst_itc_score, gap_issues = ScoringEngine._score_gst_itc_match(
            extracted_data, industry
        )
        scores['gst_itc_score'] = gst_itc_score
        issues.extend(gap_issues)
        
        # Component 2: Filing Timeliness (0-25 points)
        filing_score, filing_issues = ScoringEngine._score_filing_timeliness(
            extracted_data
        )
        scores['filing_score'] = filing_score
        issues.extend(filing_issues)
        
        # Component 3: Cashflow Health (0-25 points)
        cashflow_score, cashflow_issues = ScoringEngine._score_cashflow_health(
            extracted_data, industry, turnover_size
        )
        scores['cashflow_score'] = cashflow_score
        issues.extend(cashflow_issues)
        
        # Component 4: Data Completeness (0-25 points)
        completeness_score = ScoringEngine._score_completeness(extracted_data)
        scores['completeness_score'] = completeness_score
        
        # Total score
        total_score = (
            gst_itc_score + filing_score + cashflow_score + completeness_score
        )
        
        return {
            'total_score': min(100, max(0, total_score)),
            'components': scores,
            'issues': issues,
            'industry': industry.value,
            'turnover_size': turnover_size.value,
        }
    
    @staticmethod
    def _score_gst_itc_match(
        data: Dict[str, Any],
        industry: Industry
    ) -> Tuple[float, list]:
        """Score GST vs ITR sales consistency."""
        issues = []
        
        gstr3b_sales = data.get('gstr3b_total_sales', 0)
        itr_turnover = data.get('itr_total_turnover', 0)
        
        if not gstr3b_sales or not itr_turnover:
            return 15, ["Missing GST or ITR sales data"]
        
        # Calculate gap %
        gap_pct = abs(gstr3b_sales - itr_turnover) / itr_turnover * 100
        tolerance = ScoringEngine.GAP_TOLERANCE.get(industry, 5)
        
        if gap_pct <= tolerance:
            score = 25  # Perfect match
        elif gap_pct <= tolerance * 2:
            score = 20  # Minor variance
        elif gap_pct <= tolerance * 5:
            score = 10  # Significant variance
            gap_amount = abs(gstr3b_sales - itr_turnover)
            issues.append(f"GST-ITR gap ₹{gap_amount:,.0f} ({gap_pct:.1f}%)")
        else:
            score = 0  # Major discrepancy
            gap_amount = abs(gstr3b_sales - itr_turnover)
            issues.append(f"Major GST-ITR gap ₹{gap_amount:,.0f} ({gap_pct:.1f}%)")
        
        return score, issues
    
    @staticmethod
    def _score_filing_timeliness(data: Dict[str, Any]) -> Tuple[float, list]:
        """Score filing timeliness."""
        issues = []
        total_delay_days = 0
        filing_count = 0
        
        # Check GSTR-1 (due 11th of next month)
        gstr1_date = data.get('gstr1_filing_date')
        if gstr1_date:
            due_date = gstr1_date.replace(day=11)
            delay = (gstr1_date - due_date).days
            filing_count += 1
            if delay > 0:
                total_delay_days += delay
                issues.append(f"GSTR-1 filed {delay} days late")
        
        # Check GSTR-3B (due 20th of next month)
        gstr3b_date = data.get('gstr3b_filing_date')
        if gstr3b_date:
            due_date = gstr3b_date.replace(day=20)
            delay = (gstr3b_date - due_date).days
            filing_count += 1
            if delay > 0:
                total_delay_days += delay
                issues.append(f"GSTR-3B filed {delay} days late")
        
        # Check ITR (due July 31)
        itr_date = data.get('itr_filing_date')
        if itr_date:
            due_date = itr_date.replace(month=7, day=31)
            delay = (itr_date - due_date).days
            filing_count += 1
            if delay > 0:
                total_delay_days += delay
                issues.append(f"ITR filed {delay} days late")
        
        # Calculate score
        if filing_count == 0:
            return 15, ["Filing dates not provided"]
        
        avg_delay = total_delay_days / filing_count
        
        if avg_delay <= 0:
            score = 25  # On time
        elif avg_delay <= 5:
            score = 20  # Slightly late
        elif avg_delay <= 15:
            score = 10  # Moderately late
        else:
            score = 0  # Significantly late
        
        return score, issues
    
    @staticmethod
    def _score_cashflow_health(
        data: Dict[str, Any],
        industry: Industry,
        turnover_size: TurnoverSize
    ) -> Tuple[float, list]:
        """Score bank balance health."""
        issues = []
        
        avg_balance = data.get('banking_avg_balance', 0)
        gstr3b_sales = data.get('gstr3b_total_sales', 0)
        
        if not avg_balance or not gstr3b_sales:
            return 15, ["Banking or sales data missing"]
        
        # Calculate monthly average sales
        monthly_sales = gstr3b_sales / 12
        
        # Get benchmark
        benchmark_pct = ScoringEngine.BALANCE_BENCHMARKS.get(industry, 12)
        required_balance = monthly_sales * (benchmark_pct / 100)
        
        # Calculate score
        balance_ratio = avg_balance / required_balance if required_balance > 0 else 0
        
        if balance_ratio >= 1.0:
            score = 25  # Healthy
        elif balance_ratio >= 0.75:
            score = 20  # Adequate
        elif balance_ratio >= 0.5:
            score = 10  # Weak
            issues.append(f"Low bank balance: ₹{avg_balance:,.0f} (need ₹{required_balance:,.0f})")
        else:
            score = 0  # Critical
            issues.append(f"Critical: Bank balance ₹{avg_balance:,.0f} (need ₹{required_balance:,.0f})")
        
        # Check bounces
        bounces = data.get('banking_bounce_count', 0)
        if bounces > 0:
            score = max(0, score - (bounces * 2))  # Deduct 2 points per bounce
            issues.append(f"{bounces} cheque bounce(s)")
        
        return score, issues
    
    @staticmethod
    def _score_completeness(data: Dict[str, Any]) -> float:
        """Score data completeness (0-25 points)."""
        required_fields = [
            'gstr1_filing_date', 'gstr1_total_sales',
            'gstr3b_filing_date', 'gstr3b_total_sales',
            'itr_filing_date', 'itr_net_profit',
            'banking_avg_balance'
        ]
        
        filled = sum(1 for field in required_fields if data.get(field))
        completeness_ratio = filled / len(required_fields)
        
        return completeness_ratio * 25
