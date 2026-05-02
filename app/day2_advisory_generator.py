"""
DAY 2 PART 3: ADVISORY GENERATOR
File: app/advisory_generator.py

Generates smart business advisory using:
1. Risk calculation formulas (notice risk, tax exposure, penalties)
2. Claude API for friendly, specific tone
"""

import json
from typing import Dict, Any
from anthropic import Anthropic

class AdvisoryGenerator:
    """Generate business advisory using formulas and LLM."""
    
    def __init__(self):
        self.client = Anthropic()
    
    def generate_advisory(
        self,
        extracted_data: Dict[str, Any],
        scores: Dict[str, Any],
        industry: str,
        client_name: str,
        client_gstin: str
    ) -> str:
        """
        Generate comprehensive advisory message.
        
        Combines:
        1. Risk calculations (formulas)
        2. LLM for formatting and friendly tone
        """
        
        # Calculate risks
        risks = self._calculate_risks(extracted_data, scores)
        
        # Build advisory with LLM
        advisory = self._build_advisory_with_llm(
            risks, extracted_data, scores, industry, client_name
        )
        
        return advisory
    
    @staticmethod
    def _calculate_risks(
        data: Dict[str, Any],
        scores: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculate financial risks and tax exposure.
        
        Formula:
        - Notice Risk = Gap% × 50
        - Tax Exposure = Gap × 30% (assumed effective rate)
        - Penalty = Tax × 150% (worst case)
        """
        
        total_score = scores['total_score']
        gstr3b_sales = data.get('gstr3b_total_sales', 0)
        itr_turnover = data.get('itr_total_turnover', 0)
        itr_profit = data.get('itr_net_profit', 0)
        
        gap = abs(gstr3b_sales - itr_turnover)
        gap_pct = (gap / itr_turnover * 100) if itr_turnover > 0 else 0
        
        # Notice risk = gap% × 50
        notice_risk = min(100, gap_pct * 50)
        
        # Tax exposure = gap × 30% (assumed effective rate)
        tax_exposure = gap * 0.30
        
        # Penalty = tax × 150% (worst case)
        penalty = tax_exposure * 1.5
        
        # Total exposure
        total_exposure = tax_exposure + penalty
        
        # Notice probability
        notice_probability = min(100, notice_risk)
        
        return {
            'gap': gap,
            'gap_pct': gap_pct,
            'notice_risk': notice_risk,
            'notice_probability': notice_probability,
            'tax_exposure': tax_exposure,
            'penalty': penalty,
            'total_exposure': total_exposure,
            'score': total_score,
        }
    
    def _build_advisory_with_llm(
        self,
        risks: Dict[str, Any],
        data: Dict[str, Any],
        scores: Dict[str, Any],
        industry: str,
        client_name: str
    ) -> str:
        """Use Claude API to generate friendly, specific advisory."""
        
        score = risks['score']
        
        # Determine severity
        if score > 75:
            severity = "healthy"
            tone = "congratulatory but proactive"
        elif score > 50:
            severity = "moderate"
            tone = "concerned but helpful"
        else:
            severity = "critical"
            tone = "urgent and supportive"
        
        # Build prompt
        prompt = f"""You are a friendly CA advisor. Generate a brief, specific advisory for a business based on these facts:

Business: {client_name}
Industry: {industry}
Health Score: {score:.0f}/100 ({severity})

**Financial Facts:**
- GST Sales: ₹{data.get('gstr3b_total_sales', 0):,.0f}
- ITR Turnover: ₹{data.get('itr_total_turnover', 0):,.0f}
- GST-ITR Gap: ₹{risks['gap']:,.0f} ({risks['gap_pct']:.1f}%)
- Net Profit: ₹{data.get('itr_net_profit', 0):,.0f}
- Bank Balance: ₹{data.get('banking_avg_balance', 0):,.0f}

**Risk Factors:**
- Notice Risk Probability: {risks['notice_probability']:.0f}%
- Tax Exposure: ₹{risks['tax_exposure']:,.0f}
- Penalty Risk: ₹{risks['penalty']:,.0f}
- Total Risk Exposure: ₹{risks['total_exposure']:,.0f}

**Issues Found:**
{chr(10).join(f'- {issue}' for issue in scores.get('issues', []))}

Generate 3-4 short paragraphs:
1. Health verdict (score interpretation)
2. 2-3 specific issues with rupee amounts and risk percentages
3. 2-3 concrete actions with deadline (Oct 20, 2025)
4. Financial benefit if fixed (savings amount)

Tone: {tone}
Be specific. Use actual rupee amounts. Make it sound like a CA wrote it personally.
Keep it under 200 words. Use ₹ symbol for currency."""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return response.content[0].text
        except Exception as e:
            print(f"LLM error: {e}")
            return AdvisoryGenerator._fallback_advisory(score, risks, data)
    
    @staticmethod
    def _fallback_advisory(score: float, risks: Dict[str, Any], data: Dict[str, Any]) -> str:
        """Fallback advisory if LLM fails."""
        
        if score > 75:
            return f"""Your business is healthy (Score: {score:.0f}/100).

Keep maintaining your excellent compliance and financial records. Monitor GST and ITR filings to stay on track.

Continue maintaining your current bank balance levels to ensure smooth operations."""
        
        elif score > 50:
            issues = []
            
            if risks['gap'] > 100000:
                issues.append(f"GST-ITR gap of ₹{risks['gap']:,.0f} ({risks['gap_pct']:.1f}%) needs reconciliation\n   Risk: {risks['notice_probability']:.0f}% notice probability, ₹{risks['tax_exposure']:,.0f} tax + ₹{risks['penalty']:,.0f} penalty")
            
            if risks['notice_probability'] > 30:
                issues.append(f"Notice risk is {risks['notice_probability']:.0f}%. Prepare documentation to defend if audited.")
            
            advisory = f"""Your business needs attention (Score: {score:.0f}/100).

**Issues to fix:**
{chr(10).join(f'{issue}' for issue in issues)}

**Immediate Actions:**
1. Reconcile GST and ITR records by Oct 20, 2025
2. Increase bank balance to ₹{data.get('banking_avg_balance', 500000) * 1.2:,.0f}
3. File all pending returns immediately

**Benefit if fixed:** Save ₹{risks['tax_exposure'] + risks['penalty']:,.0f}"""
            return advisory
        
        else:
            return f"""🚨 Your business is at risk (Score: {score:.0f}/100).

**URGENT: Total tax exposure ₹{risks['total_exposure']:,.0f}**

GST-ITR gap ₹{risks['gap']:,.0f} with {risks['notice_probability']:.0f}% notice probability.

**Immediate Actions (This Week):**
1. Contact your accountant urgently
2. Prepare reconciliation for GST-ITR gap
3. Gather all invoices and bank statements for last 3 months

**Deadline:** Oct 20, 2025 (Last date for corrections)

**Benefit if you act now:** Save ₹{risks['total_exposure']:,.0f} in taxes and penalties"""
