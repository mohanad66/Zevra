"""Crypto transfer / payment provider.

The platform moves coins through Plisio, a hosted crypto gateway. There are two
integration points, switched by the PlatformSetting ``payment_mode``:

* **Investments** (user pays the platform): ``create_payment_order`` creates a
  Plisio invoice (``GET /api/v1/invoices/new``) the user pays. It is confirmed by
  the Plisio webhook (``/api/gateway/webhook/?json=true``) and/or polling
  (``confirm_payment``, ``reconcile_gateway``), and can be finalized manually in
  admin.
* **Withdrawals / payouts** (platform pays the user): once an admin approves the
  payout/withdrawal, ``send_platform_to_user`` creates a Plisio withdrawal
  (``GET /api/v1/operations/withdraw``). ``reconcile_gateway()`` (polling — run
  via ``python manage.py poll_gateway`` or lazily from the admin orders view)
  finalizes the on-chain result.

Modes:
    simulate – fake deposit address + fake tx hashes (default)
    provider – Plisio (hosted crypto gateway)
    manual   – a human operator moves coins off-line and enters tx hashes in admin

Plisio configuration:
    One SECRET_KEY (Plisio dashboard » API » API settings) powers deposits and
    payouts on every chain the platform offers:

        PLISIO_API_KEY   - Plisio SECRET_KEY (api_key query parameter)

    Webhooks: Plisio callbacks POST JSON to
    ``/api/gateway/webhook/?json=true`` with a ``verify_hash`` field
    (HMAC-SHA1 keyed by the SECRET_KEY over the sorted request values).
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
from decimal import Decimal

import requests
from django.utils import timezone

from api.models import PaymentOrder, PlatformSettings


def _provider_setting(key, env_name, default=""):
    """Environment variables win; PlatformSettings is the fallback."""
    val = os.environ.get(env_name, "").strip()
    if val:
        return val
    val = PlatformSettings.get(key, "")
    if val is not None and val != "":
        return val
    return default


# ---------------------------------------------------------------------------
# Modes / provider readiness
# ---------------------------------------------------------------------------


def _mode():
    mode = PlatformSettings.get("payment_mode", "simulate").lower()
    return mode if mode in {"simulate", "provider", "manual"} else "simulate"


def _provider_ready():
    """(ok, message) check that Plisio is configured."""
    key = _plisio_api_key()
    if not key:
        return False, "No Plisio API key configured (Admin > Payments)."
    return True, "Plisio configured."


# ---------------------------------------------------------------------------
# USD conversion
# ---------------------------------------------------------------------------


def _usd_price(coin):
    """Current USD price of one unit of ``coin``.

    Uses the coin's stored reference price. Stablecoins carry a 1.0 reference so
    the conversion is exact; admins keep other reference prices up to date.
    """
    try:
        return float(coin.reference_price or 0)
    except (TypeError, ValueError):
        return 0.0


def _usd_amount(coin, amount):
    """Convert a crypto amount to USD (2 decimals) for payment creation."""
    price = _usd_price(coin)
    if price <= 0:
        raise ValueError(f"No USD price available for {coin.symbol}.")
    return round(float(amount) * price, 2)


# ---------------------------------------------------------------------------
# Cryptomus configuration + HTTP
# ---------------------------------------------------------------------------
#
#   CRYPTOMUS_MERCHANT_ID      - merchant uuid (Cryptomus dashboard > settings)
#   CRYPTOMUS_PAYMENT_API_KEY  - "Payment API key" (invoices / deposits)
#   CRYPTOMUS_PAYOUT_API_KEY   - "Payout API key" (withdrawals) - optional,
#                                 only needed if payouts run through Cryptomus
#
# Same PlatformSettings-first-then-env lookup as the rest of this file. Set
# webhook URL in the Cryptomus dashboard (or PAYMENT_CALLBACK_URL) to:
#   https://<your-api-domain>/api/gateway/webhook/


def _cryptomus_merchant_id():
    return _provider_setting(
        PlatformSettings.S_CRYPTOMUS_MERCHANT_ID, "CRYPTOMUS_MERCHANT_ID", ""
    ).strip()


def _cryptomus_payment_key():
    return _provider_setting(
        PlatformSettings.S_CRYPTOMUS_PAYMENT_KEY, "CRYPTOMUS_PAYMENT_API_KEY", ""
    ).strip()


def _cryptomus_payout_key():
    return _provider_setting(
        PlatformSettings.S_CRYPTOMUS_PAYOUT_KEY, "CRYPTOMUS_PAYOUT_API_KEY", ""
    ).strip()


def _gateway_webhook_url():
    return _provider_setting(
        PlatformSettings.S_PAYMENT_CALLBACK_URL, "PAYMENT_CALLBACK_URL",
        "https://api.miyartrading.com/api/gateway/webhook/",
    ).strip()


# UI network id -> Cryptomus blockchain code. Verify each against your own
# account with a real test call before relying on it (see the test script).
_CRYPTOMUS_NETWORKS = {
    "TRC20": "TRON",
    "ERC20": "ETH",
    "BEP20": "BSC",
    "POL": "POLYGON",
}


def _cryptomus_sign(body, api_key):
    payload = json.dumps(body, separators=(",", ":")) if body else ""
    b64 = base64.b64encode(payload.encode()).decode()
    return hashlib.md5((b64 + api_key).encode()).hexdigest()


def _cryptomus_post(path, body, api_key):
    """POST to the Cryptomus API. Raises ValueError on failure. Returns the
    ``result`` object of a successful (``state: 0``) response."""
    merchant = _cryptomus_merchant_id()
    if not merchant or not api_key:
        raise ValueError(
            "Cryptomus is not configured. Set CRYPTOMUS_MERCHANT_ID and the "
            "relevant API key in Admin > Payments or in .env."
        )
    payload = json.dumps(body, separators=(",", ":"))
    headers = {
        "merchant": merchant,
        "sign": _cryptomus_sign(body, api_key),
        "Content-Type": "application/json",
    }
    try:
        r = requests.post(
            f"https://api.cryptomus.com/v1{path}", data=payload, headers=headers, timeout=30
        )
    except requests.RequestException as exc:
        raise ValueError(f"Cryptomus unreachable: {exc}") from exc
    try:
        parsed = r.json()
    except ValueError:
        parsed = {}
    if r.status_code >= 300 or parsed.get("state") not in (0, None):
        msg = parsed.get("message") or parsed.get("errors") or r.text[:300]
        raise ValueError(f"Cryptomus HTTP {r.status_code}: {msg}")
    return parsed.get("result") or {}


def _create_cryptomus_payment(investment, order_ref):
    """Create a Cryptomus invoice for an investment. Returns the checkout payload."""
    coin = investment.coin
    amount = float(investment.amount)
    net_label = (investment.source_address or "").strip().upper()
    common = {
        "coin_symbol": coin.symbol,
        "chain": net_label or coin.chain,
        "amount": investment.amount,
        "payment_mode": "provider",
        "order_ref": order_ref,
        "gateway": "cryptomus",
    }
    payment_key = _cryptomus_payment_key()
    if not _cryptomus_merchant_id() or not payment_key:
        return {
            "status": "failed", "address": "", "checkout_url": "",
            "message": "Cryptomus is not configured (merchant id / payment key).",
            **common,
        }
    try:
        amount_usd = _usd_amount(coin, amount)
    except ValueError as exc:
        return {"status": "failed", "address": "", "checkout_url": "", "message": str(exc), **common}
    if amount_usd <= 0:
        return {"status": "failed", "address": "", "checkout_url": "",
                "message": "Payment amount must be positive in USD.", **common}
    body = {
        "amount": f"{amount_usd:.2f}",
        "currency": "USD",
        "order_id": order_ref,
        "url_callback": _gateway_webhook_url(),
        "lifetime": "3600",
    }
    net = _CRYPTOMUS_NETWORKS.get(net_label)
    if net:
        body["network"] = net
    try:
        result = _cryptomus_post("/payment", body, payment_key)
    except ValueError as exc:
        return {"status": "failed", "address": "", "checkout_url": "", "message": str(exc), **common}
    url = str(result.get("url") or "")
    address = str(result.get("address") or "")
    if not url and not address:
        return {"status": "failed", "address": "", "checkout_url": "",
                "message": "Cryptomus created the payment but returned no address or checkout url.",
                **common}
    pay_amount = str(
        result.get("payer_amount") or result.get("payment_amount") or ""
    )
    pay_currency = str(result.get("payer_currency") or result.get("currency") or "")
    return {
        "status": "pending",
        "address": address,
        "checkout_url": url,
        "pay_amount": pay_amount,
        "pay_currency": pay_currency,
        "provider_order_id": str(result.get("uuid") or order_ref),
        **common,
    }


def _cryptomus_payment_status(order_ref):
    """Poll a Cryptomus invoice by our order_id. Returns (state, tx) using the
    same vocabulary as the gateway state sets (FILLED / OVER_FILLED / CANCELLED /
    PENDING), so the shared _GATEWAY_* checks work unchanged."""
    key = _cryptomus_payment_key()
    result = _cryptomus_post("/payment/info", {"order_id": order_ref}, key)
    status = str(result.get("status") or "").lower()
    is_final = bool(result.get("is_final"))
    tx = str(result.get("txid") or "")
    if status in ("paid", "paid_over"):
        return ("OVER_FILLED" if status == "paid_over" else "FILLED"), tx
    if is_final:
        return "CANCELLED", tx
    return "PENDING", tx


def _create_cryptomus_payout(coin, to_address, amount, network="", order_ref=None, user=None):
    """Create a Cryptomus payout. Returns our own order_ref as the tracking id
    (Cryptomus is polled/matched by order_id, not by its own uuid)."""
    payout_key = _cryptomus_payout_key()
    if not _cryptomus_merchant_id() or not payout_key:
        raise ValueError(
            "Cryptomus payout is not configured (merchant id / payout key)."
        )
    net = _CRYPTOMUS_NETWORKS.get((network or coin.chain or "").upper())
    if not net:
        raise ValueError(
            f"Cryptomus does not support payouts on {network or coin.chain}. "
            f"Supported: {', '.join(_CRYPTOMUS_NETWORKS)}."
        )
    currency = str(coin.symbol).upper()
    ref = order_ref or f"PO-{secrets.token_hex(6)}"
    body = {
        "amount": _amount_str(coin, amount),
        "currency": currency,
        "network": net,
        "order_id": ref,
        "address": to_address,
        "is_subtract": "0",
        "url_callback": _gateway_webhook_url(),
    }
    _cryptomus_post("/payout", body, payout_key)
    return ref


def _cryptomus_payout_status(order_ref):
    """Poll a Cryptomus payout by our order_id. Returns (status, tx) using the
    same vocabulary (SENT / FAILED / PROCESSING) the shared
    _GATEWAY_PAYOUT_DONE / _GATEWAY_PAYOUT_FAILED checks expect."""
    key = _cryptomus_payout_key()
    result = _cryptomus_post("/payout/info", {"order_id": order_ref}, key)
    status = str(result.get("status") or "").lower()
    is_final = bool(result.get("is_final"))
    tx = str(result.get("txid") or "")
    if status == "paid":
        return "SENT", tx
    if is_final:
        return "FAILED", tx
    return "PROCESSING", tx


def verify_cryptomus_signature(data):
    """Verify a Cryptomus webhook: md5(base64(body without "sign") + api_key),
    tried against both the payment and payout keys. Best-effort: if Cryptomus's
    own JSON formatting ever differs from Python's, this can miss a valid
    webhook -- reconcile_gateway() polling is the fallback for that case."""
    if not isinstance(data, dict):
        return False
    sign = str(data.get("sign") or "").strip()
    if not sign:
        return False
    body = {k: v for k, v in data.items() if k != "sign"}
    payload = json.dumps(body, separators=(",", ":"))
    b64 = base64.b64encode(payload.encode()).decode()
    for key in (_cryptomus_payment_key(), _cryptomus_payout_key()):
        if not key:
            continue
        expected = hashlib.md5((b64 + key).encode()).hexdigest()
        if hmac.compare_digest(expected, sign):
            return True
    return False


def handle_cryptomus_webhook(data):
    """Route a verified Cryptomus webhook by our own order_id prefix."""
    order_id = str(data.get("order_id") or "").strip()
    if not order_id:
        return False
    if order_id.startswith(("WD", "PO")):
        return _handle_cryptomus_payout_webhook(order_id, data)
    return _handle_cryptomus_payment_webhook(order_id, data)


def _handle_cryptomus_payment_webhook(order_id, data):
    from api.models import PaymentOrder

    order = PaymentOrder.objects.filter(order_ref=order_id).first()
    if order is None:
        return False
    status = str(data.get("status") or "").lower()
    is_final = bool(data.get("is_final"))
    tx = str(data.get("txid") or "")
    if status in ("paid", "paid_over"):
        if order.status == PaymentOrder.STATUS_PAID:
            return False
        order.mark_paid(tx)
        order.investment.confirm()
        return True
    if is_final:
        if order.status != PaymentOrder.STATUS_PAID:
            order.status = PaymentOrder.STATUS_FAILED
            order.save(update_fields=["status", "updated_at"])
        return True
    return False


def _handle_cryptomus_payout_webhook(order_id, data):
    from api.models import Payout, Wallet, Withdrawal

    status = str(data.get("status") or "").lower()
    is_final = bool(data.get("is_final"))
    tx = str(data.get("txid") or "")

    if order_id.startswith("WD"):
        wd = Withdrawal.objects.filter(
            provider_id=order_id, status=Withdrawal.STATUS_PROCESSING
        ).select_related("user", "coin").first()
        if wd is None:
            return False
        if status == "paid":
            wd.status = Withdrawal.STATUS_COMPLETED
            wd.tx_hash = tx or wd.tx_hash
            wd.save(update_fields=["status", "tx_hash", "updated_at"])
            return True
        if is_final:
            wallet = Wallet.ensure(wd.user, wd.coin)
            wallet.withdrawable_balance += wd.amount
            wallet.save(update_fields=["withdrawable_balance", "updated_at"])
            wd.status = Withdrawal.STATUS_FAILED
            wd.reject_reason = f"Cryptomus payout {status or 'failed'}."
            wd.save(update_fields=["status", "reject_reason", "updated_at"])
            return True
        return False

    po = Payout.objects.filter(
        provider_id=order_id, status=Payout.STATUS_PROCESSING
    ).select_related("coin").first()
    if po is None:
        return False
    if status == "paid":
        po.status = Payout.STATUS_COMPLETED
        po.tx_hash = tx or po.tx_hash
        po.save(update_fields=["status", "tx_hash", "updated_at"])
        return True
    if is_final:
        po.status = Payout.STATUS_FAILED
        po.note = f"{po.note}\nCryptomus payout {status or 'failed'}.".strip()
        po.save(update_fields=["status", "note", "updated_at"])
        return True
    return False


# ---------------------------------------------------------------------------
# Plisio (deposits + payouts)
# ---------------------------------------------------------------------------
#
# Plisio is the platform's sole crypto gateway. One SECRET_KEY (API » Api
# settings) powers every chain end-to-end:
#
#   * Deposits:    GET https://api.plisio.net/api/v1/invoices/new  -> invoice_url
#   * Deposit poll: GET /api/v1/operations/{txn_id}
#   * Deposit webhook to /api/gateway/webhook/?json=true  (HMAC-SHA1 JSON callback)
#   * Payouts:     GET https://api.plisio.net/api/v1/operations/withdraw -> op id
#   * Payout poll:  GET /api/v1/operations/{op_id}
#
# All Plisio requests are GETs with an ``api_key`` query parameter.


def _plisio_api_key():
    return _provider_setting(
        PlatformSettings.S_PLISIO_API_KEY, "PLISIO_API_KEY", ""
    ).strip()


# UI network label -> Plisio currency ID ("psys_cid" column). Only USDT is
# enabled on this platform's coins, so one map serves both directions (invoice
# ``currency`` and cash_out ``currency``).
#
# The same map routes deposits *and* payouts so the whole chain lives on one
# provider.
_PLISIO_NETWORKS = {
    "TRC20": "USDT_TRX",
    "BEP20": "USDT_BSC",
    "ERC20": "USDT",
    "ETH20": "USDT",
}


def _plisio_get(endpoint, params, api_key=None):
    """GET to the Plisio API. Raises ValueError on failure. Returns the ``data``
    dict of a successful (``status: success``) response."""
    if not api_key:
        raise ValueError(
            "Plisio is not configured. Set PLISIO_API_KEY in Admin > Payments "
            "or in .env."
        )
    qs = dict(params or {})
    qs["api_key"] = api_key
    try:
        r = requests.get(
            f"https://api.plisio.net/api/v1{endpoint}", params=qs, timeout=30
        )
    except requests.RequestException as exc:
        raise ValueError(f"Plisio unreachable: {exc}") from exc
    try:
        parsed = r.json()
    except ValueError:
        parsed = {}
    if r.status_code >= 300 or str(parsed.get("status") or "").lower() != "success":
        msg = ""
        data = parsed.get("data")
        if isinstance(data, dict):
            msg = str(data.get("message") or "")
            if not msg and data.get("name"):
                msg = f"{data.get('name')}: {data.get('message', '')}".strip()
        raise ValueError(
            f"Plisio HTTP {r.status_code}: {msg or parsed.get('message') or r.text[:300]}"
        )
    return parsed.get("data") or {}


def _plisio_tx_from_url(url):
    """Extract a tx hash from a Plisio block-explorer URL (last path segment)."""
    url = str(url or "").strip()
    if not url or url in ("http:", "https:"):
        return ""
    parts = url.rstrip("/").split("/")
    return parts[-1] if len(parts) > 1 else url


def _create_plisio_payment(investment, order_ref):
    """Create a Plisio invoice for a BEP20 investment. Returns the checkout
    payload the frontend renders (redirect to the Plisio hosted invoice)."""
    coin = investment.coin
    amount = float(investment.amount)
    user = investment.user
    net_label = (investment.source_address or "").strip().upper() or coin.chain
    common = {
        "coin_symbol": coin.symbol,
        "chain": net_label,
        "amount": investment.amount,
        "payment_mode": "provider",
        "order_ref": order_ref,
        "gateway": "plisio",
    }
    key = _plisio_api_key()
    if not key:
        return {
            "status": "failed",
            "address": "",
            "checkout_url": "",
            "message": "Plisio is not configured (API key).",
            **common,
        }
    currency = _PLISIO_NETWORKS.get(net_label)
    if not currency:
        return {
            "status": "failed",
            "address": "",
            "checkout_url": "",
            "message": f"{net_label} is not supported by Plisio. "
            f"Choose one of: {', '.join(sorted(_PLISIO_NETWORKS))}.",
            **common,
        }
    try:
        amount_usd = _usd_amount(coin, amount)
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
    callback = _gateway_webhook_url()
    if callback and "json=true" not in callback:
        sep = "&" if "?" in callback else "?"
        callback = f"{callback}{sep}json=true"
    params = {
        "source_currency": "USD",
        "source_amount": f"{amount_usd:.2f}",
        "order_number": order_ref,
        "order_name": f"Investment {order_ref}",
        "currency": currency,
        "allowed_psys_cids": currency,
        "email": user.email or f"user{user.pk}@miyartrading.com",
        "expire_min": "30",
        "callback_url": callback,
    }
    try:
        data = _plisio_get("/invoices/new", params, key)
    except ValueError as exc:
        return {
            "status": "failed",
            "address": "",
            "checkout_url": "",
            "message": str(exc),
            **common,
        }
    txn_id = str(data.get("txn_id") or "")
    url = str(data.get("invoice_url") or "")
    if not txn_id or not url:
        return {
            "status": "failed",
            "address": "",
            "checkout_url": "",
            "message": "Plisio created the invoice but returned no txn_id or invoice_url.",
            **common,
        }
    # ``wallet_hash`` / ``qr_code`` / ``amount`` are only returned when the shop
    # has white-label processing enabled — that is what lets the checkout render
    # the deposit address + QR in-page instead of bouncing to the hosted invoice.
    return {
        "status": "pending",
        "address": str(data.get("wallet_hash") or ""),
        "qr_code": str(data.get("qr_code") or ""),
        "checkout_url": url,
        "pay_amount": str(data.get("amount") or investment.amount),
        "pay_currency": str(data.get("currency") or coin.symbol),
        "provider_order_id": txn_id,
        "provider_token": txn_id,
        "amount_usd": f"{amount_usd:.2f}",
        **common,
    }


_PLISIO_PAYMENT_DONE = {"completed", "paid", "paid_over"}
_PLISIO_PAYMENT_FAILED = {
    "error",
    "expired",
    "cancelled",
    "cancelled_duplicate",
    "mismatch",
}


def _plisio_payment_status(txn_id):
    """Poll a Plisio invoice by txn_id. Returns (state, tx) in the shared
    gateway vocabulary (FILLED / CANCELLED / PENDING)."""
    key = _plisio_api_key()
    data = _plisio_get(f"/operations/{txn_id}", {}, key)
    status = str(data.get("status") or "").lower().replace(" ", "_")
    tx = ""
    tx_urls = data.get("tx_urls")
    if isinstance(tx_urls, list) and tx_urls:
        tx = _plisio_tx_from_url(tx_urls[0])
    if not tx:
        tx = _plisio_tx_from_url(data.get("tx_url") or data.get("txid") or "")
    if status in _PLISIO_PAYMENT_DONE:
        return "FILLED", tx
    if status in _PLISIO_PAYMENT_FAILED:
        return "CANCELLED", tx
    return "PENDING", tx


def _create_plisio_payout(coin, to_address, amount, network="", order_ref=None, user=None):
    """Create a Plisio withdrawal. Returns its Plisio operation id."""
    key = _plisio_api_key()
    if not key:
        raise ValueError("Plisio payout is not configured (API key).")
    net = (network or coin.chain or "").upper()
    currency = _PLISIO_NETWORKS.get(net)
    if not currency:
        raise ValueError(
            f"Plisio does not support payouts on {net}. "
            f"Supported: {', '.join(_PLISIO_NETWORKS)}."
        )
    params = {
        "currency": currency,
        "type": "cash_out",
        "to": str(to_address).strip(),
        "amount": _amount_str(coin, amount),
    }
    try:
        data = _plisio_get("/operations/withdraw", params, key)
    except ValueError as exc:
        raise ValueError(f"Plisio withdrawal failed: {exc}") from exc
    pid = str(data.get("id") or "")
    if not pid:
        raise ValueError("Plisio created the payout but returned no operation id.")
    return pid


def _plisio_payout_status(op_id):
    """Poll a Plisio withdrawal by operation id. Returns (status, tx_hash) in
    the shared gateway vocabulary (SENT / FAILED / PROCESSING)."""
    key = _plisio_api_key()
    data = _plisio_get(f"/operations/{op_id}", {}, key)
    status = str(data.get("status") or "").lower().replace(" ", "_")
    tx_hash = _plisio_tx_from_url(data.get("tx_url") or "")
    tx_urls = data.get("tx_urls")
    if isinstance(tx_urls, list) and tx_urls:
        tx_hash = _plisio_tx_from_url(tx_urls[0])
    if status in ("completed", "success", "done", "sent"):
        return "SENT", tx_hash
    if status in ("error", "failed"):
        return "FAILED", tx_hash
    return "PROCESSING", tx_hash


def verify_plisio_signature(data):
    """Verify a Plisio JSON callback (``callback_url?json=true``).

    Per Plisio's Node example: HMAC-SHA1 (hex) keyed by the SECRET_KEY over
    ``JSON.stringify(callback payload without verify_hash)`` preserving the
    original key order.
    """
    if not isinstance(data, dict):
        return False
    verify_hash = str(data.get("verify_hash") or "").strip()
    if not verify_hash:
        return False
    key = _plisio_api_key()
    if not key:
        return False
    body = {k: v for k, v in data.items() if k != "verify_hash"}
    payload = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    expected = hmac.new(key.encode(), payload.encode(), hashlib.sha1).hexdigest()
    return hmac.compare_digest(expected, verify_hash)


_PLISIO_WEBHOOK_DONE = {"completed", "paid", "paid_over"}


def handle_plisio_webhook(data):
    """Apply a verified Plisio invoice callback.

    Payload key fields: ``order_number`` (our order_ref), ``status``
    (completed / expired / cancelled / error / pending / new), ``tx_urls``.
    """
    from api.models import PaymentOrder

    order_ref = str(data.get("order_number") or "").strip()
    if not order_ref:
        return False
    order = PaymentOrder.objects.filter(order_ref=order_ref).first()
    if order is None:
        return False
    status = str(data.get("status") or "").lower().replace(" ", "_")
    tx = ""
    tx_urls = data.get("tx_urls")
    if isinstance(tx_urls, list) and tx_urls:
        tx = _plisio_tx_from_url(tx_urls[0])
    if status in _PLISIO_WEBHOOK_DONE:
        if order.status == PaymentOrder.STATUS_PAID:
            return False
        order.mark_paid(tx)
        order.investment.confirm()
        return True
    if status in _PLISIO_PAYMENT_FAILED:
        if order.status != PaymentOrder.STATUS_PAID:
            order.status = PaymentOrder.STATUS_FAILED
            order.save(update_fields=["status", "updated_at"])
        return True
    return False


def _payment_gateway(order):
    """Which provider owns a payment order. Plisio is the only one."""
    return "plisio"


def _payout_gateway(net):
    """Which provider owns a payout/withdrawal. Plisio is the only one."""
    return "plisio"


# ---------------------------------------------------------------------------
# Simulation / manual helpers
# ---------------------------------------------------------------------------


def _simulated_hash(kind):
    return f"SIM-{timezone.now():%Y%m%d%H%M%S}-{secrets.token_hex(6)}"


def _fake_address(coin):
    """Deterministic fake deposit address so simulate mode looks realistic."""
    net = (coin.chain or "TRC20").upper()
    # .get with an empty default: a coin row can still carry a chain that is no
    # longer offered (e.g. after removing SOL), and that must not 500 here.
    prefix = {"TRC20": "T", "BEP20": "0x", "BEP2": "bnb1", "ERC20": "0x", "TON": "UQ"}.get(net, "")
    return f"{prefix}{secrets.token_hex(20)}"


def _amount_str(coin, amount):
    try:
        return f"{float(amount):.{8}f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(amount)


def send_platform_to_user(coin, to_address, amount, network="", order_ref=None, user=None):
    """Admin/platform wallet -> user wallet. Returns provider ref or ''.

    Used by payouts and withdrawals once admin approves them.
    - provider: creates a Plisio payout and returns its Plisio operation id.
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
        net = (network or coin.chain or "").upper()
        return _create_plisio_payout(coin, to_address, amount, net, order_ref, user)
    # simulate
    return _simulated_hash("send")


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

_GATEWAY_PAYMENT_PAID = {"FILLED", "OVER_FILLED"}
_GATEWAY_PAYMENT_FAILED = {"CANCELLED"}
_GATEWAY_PAYOUT_DONE = {"SENT", "PROCESSED"}
_GATEWAY_PAYOUT_FAILED = {"FAILED", "REJECTED", "CANCELLED"}


def create_payment_order(investment):
    """Create a payment order for a pending investment.

    Returns the checkout payload the frontend shows the user:
        {"order_ref", "status", "address", "checkout_url", "chain", "amount", "payment_mode"}
    """
    coin = investment.coin
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
        return _create_plisio_payment(investment, ref)

    # simulate: show the platform's deposit address and confirm on "I paid".
    return {
        "order_ref": ref,
        "status": "pending",
        "address": _platform_deposit_address(coin),
        "checkout_url": "",
        **common,
    }


def _apply_payment_status(order, state, tx=""):
    """Apply a gateway payment state to an order. Idempotent.

    Returns a machine status key: "paid" | "failed" | "pending".
    """
    state = str(state or "").upper()
    if state in _GATEWAY_PAYMENT_PAID:
        if order.status != PaymentOrder.STATUS_PAID:
            order.mark_paid(tx)
            order.investment.confirm()
        return "paid"
    if state in _GATEWAY_PAYMENT_FAILED:
        if order.status != PaymentOrder.STATUS_PAID:
            order.status = PaymentOrder.STATUS_FAILED
            order.save(update_fields=["status", "updated_at"])
        return "failed"
    return "pending"


def confirm_payment(order_ref):
    """Confirm a payment order and return (ok, tx_hash, message).

    simulate: trusts the user's confirmation (order was "paid" off-screen).
    provider: polls Plisio; only confirms when the payment is filled.
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
            state, txid = _plisio_payment_status(
                order.provider_order_id or order.order_ref
            )
        except ValueError as exc:
            return False, "", f"Gateway check failed: {exc}"
        result = _apply_payment_status(order, state, txid)
        if result == "paid":
            return True, order.tx_hash, "paid"
        if result == "failed":
            return False, "", f"Payment {state} on the gateway."
        return False, "", f"Payment still {state or 'unknown'} on the gateway."

    # simulate
    tx = _simulated_hash("receive")
    order.mark_paid(tx)
    return True, tx, "paid"


def payment_order_status(order_ref):
    """Machine-readable status for one payment order (user status checker).

    In provider mode it polls Plisio, so a payment that Plisio already marked
    completed is confirmed even when an earlier webhook delivery was missed.

    Returns:
        {"order_ref", "status": pending|paid|failed|expired, "tx_hash",
         "message"}
    """
    from api.models import PaymentOrder

    order = PaymentOrder.objects.filter(order_ref=order_ref).first()
    if order is None:
        return {
            "order_ref": order_ref,
            "status": "expired",
            "tx_hash": "",
            "message": "Payment order not found.",
        }

    if order.status == PaymentOrder.STATUS_PAID:
        return {
            "order_ref": order_ref,
            "status": "paid",
            "tx_hash": order.tx_hash or "",
            "message": "Payment received. Your investment is confirmed and your balance is updated.",
        }

    if _mode() == "provider" and order.provider_order_id:
        try:
            state, txid = _plisio_payment_status(
                order.provider_order_id or order.order_ref
            )
        except ValueError:
            state, txid = None, ""
        if state:
            _apply_payment_status(order, state, txid)

    if order.status == PaymentOrder.STATUS_PAID:
        return {
            "order_ref": order_ref,
            "status": "paid",
            "tx_hash": order.tx_hash or "",
            "message": "Payment received. Your investment is confirmed and your balance is updated.",
        }
    if order.status == PaymentOrder.STATUS_FAILED:
        return {
            "order_ref": order_ref,
            "status": "failed",
            "tx_hash": "",
            "message": "Payment failed or expired.",
        }
    return {
        "order_ref": order_ref,
        "status": "pending",
        "tx_hash": "",
        "message": "Waiting for your payment.",
    }


# ---------------------------------------------------------------------------
# Webhook verification (legacy + Plisio)
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


_BTCPAY_PAID_EVENTS = {"invoicesettled", "invoiceprocessingsettled"}
_BTCPAY_FAILED_EVENTS = {"invoiceexpired", "invoiceinvalid"}


def handle_gateway_webhook(data):
    """Apply a verified legacy gateway callback.

    Plisio callbacks are handled by ``handle_plisio_webhook``; this keeps legacy
    webhook shapes working:
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
# Polling (Plisio fallback besides webhooks)
# ---------------------------------------------------------------------------


def _withdrawal_order_ref(pk):
    return f"WD{pk}"


def _payout_order_ref(pk):
    return f"PO{pk}"


def test_plisio_connection():
    """Test the Plisio connection. Returns (ok, message)."""
    mode = _mode()
    if mode != "provider":
        return False, f"Payment mode is '{mode}'. Switch to 'provider' to test."
    key = _plisio_api_key()
    if not key:
        return False, "No Plisio API key configured (Admin > Payments)."
    try:
        _plisio_get("/operations/fee/1", {"currency": "USDT_TRX"}, key)
    except ValueError as exc:
        if "401" in str(exc) or "api key" in str(exc).lower() or "invalid" in str(exc).lower():
            return False, f"Plisio API key rejected: {exc}"
        # Any other error still proves the key reached the API.
    except requests.RequestException as exc:
        return False, f"Connection failed: {exc}"
    return True, "Plisio OK."


def reconcile_gateway():
    """Finalize outstanding gateway orders by polling Plisio.

    - Confirms pending investments whose Plisio payment reached a filled state.
    - Finalizes PROCESSING withdrawals/payouts whose Plisio payout reached a
      terminal state (completed or failed/refunded).
    Returns (investments_confirmed, transfers_finalized) counts.
    """
    from api.models import PaymentOrder, Payout, Withdrawal

    if _mode() != "provider":
        return 0, 0
    if not _plisio_api_key():
        return 0, 0

    paid_orders = 0
    orders = PaymentOrder.objects.filter(status=PaymentOrder.STATUS_PENDING).exclude(
        order_ref=""
    )
    for order in orders:
        try:
            state, txid = _plisio_payment_status(
                order.provider_order_id or order.order_ref
            )
        except ValueError:
            continue
        if _apply_payment_status(order, state, txid) == "paid":
            paid_orders += 1

    transfers = 0
    for wd in Withdrawal.objects.filter(
        status=Withdrawal.STATUS_PROCESSING
    ).exclude(provider_id="").select_related("coin", "user"):
        try:
            status, txid = _plisio_payout_status(wd.provider_id)
        except ValueError:
            continue
        if status in _GATEWAY_PAYOUT_DONE:
            wd.status = Withdrawal.STATUS_COMPLETED
            wd.tx_hash = txid or wd.tx_hash
            wd.save(update_fields=["status", "tx_hash", "updated_at"])
            transfers += 1
        elif status in _GATEWAY_PAYOUT_FAILED:
            if wd.status != Withdrawal.STATUS_COMPLETED:
                from api.models import Wallet

                wallet = Wallet.ensure(wd.user, wd.coin)
                wallet.withdrawable_balance += wd.amount
                wallet.save(update_fields=["withdrawable_balance", "updated_at"])
                wd.status = Withdrawal.STATUS_FAILED
                wd.reject_reason = f"Gateway payout {status.lower()}."
                wd.save(update_fields=["status", "reject_reason", "updated_at"])
                transfers += 1

    for po in Payout.objects.filter(
        status=Payout.STATUS_PROCESSING
    ).exclude(provider_id="").select_related("coin"):
        try:
            status, txid = _plisio_payout_status(po.provider_id)
        except ValueError:
            continue
        if status in _GATEWAY_PAYOUT_DONE:
            po.status = Payout.STATUS_COMPLETED
            po.tx_hash = txid or po.tx_hash
            po.save(update_fields=["status", "tx_hash", "updated_at"])
            transfers += 1
        elif status in _GATEWAY_PAYOUT_FAILED:
            if po.status != Payout.STATUS_COMPLETED:
                po.status = Payout.STATUS_FAILED
                po.note = f"{po.note}\nGateway payout {status.lower()}.".strip()
                po.save(update_fields=["status", "note", "updated_at"])
                transfers += 1

    return paid_orders, transfers