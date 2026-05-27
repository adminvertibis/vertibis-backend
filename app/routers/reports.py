import uuid
from datetime import datetime
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth_utils import get_current_partner
from app.database import get_db
from app.models import Client, CreditTransaction, HealthScore, Partner
from app.pricing_config import get_credit_rule, get_size_band
from app.schemas import ReportUnlockOut, ReportUnlockRequest

router = APIRouter(prefix="/api/v1/reports", tags=["Reports"])


UNLOCKED_STATUSES = {"unlocked", "download_unlocked", "downloaded", "shared"}


def _score_band(score: float) -> str:
    if score >= 75:
        return "Healthy"
    if score >= 50:
        return "Needs Review"
    return "At Risk"


def _build_pdf(client: Client, score: HealthScore, partner: Partner) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=42, leftMargin=42, topMargin=42, bottomMargin=42)
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Vertibis MSME Business Health Report", styles["Title"]))
    story.append(Paragraph(f"Prepared for {client.name}", styles["Heading2"]))
    story.append(Paragraph(f"Prepared by {partner.name}", styles["Normal"]))
    story.append(Spacer(1, 0.18 * inch))

    summary = [
        ["Report Number", score.report_number or str(score.id)],
        ["Report Type", score.report_variant or score.report_type or "MSME Health Report"],
        ["GSTIN", client.gstin or "-"],
        ["Industry", client.industry or "-"],
        ["Score Date", score.score_date.strftime("%d-%m-%Y")],
        ["Health Score", f"{score.total_score:.1f}/100"],
        ["Verdict", _score_band(score.total_score)],
        ["Scoring Version", score.scoring_version or "V2.0"],
        ["Data Completeness", f"{score.data_completeness_pct or 0:.1f}%"],
    ]
    table = Table(summary, colWidths=[2.0 * inch, 4.2 * inch])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f4ff")),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#1e40af")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7e8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(table)
    story.append(Spacer(1, 0.22 * inch))

    components = [
        ["Component", "Score"],
        ["GST Integrity", score.gst_integrity_score if score.gst_integrity_score is not None else "-"],
        ["ITR Consistency", score.itr_consistency_score if score.itr_consistency_score is not None else "-"],
        ["Cashflow Health", score.cashflow_health_score if score.cashflow_health_score is not None else "-"],
        ["Compliance Behaviour", score.compliance_behaviour_score if score.compliance_behaviour_score is not None else "-"],
        ["Data Credibility", score.data_credibility_score if score.data_credibility_score is not None else "-"],
    ]
    comp_table = Table(components, colWidths=[3.2 * inch, 3.0 * inch])
    comp_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0066cc")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d0d7e8")),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(Paragraph("Score Breakdown", styles["Heading2"]))
    story.append(comp_table)
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("Key Issues", styles["Heading2"]))
    issues = score.issues or []
    if issues:
        for issue in issues:
            story.append(Paragraph(f"- {issue}", styles["Normal"]))
    else:
        story.append(Paragraph("No major issues detected from available data.", styles["Normal"]))
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("Advisory Summary", styles["Heading2"]))
    for para in (score.advisory or "No advisory generated.").split("\n"):
        if para.strip():
            story.append(Paragraph(para.strip(), styles["Normal"]))
            story.append(Spacer(1, 0.08 * inch))

    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph("Compliance Note", styles["Heading2"]))
    story.append(Paragraph("This report is generated after client consent from uploaded or API-sourced data. It is analytical and advisory in nature, not a credit rating, loan approval, or legal opinion. Banks, NBFCs, enterprises, and advisors may conduct independent verification.", styles["Normal"]))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


@router.get("/{score_id}/download", summary="Download detailed PDF report")
def download_report(
    score_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_partner: Partner = Depends(get_current_partner),
):
    row = (
        db.query(HealthScore, Client)
        .join(Client, HealthScore.client_id == Client.id)
        .filter(HealthScore.id == score_id, Client.partner_id == current_partner.id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    score, client = row
    if score.report_status not in UNLOCKED_STATUSES:
        raise HTTPException(status_code=402, detail="Report is ready but locked. Unlock final download/share/export with credits first.")

    if score.report_status != "downloaded":
        score.report_status = "downloaded"
        score.downloaded_at = datetime.utcnow()
        db.commit()

    pdf = _build_pdf(client, score, current_partner)
    identifier = score.report_number or str(score.id)
    filename = f"vertibis-report-{client.name.replace(' ', '-')}-{identifier}.pdf"
    return StreamingResponse(
        BytesIO(pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _unlock_economics(score: HealthScore, client: Client, payload: ReportUnlockRequest | None):
    requested_size = payload.client_size_band if payload else None
    band = get_size_band(requested_size or score.client_size_band or score.turnover_band, client.turnover)
    if not band:
        raise HTTPException(status_code=422, detail="Client size is missing. Add turnover or select client size before unlocking.")

    rule = get_credit_rule(score.report_type, band.name, client.turnover)
    if not rule or rule.credits_required is None:
        raise HTTPException(status_code=422, detail="Credits for this report and client size are custom. Ask admin to configure or override it.")

    credits_required = int(score.credits_required or rule.credits_required or 0)
    if credits_required <= 0:
        credits_required = int(rule.credits_required or 0)

    return band.name, credits_required, rule.suggested_fee_min, rule.suggested_fee_max


@router.post("/{score_id}/unlock-download", response_model=ReportUnlockOut, summary="Spend report credits to unlock final report download")
def unlock_report_download(
    score_id: uuid.UUID,
    payload: ReportUnlockRequest | None = None,
    db: Session = Depends(get_db),
    current_partner: Partner = Depends(get_current_partner),
):
    row = (
        db.query(HealthScore, Client)
        .join(Client, HealthScore.client_id == Client.id)
        .filter(HealthScore.id == score_id, Client.partner_id == current_partner.id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    score, client = row
    if score.report_status in UNLOCKED_STATUSES:
        return ReportUnlockOut(
            report_id=score.id,
            report_status=score.report_status,
            credits_remaining=current_partner.credits_balance,
            credits_required=score.credits_required or score.credits_used or 0,
            credits_used=score.credits_used or 0,
            client_size_band=score.client_size_band or score.turnover_band,
            suggested_fee_min=score.suggested_fee_min,
            suggested_fee_max=score.suggested_fee_max,
            download_url=f"/api/v1/reports/{score.id}/download",
        )

    client_size_band, credits_required, suggested_fee_min, suggested_fee_max = _unlock_economics(score, client, payload)

    if current_partner.credits_balance < credits_required:
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient credits. Required {credits_required}, available {current_partner.credits_balance}.",
        )

    current_partner.credits_balance -= credits_required
    score.client_size_band = client_size_band
    score.turnover_band = client_size_band
    score.credits_required = credits_required
    score.credits_used = credits_required
    score.suggested_fee_min = suggested_fee_min
    score.suggested_fee_max = suggested_fee_max
    score.report_status = "unlocked"
    score.unlocked_at = datetime.utcnow()
    db.add(CreditTransaction(
        partner_id=current_partner.id,
        transaction_type="report_unlock",
        credits_amount=-credits_required,
        balance_after=current_partner.credits_balance,
        related_client_id=client.id,
        related_health_score_id=score.id,
        description=f"Report unlock for {client.name}",
        remarks=f"{score.report_variant or score.report_type} | {client_size_band}",
        created_by=str(current_partner.id),
    ))
    db.commit()

    return ReportUnlockOut(
        report_id=score.id,
        report_status=score.report_status,
        credits_remaining=current_partner.credits_balance,
        credits_required=credits_required,
        credits_used=credits_required,
        client_size_band=client_size_band,
        suggested_fee_min=suggested_fee_min,
        suggested_fee_max=suggested_fee_max,
        download_url=f"/api/v1/reports/{score.id}/download",
    )
