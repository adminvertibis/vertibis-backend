"""Generate money-impact advisory for MSME health reports."""

from typing import Any, Dict


class AdvisoryGenerator:
    @staticmethod
    def generate_advisory(
        extracted_data: Dict[str, Any],
        scores: Dict[str, Any],
        industry: str,
        client_name: str,
    ) -> str:
        risks = AdvisoryGenerator._calculate_risks(extracted_data, scores)
        return AdvisoryGenerator._build_advisory(risks, scores, client_name)

    @staticmethod
    def _calculate_risks(data: Dict[str, Any], scores: Dict[str, Any]) -> Dict[str, Any]:
        total_score = float(scores["total_score"])
        metrics = scores.get("metrics", {})
        gstr3b_sales = float(data.get("gstr3b_total_sales") or 0)
        itr_turnover = float(data.get("itr_total_turnover") or 0)
        gap = abs(gstr3b_sales - itr_turnover)
        gap_pct = (gap / itr_turnover * 100) if itr_turnover > 0 else 0

        tax_exposure = gap * 0.18
        penalty_risk = tax_exposure * 1.5
        working_capital_gap = max(0, 1 - float(metrics.get("cash_buffer_months") or 0)) * max(gstr3b_sales / 12, 0)

        return {
            "score": total_score,
            "gap": gap,
            "gap_pct": gap_pct,
            "tax_exposure": tax_exposure,
            "penalty_risk": penalty_risk,
            "working_capital_gap": working_capital_gap,
            "metrics": metrics,
        }

    @staticmethod
    def _build_advisory(risks: Dict[str, Any], scores: Dict[str, Any], client_name: str) -> str:
        score = risks["score"]
        if score >= 80:
            status = "STRONG"
            opening = "The business is in a strong band and can use the report for lender or vendor discussions."
        elif score >= 65:
            status = "MODERATE"
            opening = "The business is acceptable, but a few corrections can improve lending terms and client confidence."
        elif score >= 50:
            status = "RISK"
            opening = "The business has elevated risk signals that should be corrected before loan or vendor review."
        else:
            status = "HIGH RISK"
            opening = "The business needs immediate intervention before this report is shared externally."

        lines = [
            f"{client_name} has a Vertibis Business Health Score of {score:.0f}/100 ({status}).",
            opening,
            "",
            "Money impact:",
        ]

        if risks["gap"] > 100000:
            lines.append(
                f"- GST-ITR turnover gap is Rs {risks['gap']:,.0f} ({risks['gap_pct']:.1f}%). "
                f"Potential tax and penalty exposure can reach about Rs {risks['tax_exposure'] + risks['penalty_risk']:,.0f} if not reconciled."
            )
        else:
            lines.append("- No large GST-ITR exposure was detected from the available data.")

        if risks["working_capital_gap"] > 0:
            lines.append(
                f"- Cash buffer is below the preferred level. Estimated working-capital comfort gap is Rs {risks['working_capital_gap']:,.0f}."
            )

        lines.extend(
            [
                "",
                "Action plan:",
                "1. Reconcile GST, ITR, and banking turnover before the next client or lender discussion.",
                "2. Ask the CA/consultant to certify corrected GST-ITR alignment where a variance exists.",
                "3. Build a 30-60-90 day improvement plan covering filing discipline, ITC hygiene, and cash buffer.",
                "4. Regenerate the report after corrections so the score movement is visible to the client.",
            ]
        )

        issues = scores.get("issues") or []
        if issues:
            lines.append("")
            lines.append("Priority issues detected:")
            lines.extend(f"- {issue}" for issue in issues[:6])

        return "\n".join(lines)
