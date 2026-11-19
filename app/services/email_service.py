import os
from typing import Optional, Dict, Any
import httpx


RESEND_API_URL = "https://api.resend.com/emails"


def _get_frontend_url() -> str:
    return (
        os.getenv("FRONTEND_URL")
        or os.getenv("NEXT_PUBLIC_APP_URL")
        or "https://ruvexisolutions.com"
    ).rstrip("/")


def _wrap_ruvexi_email(title: str, subtitle: str, body_html: str) -> str:
    frontend_url = _get_frontend_url()
    logo_url = f"{frontend_url}/logo.png"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background-color:#080808;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#F8FAFC;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color:#080808;padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background-color:#111111;border:1px solid #27272A;border-radius:20px;overflow:hidden;">
          <tr>
            <td style="padding:28px 32px 20px;border-bottom:1px solid #27272A;background:linear-gradient(180deg,#181818 0%,#111111 100%);text-align:center;">
              <img src="{logo_url}" alt="Ruvexi" width="48" height="48" style="display:inline-block;border-radius:12px;border:1px solid rgba(250,204,21,0.35);margin-bottom:12px;" />
              <div style="font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#FACC15;font-weight:700;">RUVEXI SOLUTIONS</div>
              <h1 style="margin:8px 0 4px;font-size:22px;line-height:1.3;color:#F8FAFC;font-weight:700;">{title}</h1>
              <p style="margin:0;font-size:13px;color:#A1A1AA;">{subtitle}</p>
            </td>
          </tr>
          <tr>
            <td style="padding:28px 32px;font-size:14px;line-height:1.6;color:#E4E4E7;">
              {body_html}
            </td>
          </tr>
          <tr>
            <td style="padding:18px 32px;border-top:1px solid #27272A;background-color:#0B0B0B;text-align:center;font-size:11px;color:#717171;">
              Sent securely by Ruvexi Solutions &middot; Luxury Salon Operating System
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def send_email_via_resend(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Sends a transactional email via Resend REST API.
    Requires RESEND_API_KEY in environment variables.
    """
    api_key = (os.getenv("RESEND_API_KEY") or "").strip()
    if not api_key:
        print(f"[Resend] RESEND_API_KEY not configured. Skipped email to {to_email} ({subject}).")
        return {"sent": False, "error": "RESEND_API_KEY is not configured on the server."}

    from_email = (
        os.getenv("RESEND_FROM_EMAIL")
        or "Ruvexi Solutions <noreply@ruvexisolutions.com>"
    ).strip()

    payload: Dict[str, Any] = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    }
    if text_body:
        payload["text"] = text_body

    try:
        with httpx.Client(timeout=10.0) as client:
            res = client.post(
                RESEND_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        data = res.json() if res.content else {}
        if res.status_code in (200, 201):
            return {"sent": True, "id": data.get("id"), "error": None}
        err_msg = data.get("message") or data.get("error") or f"Resend HTTP {res.status_code}"
        print(f"[Resend] Failed sending email to {to_email}: {err_msg}")
        return {"sent": False, "error": err_msg}
    except Exception as exc:
        print(f"[Resend] Exception sending email to {to_email}: {exc}")
        return {"sent": False, "error": str(exc)}


def send_staff_invitation_email(
    to_email: str,
    salon_name: str,
    inviter_name: str,
    invite_token: str,
    branch_name: Optional[str] = None,
) -> Dict[str, Any]:
    frontend_url = _get_frontend_url()
    join_url = f"{frontend_url}/join/{invite_token}"
    branch_line = f" ({branch_name})" if branch_name else ""

    body_html = f"""
      <p style="margin:0 0 16px;">Hello,</p>
      <p style="margin:0 0 18px;">
        <strong>{inviter_name}</strong> has invited you to join <strong>{salon_name}{branch_line}</strong> as a
        <strong>Salon Receptionist</strong> on Ruvexi.
      </p>
      <div style="text-align:center;margin:26px 0;">
        <a href="{join_url}" style="display:inline-block;padding:14px 28px;background-color:#FACC15;color:#080808;font-weight:700;font-size:14px;text-decoration:none;border-radius:12px;">
          Accept Invitation &amp; Create Account &rarr;
        </a>
      </div>
      <p style="margin:0 0 8px;font-size:12px;color:#A1A1AA;">
        Or copy and open this link in your browser (valid for 48 hours):
      </p>
      <p style="margin:0;padding:10px 12px;background:#181818;border:1px solid #27272A;border-radius:8px;font-family:monospace;font-size:12px;word-break:break-all;color:#FACC15;">
        {join_url}
      </p>
    """
    html = _wrap_ruvexi_email(
        title=f"Join {salon_name}",
        subtitle="Staff Invitation • Salon Receptionist Access",
        body_html=body_html,
    )
    text = (
        f"{inviter_name} invited you to join {salon_name}{branch_line} on Ruvexi.\n\n"
        f"Accept your invitation (valid for 48 hours): {join_url}"
    )
    return send_email_via_resend(
        to_email=to_email,
        subject=f"You're invited to join {salon_name} on Ruvexi",
        html_body=html,
        text_body=text,
    )


def send_password_reset_email(
    to_email: str,
    user_name: str,
    reset_token: str,
) -> Dict[str, Any]:
    frontend_url = _get_frontend_url()
    reset_url = f"{frontend_url}/reset-password?token={reset_token}"
    body_html = f"""
      <p style="margin:0 0 16px;">Hi {user_name or 'there'},</p>
      <p style="margin:0 0 18px;">
        We received a request to reset the password for your Ruvexi account. Click the button below to choose a new password.
      </p>
      <div style="text-align:center;margin:26px 0;">
        <a href="{reset_url}" style="display:inline-block;padding:14px 28px;background-color:#FACC15;color:#080808;font-weight:700;font-size:14px;text-decoration:none;border-radius:12px;">
          Reset Password &rarr;
        </a>
      </div>
      <p style="margin:0;font-size:12px;color:#A1A1AA;">
        This link expires in 1 hour. If you did not request a password reset, you can safely ignore this email.
      </p>
    """
    html = _wrap_ruvexi_email(
        title="Reset Your Password",
        subtitle="Ruvexi Account Security",
        body_html=body_html,
    )
    text = f"Reset your Ruvexi password (valid for 1 hour): {reset_url}"
    return send_email_via_resend(
        to_email=to_email,
        subject="Reset your Ruvexi password",
        html_body=html,
        text_body=text,
    )


def send_otp_email(
    to_email: str,
    user_name: str,
    otp_code: str,
) -> Dict[str, Any]:
    body_html = f"""
      <p style="margin:0 0 16px;">Hi {user_name or 'there'},</p>
      <p style="margin:0 0 18px;">
        Use the 6-digit verification code below to sign in to your Ruvexi salon workspace:
      </p>
      <div style="text-align:center;margin:24px 0;">
        <div style="display:inline-block;padding:16px 32px;background:#181818;border:1px solid rgba(250,204,21,0.4);border-radius:14px;font-family:monospace;font-size:30px;font-weight:800;letter-spacing:8px;color:#FACC15;">
          {otp_code}
        </div>
      </div>
      <p style="margin:0;font-size:12px;color:#A1A1AA;">
        This code expires in 5 minutes. Never share your verification code with anyone.
      </p>
    """
    html = _wrap_ruvexi_email(
        title="Your Ruvexi Sign-In Code",
        subtitle="6-Digit Security Verification",
        body_html=body_html,
    )
    text = f"Your Ruvexi verification code is: {otp_code} (valid for 5 minutes)."
    return send_email_via_resend(
        to_email=to_email,
        subject=f"{otp_code} is your Ruvexi verification code",
        html_body=html,
        text_body=text,
    )


def send_welcome_email(
    to_email: str,
    user_name: str,
    salon_name: str,
) -> Dict[str, Any]:
    frontend_url = _get_frontend_url()
    body_html = f"""
      <p style="margin:0 0 16px;">Welcome to Ruvexi, <strong>{user_name or 'Partner'}</strong>!</p>
      <p style="margin:0 0 18px;">
        Your salon workspace <strong>{salon_name}</strong> is ready. You can now manage appointments, POS billing,
        staff commissions, and client bookings from one place.
      </p>
      <div style="text-align:center;margin:26px 0;">
        <a href="{frontend_url}/overview" style="display:inline-block;padding:14px 28px;background-color:#FACC15;color:#080808;font-weight:700;font-size:14px;text-decoration:none;border-radius:12px;">
          Open Salon Dashboard &rarr;
        </a>
      </div>
    """
    html = _wrap_ruvexi_email(
        title=f"Welcome to Ruvexi, {salon_name}",
        subtitle="Your Salon Workspace is Live",
        body_html=body_html,
    )
    text = f"Welcome to Ruvexi! Your workspace for {salon_name} is ready at {frontend_url}/overview"
    return send_email_via_resend(
        to_email=to_email,
        subject=f"Welcome to Ruvexi — {salon_name} is live!",
        html_body=html,
        text_body=text,
    )

