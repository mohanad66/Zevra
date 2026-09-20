"""Crypto transfer / payment provider.

The platform moves coins through PayRam, a self-hosted crypto gateway. There are
two integration points, switched by the PlatformSetting ``payment_mode``:

* **Investments** (user pays the platform): ``create_payment_order`` creates a
  PayRam payment link (``POST /api/v1/payment``) the user opens to pay. It is
  confirmed by the PayRam webhook (``/api/webhooks/gateway``) and/or polling
  (``confirm_payment``, ``reconcile_gateway``), and can be finalized manually in
  admin.
* **Withdrawals / payouts** (platform pays the user): once an admin approves the
  payout/withdrawal, ``send_platform_to_user`` creates a PayRam payout
  (``POST /api/v1/withdrawal/merchant``). PayRam pushes ``payout.*`` webhooks;
  ``reconcile_gateway()`` (polling — run via ``python manage.py poll_gateway``
  or lazily from the admin orders view) finalizes the on-chain result.

Modes:
    simulate – fake deposit address + fake tx hashes (default)
    provider – PayRam (self-hosted crypto gateway)
    manual   – a human operator moves coins off-line and enters tx hashes in admin

PayRam test / production:
    PayRam instances are environment-specific (a mainnet server vs a testnet
    server), each with its own Site URL and project API key. The active
    environment is chosen by ``payram_mode`` (``PlatformSettings`` / env
    ``PAYRAM_MODE``):

        PAYRAM_MODE                     - "test" (default) | "production"
        PAYRAM_BASE_URL_TEST            - test environment Site URL
        PAYRAM_API_KEY_TEST             - test project API key
        PAYRAM_BASE_URL_PRODUCTION      - production Site URL
        PAYRAM_API_KEY_PRODUCTION       - production project API key

    Webhooks: PayRam POSTs JSON to ``/api/webhooks/gateway`` with the header
    ``X-Payram-Signature: sha256=<hex>`` = HMAC-SHA256 of the raw request body
    keyed with the project API key. The payment and payout webhooks share this
    endpoint.
"""
import hashlib
import hmac
import json
import os
import secrets
import time
from decimal import Decimal

import requests
from django.utils import timezone

from api.models import PlatformSettings

_PAYRAM_ENVS = ("test", "production")


def _provider_setting(key, env_name, default=""):
    """Read provider config from PlatformSettings first, then env."""
    val = PlatformSettings.get(key, "")
    if val is not None and val != "":
        return val
    return os.environ.get(env_name, default)


# ---------------------------------------------------------------------------
# PayRam configuration
# ---------------------------------------------------------------------------


def _payram_env():
    """Active PayRam environment: "test" or "production"."""
    val = _provider_setting(PlatformSettings.S_PAYRAM_MODE, "PAYRAM_MODE", "test")
    val = str(val).lower().strip()
    return val if val in _PAYRAM_ENVS else "test"


def _payram_base_url(env):
    key = (
        PlatformSettings.S_PAYRAM_BASE_URL_PROD
        if env == "production"
        else PlatformSettings.S_PAYRAM_BASE_URL_TEST
    )
    env_name = (
        "PAYRAM_BASE_URL_PRODUCTION"
        if env == "production"
        else "PAYRAM_BASE_URL_TEST"
    )
    return _provider_setting(key, env_name).strip().rstrip("/")


def _payram_api_key(env):
    key = (
        PlatformSettings.S_PAYRAM_API_KEY_PROD
        if env == "production"
        else PlatformSettings.S_PAYRAM_API_KEY_TEST
    )
    env_name = (
        "PAYRAM_API_KEY_PRODUCTION"
        if env == "production"
        else "PAYRAM_API_KEY_TEST"
    )
    return _provider_setting(key, env_name).strip()


def _payram_active():
    """Return (env, base_url, api_key) for the active PayRam environment."""
    env = _payram_env()
    return env, _payram_base_url(env), _payram_api_key(env)


# ---------------------------------------------------------------------------
# PayRam HTTP helpers
# ---------------------------------------------------------------------------


def _payram_url(base_url, endpoint):
    base_url = str(base_url or "").strip()
    if not base_url.startswith(("http://", "https://")):
        raise ValueError(
            "PayRam BASE_URL must start with http:// or https:// "
            "(admin: Payments -> PayRam, or PAYRAM_BASE_URL_* env vars)."
        )
    return f"{base_url}/api/v1{endpoint}"


def _payram_headers(api_key):
    return {
        "API-Key": api_key,
        "Content-Type": "application/json",
    }


def _payram_error(payload, r):
    """Best-effort human-readable error message from a PayRam error response."""
    if isinstance(payload, dict):
        message = payload.get("message") or payload.get("error")
        if message:
            return str(message)[:300]
    return r.text[:300]


def _payram_post(endpoint, body, api_key, idempotency_key=None):
    """POST to the PayRam API. Raises ValueError on non-2xx. Returns JSON dict."""
    headers = _payram_headers(api_key)
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    try:
        r = requests.post(
            f"{_payram_url(_py_post_base(), endpoint)}",
            data=json.dumps(body, separators=(",", ":")),
            headers=headers,
            timeout=30,
        )
    except requests.RequestException as exc:
        raise ValueError(f"PayRam unreachable: {exc}") from exc
    try:
        payload = r.json()
    except ValueError:
        payload = {}
    if r.status_code >= 300:
        raise ValueError(f"PayRam HTTP {r.status_code}: {_payram_error(payload, r)}")
    return payload


def _payram_get(endpoint, api_key):
    """GET from the PayRam API. Raises ValueError on non-2xx. Returns JSON."""
    try:
        r = requests.get(
            _payram_url(_py_get_base(), endpoint),
            headers=_payram_headers(api_key),
            timeout=30,
        )
    except requests.RequestException as exc:
        raise ValueError(f"PayRam unreachable: {exc}") from exc
    try:
        payload = r.json()
    except ValueError:
        payload = {}
    if r.status_code >= 300:
        raise ValueError(f"PayRam HTTP {r.status_code}: {_payram_error(payload, r)}")
    return payload


def _py_post_base():
    """Active PayRam BASE_URL used for writes (kept in one place)."""
    _, base, _ = _payram_active()
    return base


def _py_get_base():
    """Active PayRam BASE_URL used for reads (kept in one place)."""
    return _py_post_base()


def _mode():
    mode = PlatformSettings.get("payment_mode", "simulate").lower()
    return mode if mode in {"simulate", "provider", "manual"} else "simulate"


def _provider_ready():
    """(ok, message) check for the active PayRam environment."""
    env, base, key = _payram_active()
    if not base:
        return False, "No PayRam BASE_URL configured for the active environment."
    if not key:
        return False, "No PayRam API key configured for the active environment."
    return True, f"PayRam ({env}) configured."


# ---------------------------------------------------------------------------
# Ticker (USD conversion)
# ---------------------------------------------------------------------------


def _payram_usd_price(coin):
    """Current USD price of one unit of ``coin`` via the PayRam ticker.

    Falls back to the coin's stored reference price when the ticker has no entry.
    """
    _, base, _ = _payram_active()
    rows = None
    if base:
        try:
            rows = _payram_get("/ticker", "")
        except ValueError:
            rows = None
    if isinstance(rows, list):
        for row in rows:
            if str(row.get("currencyCode") or "").upper() == str(coin.symbol).upper():
                price = row.get("price")
                if price is not None:
                    try:
                        return float(price)
                    except (TypeError, ValueError):
                        pass
                break
    try:
        return float(coin.reference_price or 0)
    except (TypeError, ValueError):
        return 0.0


def _payram_usd_amount(coin, amount):
    """Convert a crypto amount to USD (2 decimals) for PayRam payment creation."""
    price = _payram_usd_price(coin)
    if price <= 0:
        raise ValueError(f"No USD price available for {coin.symbol}.")
    return round(float(amount) * price, 2)


# Keyed by the app's coin.chain names.
_PAYRAM_PAYMENT_NETWORKS = {
    "TRC20": "TRX",
    "ERC20": "ETH",
    "BTC": "BTC",
    "BASE": "BASE",
    "POLYGON": "POLYGON",
}

_PAYRAM_PAYOUT_CHAINS = {
    "TRC20": "TRX",
    "ERC20": "ETH",
    "BASE": "BASE",
    "POLYGON": "POLYGON",
}


# ---------------------------------------------------------------------------
# Simulation / manual helpers
# ---------------------------------------------------------------------------


def _simulated_hash(kind):
    return f"SIM-{timezone.now():%Y%m%d%H%M%S}-{secrets.token_hex(6)}"


def _fake_address(coin):
    """Deterministic fake deposit address so simulate mode looks realistic."""
    net = (coin.chain or "TRC20").upper()
    prefix = {"TRC20": "T", "BEP20": "0x", "BEP2": "bnb1", "ERC20": "0x", "SOL": "", "TON": "UQ"}[net]
    return f"{prefix}{secrets.token_hex(20)}"


def _amount_str(coin, amount):
    try:
        return f"{float(amount):.{8}f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(amount)


def send_platform_to_user(coin, to_address, amount, network="", order_ref=None, user=None):
    """Admin/platform wallet -> user wallet. Returns provider ref or ''.

    Used by payouts and withdrawals once admin approves them.
    - provider: creates a PayRam payout and returns its PayRam payout id.
    - manual:   returns '' (a human operator transfers off-line).
    - simulate: returns a fake tx hash.
    """
    amount = float(amount)
    if amount <= 0:
        raise ValueError("Amount must be positive")
    mode = _mode()
    if mode == "manual":
        return ""
    if mode == "provider":
        return _create_payram_payout(coin, to_address, amount, order_ref, user)
    # simulate
    return _simulated_hash("send")


def _create_payram_payout(coin, to_address, amount, order_ref=None, user=None):
    """Create a PayRam payout to the user's address. Returns its PayRam id."""
    env, base, key = _payram_active()
    if not base or not key:
        raise ValueError(
            "PayRam is not configured. Set the BASE_URL and API key for the "
            "active environment in Admin > Payments."
        )
    net = _PAYRAM_PAYOUT_CHAINS.get((coin.chain or "").upper())
    if not net:
        raise ValueError(
            f"PayRam does not support payouts on {coin.chain or coin.symbol}. "
            "Supported chains: ETH, BASE, POLYGON, TRX."
        )
    if user is None:
        raise ValueError("PayRam payouts need a recipient user.")
    body = {
        "email": user.email or f"user{user.pk}@miyartrading.com",
        "blockchainCode": net,
        "currencyCode": str(coin.symbol).upper(),
        "amount": _amount_str(coin, amount),
        "toAddress": to_address,
        "customerID": str(user.pk),
    }
    result = _payram_post(
        "/withdrawal/merchant", body, key, idempotency_key=order_ref
    )
    pid = str(result.get("id") or "")
    if not pid:
        raise ValueError("PayRam created the payout but returned no id.")
    return pid


def _platform_deposit_address(coin):
    """Platform's deposit address for a coin (is_platform CryptoAccount)."""
    from api.models import CryptoAccount
    acc = CryptoAccount.objects.select_related("user").filter(
        coin=coin, is_platform=True
    ).first()
    if acc:
        return acc.address
    return _fake_address(coin)


# ---------------------------------------------------------------------------
# Investment / payment checkout
# ---------------------------------------------------------------------------

_PAYRAM_PAYMENT_PAID = {"FILLED", "OVER_FILLED"}
_PAYRAM_PAYMENT_FAILED = {"CANCELLED"}
_PAYRAM_PAYOUT_DONE = {"SENT", "PROCESSED"}
_PAYRAM_PAYOUT_FAILED = {"FAILED", "REJECTED", "CANCELLED"}


def create_payment_order(investment):
    """Create a payment order for a pending investment.

    Returns the checkout payload the frontend shows the user:
        {"order_ref", "status", "address", "checkout_url", "chain", "amount", "payment_mode"}
    """
    coin = investment.coin
    amount = float(investment.amount)
    mode = _mode()

    common = {
        "coin_symbol": coin.symbol,
        "chain": coin.chain,
        "amount": investment.amount,
        "payment_mode": mode,
    }

    ref = f"ORD-{timezone.now():%Y%m%d%H%M%S}-{secrets.token_hex(4).upper()}"

    if mode == "manual":
        return {"order_ref": ref, "status": "manual", "address": "", "checkout_url": "", **common}

    if mode == "provider":
        return _create_payram_payment(investment, ref)

    # simulate: show the platform's deposit address and confirm on "I paid".
    return {
        "order_ref": ref,
        "status": "pending",
        "address": _platform_deposit_address(coin),
        "checkout_url": "",
        **common,
    }


def _create_payram_payment(investment, order_ref):
    """Create a PayRam payment link for an investment. Returns the checkout payload."""
    coin = investment.coin
    amount = float(investment.amount)
    env, base, key = _payram_active()
    user = investment.user
    common = {
        "coin_symbol": coin.symbol,
        "chain": coin.chain,
        "amount": investment.amount,
        "payment_mode": "provider",
        "order_ref": order_ref,
        "gateway": "payram",
    }
    ok, message = _provider_ready()
    if not ok:
        return {
            "status": "failed",
            "address": "",
            "checkout_url": "",
            "message": message,
            **common,
        }
    try:
        amount_usd = _payram_usd_amount(coin, amount)
    except ValueError as exc:
        return {
            "status": "failed",
            "address": "",
            "checkout_url": "",
            "message": str(exc),
            **common,
        }
    if amount_usd <= 0:
        return {
            "status": "failed",
            "address": "",
            "checkout_url": "",
            "message": "Payment amount must be positive in USD.",
            **common,
        }
    body = {
        "customerEmail": user.email or f"user{user.pk}@miyartrading.com",
        "customerID": str(user.pk),
        "amountInUSD": f"{amount_usd:.2f}",
        "invoiceID": order_ref,
    }
    net = _PAYRAM_PAYMENT_NETWORKS.get((coin.chain or "").upper())
    if net:
        body["network"] = net
        body["currency"] = str(coin.symbol).upper()
    try:
        result = _payram_post("/payment", body, key)
    except ValueError as exc:
        return {
            "status": "failed",
            "address": "",
            "checkout_url": "",
            "message": str(exc),
            **common,
        }
    ref_id = str(result.get("reference_id") or "")
    url = str(result.get("url") or "")
    if not ref_id:
        return {
            "status": "failed",
            "address": "",
            "checkout_url": "",
            "message": "PayRam created the payment but returned no reference_id.",
            **common,
        }
    return {
        "status": "pending",
        "address": "",
        "checkout_url": url,
        "provider_order_id": ref_id,
        "provider_token": ref_id,
        **common,
    }


def _payram_payment_status(reference_id):
    """Poll a PayRam payment by reference id. Returns (state, tx_hash)."""
    _, base, key = _payram_active()
    payload = _payram_get(f"/payment/reference/{reference_id}", key)
    state = str(payload.get("paymentState") or "").upper()
    tx = ""
    info = payload.get("payment_info")
    if isinstance(info, list) and info and isinstance(info[0], dict):
        tx = str(info[0].get("transaction_hash") or "")
    return state, tx


def _payram_payout_status(payout_id):
    """Poll a PayRam merchant payout by id. Returns (status, tx_hash)."""
    _, base, key = _payram_active()
    payload = _payram_get(f"/withdrawal/{payout_id}/merchant", key)
    return (
        str(payload.get("status") or "").upper(),
        str(payload.get("txHash") or ""),
    )


def confirm_payment(order_ref):
    """Confirm a payment order and return (ok, tx_hash, message).

    simulate: trusts the user's confirmation (order was "paid" off-screen).
    provider: polls PayRam; only confirms when the payment is filled.
    manual:   never auto-confirms (handled by an admin).
    """
    from api.models import PaymentOrder

    mode = _mode()
    order = PaymentOrder.objects.filter(order_ref=order_ref).first()
    if order is None:
        return False, "", "Payment order not found."
    if order.status == PaymentOrder.STATUS_PAID:
        return True, order.tx_hash, "already_paid"

    if mode == "manual":
        return False, "", "Payment requires admin confirmation in the admin panel."

    if mode == "provider":
        try:
            status, txid = _payram_payment_status(order.provider_order_id or order.order_ref)
        except ValueError as exc:
            return False, "", f"Gateway check failed: {exc}"
        if status in _PAYRAM_PAYMENT_PAID:
            order.mark_paid(txid)
            order.investment.confirm()
            return True, order.tx_hash, "paid"
        if status in _PAYRAM_PAYMENT_FAILED:
            if order.status != PaymentOrder.STATUS_PAID:
                order.status = PaymentOrder.STATUS_FAILED
                order.save(update_fields=["status", "updated_at"])
            return False, "", f"Payment {status} on PayRam."
        return False, "", f"Payment still {status or 'unknown'} on PayRam."

    # simulate
    tx = _simulated_hash("receive")
    order.mark_paid(tx)
    return True, tx, "paid"


# ---------------------------------------------------------------------------
# Webhook verification (legacy + PayRam)
# ---------------------------------------------------------------------------


def _webhook_secret():
    """Webhook signing secret. Returns None when unconfigured.

    A shared ``dev-gateway-secret`` is only ever used in DEBUG; in production an
    unconfigured secret disables (rejects) webhooks so nobody can forge a signed
    callback that marks orders paid.
    """
    val = _provider_setting(
        PlatformSettings.S_PAYMENT_WEBHOOK_TOKEN, "PAYMENT_WEBHOOK_TOKEN", ""
    ).strip()
    if val:
        return val
    from django.conf import settings

    return "dev-gateway-secret" if settings.DEBUG else None


def verify_webhook_signature(raw_body, signature):
    """Verify an HMAC-SHA256 signature over the raw POST body (legacy gate)."""
    if not signature:
        return False
    secret = _webhook_secret()
    if secret is None:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_nowpayments_signature(raw_body, signature):
    """Verify a NOWPayments IPN signature (legacy gate, HMAC-SHA512)."""
    if not signature:
        return False
    secret = _webhook_secret()
    if secret is None:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_btcpay_signature(raw_body, signature):
    """Verify a BTCPay webhook signature (``BTCPay-Sig: sha256=<hex>`` (legacy))."""
    if not signature:
        return False
    signature = signature.strip()
    if "=" in signature:
        signature = signature.split("=", 1)[-1].strip()
    secret = _webhook_secret()
    if secret is None:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_payram_signature(raw_body, signature):
    """Verify a PayRam webhook signature (``X-Payram-Signature: sha256=<hex>``).

    PayRam signs the exact raw request body with HMAC-SHA256 keyed by the
    project API key. Accepts either environment's key so test + production
    webhooks are both valid.
    """
    if not signature:
        return False
    signature = signature.strip()
    if "=" in signature:
        signature = signature.split("=", 1)[-1].strip()
    for env in _PAYRAM_ENVS:
        key = _payram_api_key(env)
        if not key:
            continue
        expected = hmac.new(key.encode(), raw_body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, signature):
            return True
    return False


_BTCPAY_PAID_EVENTS = {"invoicesettled", "invoiceprocessingsettled"}
_BTCPAY_FAILED_EVENTS = {"invoiceexpired", "invoiceinvalid"}


def handle_payram_payment_webhook(data):
    """Apply a verified PayRam payment (deposit) webhook.

    Payload key fields: ``invoice_id`` (our order_ref), ``reference_id``,
    ``status`` (FILLED / OVER_FILLED / PARTIALLY_FILLED / CANCELLED),
    ``payment_info[].transaction_hash``. Idempotent on reference + status.
    """
    from api.models import PaymentOrder

    status = str(data.get("status") or "").strip().upper()
    if not status:
        return False
    invoice = str(data.get("invoice_id") or "").strip()
    ref = str(data.get("reference_id") or "").strip()
    order = None
    if invoice:
        order = PaymentOrder.objects.filter(order_ref=invoice).first()
    if order is None and ref:
        order = PaymentOrder.objects.filter(provider_order_id=ref).first()
    if order is None:
        return False

    if status in _PAYRAM_PAYMENT_PAID:
        if order.status == PaymentOrder.STATUS_PAID:
            return False
        tx = ""
        info = data.get("payment_info")
        if isinstance(info, list) and info and isinstance(info[0], dict):
            tx = str(info[0].get("transaction_hash") or "")
        order.mark_paid(tx)
        order.investment.confirm()
        return True
    if status in _PAYRAM_PAYMENT_FAILED:
        if order.status != PaymentOrder.STATUS_PAID:
            order.status = PaymentOrder.STATUS_FAILED
            order.save(update_fields=["status", "updated_at"])
        return True
    return False


_PAYRAM_PAYOUT_WEBHOOK_DONE = {"payout.sent", "payout.processed"}
_PAYRAM_PAYOUT_WEBHOOK_FAILED = {"payout.failed", "payout.rejected", "payout.cancelled"}


def handle_payram_payout_webhook(data):
    """Apply a verified PayRam payout webhook.

    Payload key fields: ``payout_id`` (PayRam payout id, stored in
    Withdrawal/Payout.provider_id), ``event_type`` (``payout.<status>``),
    ``tx_hash``, ``failure_reason``. ``payout.sent`` is the terminal success
    event (``processed`` is not delivered). Idempotent on payout id + status.
    """
    from api.models import Payout, Wallet, Withdrawal

    pid = str(data.get("payout_id") or "").strip()
    if not pid:
        return False
    event = str(data.get("event_type") or "").strip().lower()
    tx = str(data.get("tx_hash") or "").strip()
    reason = str(data.get("failure_reason") or "").strip()

    wd = (
        Withdrawal.objects.filter(
            provider_id=pid, status=Withdrawal.STATUS_PROCESSING
        )
        .select_related("user", "coin")
        .first()
    )
    if wd is not None:
        if event in _PAYRAM_PAYOUT_WEBHOOK_DONE:
            wd.status = Withdrawal.STATUS_COMPLETED
            wd.tx_hash = tx or wd.tx_hash
            wd.save(update_fields=["status", "tx_hash", "updated_at"])
            return True
        if event in _PAYRAM_PAYOUT_WEBHOOK_FAILED:
            if wd.status != Withdrawal.STATUS_COMPLETED:
                wallet = Wallet.ensure(wd.user, wd.coin)
                wallet.withdrawable_balance += wd.amount
                wallet.save(update_fields=["withdrawable_balance", "updated_at"])
                wd.status = Withdrawal.STATUS_FAILED
                wd.reject_reason = reason or f"PayRam payout {event}."
                wd.save(update_fields=["status", "reject_reason", "updated_at"])
            return True
        return False

    po = Payout.objects.filter(
        provider_id=pid, status=Payout.STATUS_PROCESSING
    ).select_related("coin").first()
    if po is not None:
        if event in _PAYRAM_PAYOUT_WEBHOOK_DONE:
            po.status = Payout.STATUS_COMPLETED
            po.tx_hash = tx or po.tx_hash
            po.save(update_fields=["status", "tx_hash", "updated_at"])
            return True
        if event in _PAYRAM_PAYOUT_WEBHOOK_FAILED:
            if po.status != Payout.STATUS_COMPLETED:
                po.status = Payout.STATUS_FAILED
                po.note = f"{po.note}\nPayRam payout {event}: {reason or 'failed'}".strip()
                po.save(update_fields=["status", "note", "updated_at"])
            return True
        return False

    return False


def handle_gateway_webhook(data):
    """Apply a verified legacy gateway callback.

    PayRam payments are handled by ``handle_payram_payment_webhook``; this keeps
    legacy webhook shapes working:
    BTCPay:     {"type": "InvoiceSettled", "invoiceId": str, ...}
    Generic:    {"order_ref": str, "status": "PAID"|..., "tx_hash": str|""}
    Returns True when the callback was applied (accepted or order updated).
    """
    from api.models import PaymentOrder

    # Legacy BTCPay webhook shape: {"type": "InvoiceSettled", "invoiceId": "..."}
    ev_type = (data.get("type") or "").strip().lower()
    if ev_type in _BTCPAY_PAID_EVENTS or ev_type in _BTCPAY_FAILED_EVENTS:
        nested = data.get("data") if isinstance(data.get("data"), dict) else {}
        invoice_id = str(
            data.get("invoiceId")
            or nested.get("invoiceId")
            or data.get("id")
            or ""
        )
        if not invoice_id:
            return False
        order = PaymentOrder.objects.filter(provider_order_id=invoice_id).first()
        if order is None:
            return False
        if ev_type in _BTCPAY_PAID_EVENTS:
            if order.status == PaymentOrder.STATUS_PAID:
                return False
            order.mark_paid("")
            order.investment.confirm()
            return True
        order.status = PaymentOrder.STATUS_FAILED
        order.save(update_fields=["status", "updated_at"])
        return True

    # Generic + NOWPayments shapes (legacy providers).
    order_ref = (data.get("order_ref") or data.get("order_id") or "").strip()
    status = (data.get("status") or data.get("payment_status") or "").strip().lower()
    tx_hash = (data.get("tx_hash") or data.get("payout_txid") or "").strip()
    if not order_ref or not status:
        return False
    order = PaymentOrder.objects.filter(order_ref=order_ref).first()
    if order is None:
        return False
    if status in {"paid", "success", "completed", "finished", "confirmed"}:
        if order.status == PaymentOrder.STATUS_PAID:
            return False
        order.mark_paid(tx_hash)
        order.investment.confirm()
        return True
    if status in {"failed", "expired"}:
        order.status = PaymentOrder.STATUS_FAILED
        order.save(update_fields=["status", "updated_at"])
        return True
    return False


# ---------------------------------------------------------------------------
# Polling (PayRam fallback besides webhooks)
# ---------------------------------------------------------------------------


def _withdrawal_order_ref(pk):
    return f"WD{pk}"


def _payout_order_ref(pk):
    return f"PO{pk}"


def test_payram_connection():
    """Test the active PayRam environment. Returns (ok, message)."""
    mode = _mode()
    if mode != "provider":
        return False, f"Payment mode is '{mode}'. Switch to 'provider' to test."
    env, base, key = _payram_active()
    if not base:
        return False, "No PayRam BASE_URL configured for the active environment."
    try:
        rows = _payram_get("/ticker", "")
        count = len(rows) if isinstance(rows, list) else 0
    except (requests.RequestException, ValueError) as exc:
        return False, f"Connection failed: {exc}"
    if key:
        try:
            _payram_get(f"/payment/reference/{secrets.token_hex(4)}", key)
        except ValueError as exc:
            if "401" in str(exc):
                return False, f"API key rejected (HTTP 401). Check the key for '{env}'."
            # Other errors (e.g. 404 for a bogus reference) still prove the key works.
        except requests.RequestException as exc:
            return False, f"Key check failed: {exc}"
    return True, f"PayRam OK ({env}, {count} currencies ticker)."


def reconcile_gateway():
    """Finalize outstanding PayRam orders by polling the API.

    - Confirms pending investments whose PayRam payment reached a filled state.
    - Finalizes PROCESSING withdrawals/payouts whose PayRam payout reached a
      terminal state (completed or failed/refunded).
    Returns (investments_confirmed, transfers_finalized) counts.
    """
    from api.models import PaymentOrder, Payout, Withdrawal

    if _mode() != "provider":
        return 0, 0
    env, base, key = _payram_active()
    if not base or not key:
        return 0, 0

    paid_orders = 0
    orders = PaymentOrder.objects.filter(status=PaymentOrder.STATUS_PENDING).exclude(
        order_ref=""
    )
    for order in orders:
        try:
            status, txid = _payram_payment_status(order.provider_order_id or order.order_ref)
        except ValueError:
            continue
        if status in _PAYRAM_PAYMENT_PAID:
            order.mark_paid(txid)
            order.investment.confirm()
            paid_orders += 1
        elif status in _PAYRAM_PAYMENT_FAILED:
            if order.status != PaymentOrder.STATUS_PAID:
                order.status = PaymentOrder.STATUS_FAILED
                order.save(update_fields=["status", "updated_at"])

    transfers = 0
    for wd in Withdrawal.objects.filter(
        status=Withdrawal.STATUS_PROCESSING
    ).exclude(provider_id="").select_related("coin", "user"):
        try:
            status, txid = _payram_payout_status(wd.provider_id)
        except ValueError:
            continue
        if status in _PAYRAM_PAYOUT_DONE:
            wd.status = Withdrawal.STATUS_COMPLETED
            wd.tx_hash = txid or wd.tx_hash
            wd.save(update_fields=["status", "tx_hash", "updated_at"])
            transfers += 1
        elif status in _PAYRAM_PAYOUT_FAILED:
            if wd.status != Withdrawal.STATUS_COMPLETED:
                from api.models import Wallet
                wallet = Wallet.ensure(wd.user, wd.coin)
                wallet.withdrawable_balance += wd.amount
                wallet.save(update_fields=["withdrawable_balance", "updated_at"])
                wd.status = Withdrawal.STATUS_FAILED
                wd.reject_reason = f"PayRam payout {status.lower()}."
                wd.save(update_fields=["status", "reject_reason", "updated_at"])
                transfers += 1

    for po in Payout.objects.filter(
        status=Payout.STATUS_PROCESSING
    ).exclude(provider_id="").select_related("coin"):
        try:
            status, txid = _payram_payout_status(po.provider_id)
        except ValueError:
            continue
        if status in _PAYRAM_PAYOUT_DONE:
            po.status = Payout.STATUS_COMPLETED
            po.tx_hash = txid or po.tx_hash
            po.save(update_fields=["status", "tx_hash", "updated_at"])
            transfers += 1
        elif status in _PAYRAM_PAYOUT_FAILED:
            if po.status != Payout.STATUS_COMPLETED:
                po.status = Payout.STATUS_FAILED
                po.note = f"{po.note}\nPayRam payout {status.lower()}.".strip()
                po.save(update_fields=["status", "note", "updated_at"])
                transfers += 1

    return paid_orders, transfers