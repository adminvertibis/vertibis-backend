import os
import smtplib
from email.message import EmailMessage


def _smtp_configured() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("FROM_EMAIL"))


def send_email(to_email: str | None, subject: str, body: str) -> bool:
    if not to_email or not _smtp_configured():
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = os.getenv("FROM_EMAIL", "")
    message["To"] = to_email
    message.set_content(body)

    host = os.getenv("SMTP_HOST", "")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() != "false"

    try:
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            if use_tls:
                smtp.starttls()
            if username and password:
                smtp.login(username, password)
            smtp.send_message(message)
        return True
    except Exception as exc:
        print(f"Email send failed: {exc}")
        return False


def send_partner_registration_emails(partner) -> None:
    admin_email = os.getenv("ADMIN_EMAIL")
    login_url = os.getenv("FRONTEND_LOGIN_URL", "")

    send_email(
        partner.email,
        "Vertibis partner registration received",
        (
            f"Hi {partner.contact_name or partner.name},\n\n"
            "We have received your Vertibis partner account request.\n\n"
            f"Firm: {partner.name}\n"
            f"Profession: {partner.profession or partner.firm_type or '-'}\n"
            f"Membership No.: {partner.membership_no or '-'}\n\n"
            "Your account is pending approval. We will email you once it is approved.\n\n"
            "Regards,\nVertibis Team"
        ),
    )

    send_email(
        admin_email,
        "New Vertibis partner registration pending approval",
        (
            "A new partner has registered and is pending approval.\n\n"
            f"Name: {partner.contact_name or '-'}\n"
            f"Firm: {partner.name}\n"
            f"Profession: {partner.profession or partner.firm_type or '-'}\n"
            f"Email: {partner.email}\n"
            f"Phone: {partner.phone or '-'}\n"
            f"Membership No.: {partner.membership_no or '-'}\n"
            f"Login URL: {login_url or '-'}\n"
        ),
    )


def send_partner_approval_email(partner) -> None:
    login_url = os.getenv("FRONTEND_LOGIN_URL", "")
    login_line = f"\nLogin here: {login_url}\n" if login_url else ""
    send_email(
        partner.email,
        "Your Vertibis partner account is approved",
        (
            f"Hi {partner.contact_name or partner.name},\n\n"
            "Your Vertibis partner account has been approved. You can now log in to the partner dashboard."
            f"{login_line}\n"
            "Regards,\nVertibis Team"
        ),
    )
