"""Outbound verification messages.

Email uses Brevo (transactional SMTP or the Brevo HTTP API). SMS is pluggable
via ``SMS_BACKEND`` so a real provider can be dropped in with config only —
there is no genuinely free SMS provider, so the default is a console backend
that logs the code instead of sending it.

All senders return ``(ok, detail)`` and never raise: a delivery failure must
not take down the request that triggered it.
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"

PURPOSE_LABELS = {
    "register": "activate your account",
    "login": "confirm your sign-in",
    "invest": "confirm your investment",
    "withdraw": "confirm your withdrawal",
    "kyc": "verify your identity",
    "change_contact": "change your contact details",
}


def purpose_label(purpose):
    return PURPOSE_LABELS.get(purpose, "verify this action")


def _brand():
    return getattr(settings, "BRAND_NAME", "MYX app")


# --------------------------------------------------------------------- email
def _email_payload(to_email, subject, text, html):
    name = getattr(settings, "BRAND_NAME", "MYX app")
    sender_email = getattr(settings, "BREVO_SENDER_EMAIL", "") or (
        getattr(settings, "DEFAULT_FROM_EMAIL", "") or ""
    )
    sender_name = getattr(settings, "BREVO_SENDER_NAME", "") or name
    if "<" in sender_email and ">" in sender_email:
        sender_email = sender_email.split("<", 1)[1].split(">", 1)[0].strip()
    return {
        "sender": {"name": sender_name, "email": sender_email},
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": text,
        "htmlContent": html,
    }


def _send_brevo_api(api_key, to_email, subject, text, html):
    body = json.dumps(_email_payload(to_email, subject, text, html)).encode("utf-8")
    req = urllib.request.Request(
        BREVO_API_URL,
        data=body,
        method="POST",
        headers={
            "api-key": api_key,
            "Content-Type": "application/json",
            "accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                message_id = json.loads(raw).get("messageId", "")
            except ValueError:
                message_id = ""
            logger.info("brevo: sent email to %s id=%s", to_email, message_id)
            return True, "sent"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        logger.error("brevo: HTTP %s for %s: %s", exc.code, to_email, detail)
        return False, f"brevo {exc.code}"
    except Exception as exc:  # noqa: BLE001 - delivery must never raise
        logger.error("brevo: failed for %s: %s", to_email, exc)
        return False, "brevo request failed"


def _send_smtp(to_email, subject, text, html):
    try:
        send_mail(
            subject,
            text,
            getattr(settings, "DEFAULT_FROM_EMAIL", None) or None,
            [to_email],
            html_message=html,
            fail_silently=False,
        )
        logger.info("smtp: sent email to %s", to_email)
        return True, "sent"
    except Exception as exc:  # noqa: BLE001
        logger.error("smtp: failed for %s: %s", to_email, exc)
        return False, "smtp failed"


def send_email_code(to_email, code, purpose="register"):
    brand = _brand()
    label = purpose_label(purpose)
    subject = f"{brand} verification code"
    text = (
        f"Your {brand} code is: {code}\n\n"
        f"Use it to {label}. It expires in 10 minutes.\n"
        f"If you did not request this, ignore this email."
    )
    html = f"""
    <div style="font-family:Arial,Helvetica,sans-serif;background:#060504;padding:28px">
      <div style="max-width:520px;margin:0 auto;background:#16120c;border:1px solid #2b2418;
                  border-radius:12px;padding:28px;color:#f6f1e7">
        <p style="font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#a99b85;
                  margin:0 0 6px">{brand}</p>
        <p style="font-size:16px;margin:0 0 18px">Use this code to {label}:</p>
        <p style="margin:0 0 18px">
          <span style="display:inline-block;background:#0e0c08;border:1px solid #2b2418;
                       border-radius:10px;padding:14px 26px;font-size:30px;font-weight:700;
                       letter-spacing:.22em;color:#e3b441">{code}</span>
        </p>
        <p style="font-size:13px;color:#a99b85;margin:0 0 6px">Expires in 10 minutes.</p>
        <p style="font-size:13px;color:#a99b85;margin:0">
          If you did not request this, you can safely ignore this email.
        </p>
      </div>
    </div>
    """
    api_key = (getattr(settings, "BREVO_API_KEY", "") or "").strip()
    if api_key:
        return _send_brevo_api(api_key, to_email, subject, text, html)
    return _send_smtp(to_email, subject, text, html)


# ----------------------------------------------------------------------- sms
def _sms_backend():
    return (getattr(settings, "SMS_BACKEND", "") or "console").strip().lower()


def _send_sms_console(phone, text):
    logger.info("sms/console: %s -> %s", phone, text.replace("\n", " "))
    return True, "logged to console"


def _send_sms_twilio(phone, text):
    account = (getattr(settings, "TWILIO_ACCOUNT_SID", "") or "").strip()
    token = (getattr(settings, "TWILIO_AUTH_TOKEN", "") or "").strip()
    from_number = (getattr(settings, "TWILIO_FROM_NUMBER", "") or "").strip()
    if not (account and token and from_number):
        return False, "twilio not configured"
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account}/Messages.json"
    body = (
        f"From={from_number}&To={phone}&Body={urllib.parse.quote(text)}"
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )

    credentials = base64.b64encode(f"{account}:{token}".encode("utf-8")).decode("ascii")
    req.add_header("Authorization", f"Basic {credentials}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        logger.info("twilio: sent sms to %s", phone)
        return True, "sent"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        logger.error("twilio: HTTP %s for %s: %s", exc.code, phone, detail)
        return False, f"twilio {exc.code}"
    except Exception as exc:  # noqa: BLE001
        logger.error("twilio: failed for %s: %s", phone, exc)
        return False, "twilio request failed"


def send_sms_code(phone, code, purpose="register"):
    brand = _brand()
    label = purpose_label(purpose)
    text = f"{brand} code: {code}. Use it to {label}. Expires in 10 minutes."
    backend = _sms_backend()
    if backend == "twilio":
        return _send_sms_twilio(phone, text)
    if backend in {"none", "disabled", "off"}:
        logger.info("sms/disabled: %s -> %s", phone, code)
        return True, "sms disabled (code logged)"
    return _send_sms_console(phone, text)
