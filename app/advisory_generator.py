"""
Advisory Generator - Generate business advisory
Copy entire content to: C:\vertibis-backend\app\advisory_generator.py
"""

from typing import Dict, Any


class AdvisoryGenerator:
    
    @staticmethod
    def generate_advisory(
        extracted_data: Dict[str, Any],
        scores: Dict[str, Any],
        industry: str,
        client_name: str
    ) -> str:
        
        risks = AdvisoryGenerator._calculate_risks(extracted_data, scores)
        return AdvisoryGenerator._build_advisory(risks, extracted_data, scores, client_name)
    
    @staticmethod
    def _calculate_risks(
        data: Dict[str, Any],
        scores: Dict[str, Any]
    ) -> Dict[str, Any]:
        
        total_score = scores['total_score']
        gstr3b_sales = data.get('gstr3b_total_sales', 0)
        itr_turnover = data.get('itr_total_turnover', 0)
        
        gap = abs(gstr3b_sales - itr_turnover)
        gap_pct = (gap / itr_turnover * 100) if itr_turnover > 0 else 0
        
        notice_risk = min(100, gap_pct * 50)
        tax_exposure = gap * 0.30
        penalty = tax_exposure * 1.5
        total_exposure = tax_exposure + penalty
        
        return {
            'gap': gap,
            'gap_pct': gap_pct,
            'notice_risk': notice_risk,
            'tax_exposure': tax_exposure,
            'penalty': penalty,
            'total_exposure': total_exposure,
            'score': total_score,
        }
    
    @staticmethod
    def _build_advisory(
        risks: Dict[str, Any],
        data: Dict[str, Any],
        scores: Dict[str, Any],
        client_name: str
    ) -> str:
        
        score = risks['score']
        
        if score > 75:
            status = "HEALTHY"
        elif score > 50:
            status = "MODERATE"
        else:
            status = "CRITICAL"
        
        advisory = f"Your business health score is {score:.0f}/100 - {status}.\n\n"
        
        if risks['gap'] > 100000:
            advisory += f"GST-ITR gap: ₹{risks['gap']:,.0f} ({risks['gap_pct']:.1f}%)\n"
            advisory += f"Notice risk: {risks['notice_risk']:.0f}%\n"
            advisory += f"Tax exposure: ₹{risks['tax_exposure']:,.0f}\n"
            advisory += f"Penalty risk: ₹{risks['penalty']:,.0f}\n\n"
        
        if risks['notice_risk'] > 30:
            advisory += f"ACTION: Reconcile GST and ITR by Oct 20, 2025.\n"
            advisory += f"BENEFIT: Save ₹{risks['total_exposure']:,.0f} if fixed.\n\n"
        
        advisory += "Recommendation: Contact your CA for assistance."
        
        return advisory