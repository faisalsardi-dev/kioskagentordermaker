"""Email sending via Resend (transactional, send-only).

DB-free by design — like jwtmanager.py, this module must NOT import
sqlmanager. It does one job: send a verification email containing a
6-digit code. The caller (a route in mainfast.py) generates the code,
stores it, and passes it here to send.

Sending is configured for orderbuilder.tech (root domain), verified in
Resend via DKIM/SPF DNS records. Sender is admin@orderbuilder.tech.
"""

import os
from pathlib import Path

import resend
from dotenv import load_dotenv

ROOT = Path(__file__).parent
load_dotenv(ROOT / "kisoskagentapi.env")

resend.api_key = os.getenv("resendapikey")

SENDER = "admin@orderbuilder.tech"
CODE_TTL_MINUTES = 15  # informational only; the route owns the real expiry


def send_verification_email(to_email: str, code: str) -> bool:
    """Send a verification email with the 6-digit code.

    Returns True if Resend accepted the send, False on any error.
    Never raises — the caller checks the bool and decides what the user sees.
    """
    if not resend.api_key:
        # Misconfiguration: key missing from env. Fail closed.
        return False

    html = f"""
    <div style="font-family: system-ui, sans-serif; max-width: 480px;">
      <h2>Verify your email</h2>
      <p>Your verification code is:</p>
      <p style="font-size: 28px; font-weight: bold; letter-spacing: 4px;">{code}</p>
      <p>Enter this code to finish creating your account.
         It expires in {CODE_TTL_MINUTES} minutes.</p>
      <p style="color: #888; font-size: 12px;">
         If you didn't request this, you can ignore this email.</p>
    </div>
    """

    try:
        resend.Emails.send({
            "from": SENDER,
            "to": to_email,
            "subject": "Your verification code",
            "html": html,
        })
        return True
    except Exception:
        return False