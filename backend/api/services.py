"""Crypto transfer / payment provider.

The platform moves coins through a hosted crypto gateway (BlockBee or Plisio),
selected by the PlatformSetting ``payment_gateway``. There are two integration
points, switched by the PlatformSetting ``payment_mode``:

* **Investments** (user pays the platform): ``create_payment_order`` creates a
  BlockBee payment address (or a Plisio invoice) the user pays. It is confirmed
  by the gateway webhook (``/api/gateway/webhook/``) and/or polling
  (``confirm_payment``, ``reconcile_gateway``), and can be finalized manually in
  admin.
* **Withdrawals / payouts** (platform pays the user): once an admin approves the
  payout/withdrawal, ``send_platform_to_user`` creates a BlockBee payout (or a
  Plisio withdrawal). ``reconcile_gateway()`` (polling — run via
  ``python manage.py poll_gateway`` or lazily from the admin orders view)
  finalizes the on-chain result.

Modes:
    simulate – fake deposit address + fake tx hashes (default)
    provider – hosted crypto gateway (BlockBee or Plisio)
    manual   – a human operator moves coins off-line and enters tx hashes in admin

Configuration:
    BLOCKBEE_API_KEY - BlockBee API key (payouts need API Key V2 + a funded
                       Self-Custodial Wallet and the server IP allow-listed)
    PLISIO_API_KEY   - Plisio SECRET_KEY (legacy alternative)

    An explicit ``payment_gateway`` setting (blockbee | plisio) wins; otherwise
    BlockBee is selected when its API key is configured.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
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


def _log_refund(withdrawal, old_withdrawable, reason=""):
    """Audit a withdrawal refund (amount returned to the user's balance)."""
    from api.models import BalanceAudit, record_balance_change

    record_balance_change(
        withdrawal.user,
        withdrawal.coin,
        BalanceAudit.FIELD_WITHDRAWABLE,
        old_withdrawable,
        old_withdrawable + withdrawal.amount,
        source=BalanceAudit.SRC_WITHDRAWAL_REFUND,
        note=reason or "Withdrawal refunded",
    )


# ---------------------------------------------------------------------------
# Modes / provider readiness
# ---------------------------------------------------------------------------


def _mode():
    mode = PlatformSettings.get("payment_mode", "simulate").lower()
    return mode if mode in {"simulate", "provider", "manual"} else "simulate"


def _provider_ready():
    """(ok, message) check that the active crypto gateway is configured."""
    if _active_gateway() == "blockbee":
        if not _blockbee_api_key():
            return False, "No BlockBee API key configured (Admin > Payments)."
        return True, "BlockBee configured."
    if not _plisio_api_key():
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
        "https://api.myxtrading.org/api/gateway/webhook/",
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
            old_withdrawable = wallet.withdrawable_balance
            wallet.withdrawable_balance += wd.amount
            wallet.save(update_fields=["withdrawable_balance", "updated_at"])
            _log_refund(wd, old_withdrawable, "Cryptomus payout failed")
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


# ---------------------------------------------------------------------------
# BlockBee (deposits + payouts)
# ---------------------------------------------------------------------------
#
#   BLOCKBEE_API_KEY    - BlockBee API key (Dashboard » API Keys)
#   BLOCKBEE_PUBLIC_KEY - optional override; by default the public key is
#                         fetched from https://api.blockbee.io/pubkey/
#
# Deposits:  GET  /{ticker}/create/?apikey=…&callback=…&post=1&pending=1
# Payouts:   POST /{ticker}/payout/request/bulk/process/  {"outputs": {addr: amount}}
# Status:    POST /payout/status/  {"payout_id": …}
# Webhook:   POST form body + ``x-ca-signature`` (RSA-SHA256, base64)
#
# BlockBee ignores (and loses) transfers below the ticker minimum, so the
# minimum is validated before an address is handed to the user.

_BLOCKBEE_BASE = "https://api.blockbee.io"
_BLOCKBEE_DOC_PUBKEY = """-----BEGIN PUBLIC KEY-----
MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC3FT0Ym8b3myVxhQW7ESuuu6lo
dGAsUJs4fq+Ey//jm27jQ7HHHDmP1YJO7XE7Jf/0DTEJgcw4EZhJFVwsk6d3+4fy
Bsn0tKeyGMiaE6cVkX0cy6Y85o8zgc/CwZKc0uw6d5siAo++xl2zl+RGMXCELQVE
ox7pp208zTvown577wIDAQAB
-----END PUBLIC KEY-----"""

_BLOCKBEE_PUBKEY_CACHE = {"pem": "", "fetched": 0.0}
_BLOCKBEE_MINIMUM_CACHE = {}

_BLOCKBEE_TOKENS = {
    ("USDT", "TRC20"): "trc20/usdt",
    ("USDT", "ERC20"): "erc20/usdt",
    ("USDT", "ETH20"): "erc20/usdt",
    ("USDT", "BEP20"): "bep20/usdt",
    ("USDT", "POLYGON"): "polygon/usdt",
    ("USDT", "TON"): "ton/usdt",
    ("USDC", "TRC20"): "trc20/usdc",
    ("USDC", "ERC20"): "erc20/usdc",
    ("USDC", "ETH20"): "erc20/usdc",
    ("USDC", "BEP20"): "bep20/usdc",
    ("USDC", "POLYGON"): "polygon/usdc",
    ("USDC", "TON"): "ton/usdc",
    ("DAI", "ERC20"): "erc20/dai",
    ("DAI", "ETH20"): "erc20/dai",
    ("DAI", "BEP20"): "bep20/dai",
}

_BLOCKBEE_NATIVE = {
    "BTC": "btc",
    "ETH": "eth",
    "LTC": "ltc",
    "BCH": "bch",
    "TRX": "trx",
    "BNB": "bnb",
    "DOGE": "doge",
    "SOL": "sol",
    "XRP": "xrp",
    "ADA": "ada",
    "DOT": "dot",
    "MATIC": "polygon",
    "POL": "polygon",
    "TON": "ton",
}


def _blockbee_api_key():
    return _provider_setting(
        PlatformSettings.S_BLOCKBEE_API_KEY, "BLOCKBEE_API_KEY", ""
    ).strip()


def _active_gateway():
    """Gateway used for new deposits/payouts.

    An explicit ``payment_gateway`` setting wins. Otherwise BlockBee is picked
    as soon as its API key is configured, so adding the key is enough to switch
    away from Plisio.
    """
    configured = (
        PlatformSettings.get(PlatformSettings.S_PAYMENT_GATEWAY, "") or ""
    ).strip().lower()
    if configured in {"blockbee", "plisio"}:
        return configured
    return "blockbee" if _blockbee_api_key() else "plisio"


def _blockbee_ticker(coin, network=""):
    symbol = str(getattr(coin, "symbol", "") or "").strip().upper()
    net = str(network or getattr(coin, "chain", "") or "").strip().upper()
    net = net.replace("ETH20", "ERC20")
    ticker = _BLOCKBEE_TOKENS.get((symbol, net))
    if ticker:
        return ticker
    if symbol in {"USDT", "USDC"}:
        raise ValueError(
            f"BlockBee does not support {symbol} on {net or 'this network'}."
        )
    if symbol in _BLOCKBEE_NATIVE:
        return _BLOCKBEE_NATIVE[symbol]
    if symbol.isalnum():
        return symbol.lower()
    raise ValueError(f"BlockBee does not support {symbol}.")


def _blockbee_request(method, path, params=None, body=None):
    """Call the BlockBee API. Raises ValueError on any API/transport failure."""
    key = _blockbee_api_key()
    if not key:
        raise ValueError(
            "BlockBee is not configured. Set BLOCKBEE_API_KEY in Admin > Payments "
            "or in the server environment."
        )
    query = dict(params or {})
    query["apikey"] = key
    url = f"{_BLOCKBEE_BASE}/{path.lstrip('/')}"
    try:
        if method.upper() == "GET":
            r = requests.get(url, params=query, timeout=30)
        else:
            r = requests.post(
                url,
                params=query,
                json=body or {},
                headers={"apikey": key},
                timeout=30,
            )
    except requests.RequestException as exc:
        raise ValueError(f"BlockBee unreachable: {exc}") from exc
    try:
        data = r.json()
    except ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    status = str(data.get("status") or "").lower()
    if r.status_code >= 400 or status == "error":
        message = (
            data.get("error")
            or data.get("message")
            or data.get("detail")
            or r.text[:300]
        )
        raise ValueError(f"BlockBee HTTP {r.status_code}: {message}")
    return data


def _blockbee_minimum(ticker):
    """Minimum transfer for a ticker (coin units). Cached for 10 minutes."""
    now = time.time()
    cached = _BLOCKBEE_MINIMUM_CACHE.get(ticker)
    if cached and now - cached[0] < 600:
        return cached[1]
    data = _blockbee_request("GET", f"{ticker}/info/")
    try:
        minimum = float(data.get("minimum_transaction_coin") or 0)
    except (TypeError, ValueError):
        minimum = 0.0
    _BLOCKBEE_MINIMUM_CACHE[ticker] = (now, minimum)
    return minimum


def _blockbee_callback_url(order_ref):
    base = _gateway_webhook_url()
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}order_id={order_ref}"


def _create_blockbee_payment(investment, order_ref):
    """Create a BlockBee payment address for an investment."""
    coin = investment.coin
    amount = float(investment.amount)
    net_label = (investment.source_address or "").strip().upper() or coin.chain
    common = {
        "coin_symbol": coin.symbol,
        "chain": net_label,
        "amount": investment.amount,
        "payment_mode": "provider",
        "order_ref": order_ref,
        "gateway": "blockbee",
    }
    if not _blockbee_api_key():
        return {
            "status": "failed",
            "address": "",
            "checkout_url": "",
            "message": "BlockBee is not configured (API key).",
            **common,
        }
    try:
        ticker = _blockbee_ticker(coin, net_label)
        minimum = _blockbee_minimum(ticker)
    except ValueError as exc:
        return {
            "status": "failed",
            "address": "",
            "checkout_url": "",
            "message": str(exc),
            **common,
        }
    if minimum > 0 and amount < minimum:
        return {
            "status": "failed",
            "address": "",
            "checkout_url": "",
            "message": (
                f"Minimum for {coin.symbol} on {net_label} is "
                f"{_amount_str(coin, minimum)} {coin.symbol}; "
                f"this order is {_amount_str(coin, amount)} {coin.symbol}."
            ),
            **common,
        }
    callback = _blockbee_callback_url(order_ref)
    try:
        data = _blockbee_request(
            "GET",
            f"{ticker}/create/",
            params={
                "callback": callback,
                "post": 1,
                "pending": 1,
                "convert": 1,
            },
        )
    except ValueError as exc:
        return {
            "status": "failed",
            "address": "",
            "checkout_url": "",
            "message": str(exc),
            **common,
        }
    address = str(data.get("address_in") or "").strip()
    if not address:
        return {
            "status": "failed",
            "address": "",
            "checkout_url": "",
            "message": "BlockBee created the payment but returned no address_in.",
            **common,
        }
    try:
        amount_usd = f"{_usd_amount(coin, amount):.2f}"
    except ValueError:
        amount_usd = ""
    return {
        "status": "pending",
        "address": address,
        "checkout_url": "",
        "qr_code": "",
        "pay_amount": _amount_str(coin, amount),
        "pay_currency": coin.symbol,
        "provider_order_id": address,
        "provider_token": "blockbee",
        "amount_usd": amount_usd,
        "minimum": _amount_str(coin, minimum),
        **common,
    }


def _blockbee_payment_status(order):
    """Poll a BlockBee payment address. Returns (state, tx) in the shared
    gateway vocabulary (FILLED / CANCELLED / PENDING)."""
    ticker = _blockbee_ticker(order.coin, order.chain)
    callback = _blockbee_callback_url(order.order_ref)
    data = _blockbee_request(
        "GET", f"{ticker}/logs/", params={"callback": callback}
    )
    address_in = str(data.get("address_in") or "").strip()
    if address_in and order.provider_order_id and address_in != order.provider_order_id:
        return "PENDING", ""
    try:
        expected = float(order.amount or 0)
    except (TypeError, ValueError):
        expected = 0.0
    tolerance = max(1e-8, expected * 0.005)
    callbacks = data.get("callbacks") or []
    confirmed = False
    tx = ""
    for entry in callbacks:
        if not isinstance(entry, dict):
            continue
        tx = tx or str(entry.get("txid_in") or "")
        result = str(entry.get("result") or "").lower()
        if result not in {"done", "sent"}:
            continue
        try:
            received = float(entry.get("value_coin") or 0)
        except (TypeError, ValueError):
            received = 0.0
        if expected > 0 and received + tolerance < expected:
            continue
        confirmed = True
    if confirmed:
        return "FILLED", tx
    return "PENDING", tx


def _create_blockbee_payout(coin, to_address, amount, network="", order_ref=None, user=None):
    """Create and process a BlockBee payout. Returns ``bb:<payout_id>``."""
    if not _blockbee_api_key():
        raise ValueError("BlockBee payout is not configured (API key).")
    ticker = _blockbee_ticker(coin, network)
    amount = float(amount)
    minimum = _blockbee_minimum(ticker)
    if minimum > 0 and amount < minimum:
        raise ValueError(
            f"Minimum for {coin.symbol} on {network or coin.chain} is "
            f"{_amount_str(coin, minimum)} {coin.symbol}; "
            f"this payout is {_amount_str(coin, amount)} {coin.symbol}."
        )
    data = _blockbee_request(
        "POST",
        f"{ticker}/payout/request/bulk/process/",
        body={"outputs": {str(to_address).strip(): amount}},
    )
    info = data.get("payout_info") if isinstance(data.get("payout_info"), dict) else {}
    payout_id = str(info.get("id") or data.get("payout_id") or data.get("id") or "")
    if not payout_id:
        raise ValueError("BlockBee created the payout but returned no payout id.")
    return f"bb:{payout_id}"


def _blockbee_payout_status(payout_id):
    """Poll a BlockBee payout. Returns (status, tx_hash) in the shared gateway
    vocabulary (SENT / FAILED / PROCESSING)."""
    pid = str(payout_id or "")
    if pid.startswith("bb:"):
        pid = pid[3:]
    data = _blockbee_request("POST", "payout/status/", body={"payout_id": pid})
    info = data.get("payout_info") if isinstance(data.get("payout_info"), dict) else {}
    status = str(info.get("status") or data.get("status") or "").lower()
    tx = str(info.get("txid") or info.get("tx_hash") or "")
    if status in {"done", "completed", "sent", "success"}:
        return "SENT", tx
    if status in {"rejected", "expired", "error", "failed", "cancelled"}:
        return "FAILED", tx
    return "PROCESSING", tx


def _blockbee_public_key():
    override = os.environ.get("BLOCKBEE_PUBLIC_KEY", "").strip()
    if override:
        return override
    now = time.time()
    cached = _BLOCKBEE_PUBKEY_CACHE
    if cached["pem"] and now - cached["fetched"] < 86400:
        return cached["pem"]
    try:
        r = requests.get(f"{_BLOCKBEE_BASE}/pubkey/", timeout=10)
        pem = str((r.json() or {}).get("pubkey") or "").strip()
        if pem:
            cached["pem"] = pem
            cached["fetched"] = now
            return pem
    except (requests.RequestException, ValueError):
        pass
    return cached["pem"] or _BLOCKBEE_DOC_PUBKEY


def verify_blockbee_signature(raw_body, signature, method="POST", url=""):
    """Verify BlockBee's ``x-ca-signature`` header (RSA-SHA256, base64).

    POST callbacks sign the raw body; GET callbacks sign the full URL.
    """
    signature = str(signature or "").strip()
    if not signature:
        return False
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError:
        return False
    try:
        sig = base64.b64decode(signature)
    except (ValueError, TypeError):
        return False
    try:
        key = serialization.load_pem_public_key(_blockbee_public_key().encode())
    except (ValueError, TypeError):
        return False
    data = url.encode() if str(method).upper() == "GET" else (raw_body or b"")
    if not data:
        return False
    try:
        key.verify(sig, data, padding.PKCS1v15(), hashes.SHA256())
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True


def handle_blockbee_webhook(data, order_ref=""):
    """Apply a verified BlockBee payment callback.

    ``order_id`` is carried as a GET parameter on the callback URL (BlockBee
    keeps custom GET parameters even for POST callbacks); ``address_in`` is the
    fallback identifier. Pending callbacks (``pending=1``) leave the order as is.
    """
    from api.models import PaymentOrder

    if not isinstance(data, dict):
        return False
    order = None
    ref = str(order_ref or data.get("order_id") or "").strip()
    if ref:
        order = PaymentOrder.objects.filter(order_ref=ref).first()
    address_in = str(data.get("address_in") or "").strip()
    if order is None and address_in:
        order = PaymentOrder.objects.filter(provider_order_id=address_in).first()
    if order is None:
        return False
    # Only BlockBee orders may be credited by a BlockBee callback, and the
    # signed address_in must be the one we generated for that order. This stops
    # a replayed body from being redirected to another order via ?order_id=.
    if str(order.provider_token or "").strip() != "blockbee":
        return False
    if not order.provider_order_id or not address_in:
        return False
    if address_in != order.provider_order_id:
        return False

    pending = str(data.get("pending", "")).strip().lower()
    if pending not in {"0", "false", "no"}:
        return False

    txid = str(data.get("txid_in") or "")
    try:
        received = float(data.get("value_coin") or 0)
    except (TypeError, ValueError):
        received = 0.0
    try:
        expected = float(order.amount)
    except (TypeError, ValueError):
        expected = 0.0
    # Never credit an investment for less than the ordered amount. A shortfall
    # is left pending so an admin can review it (BlockBee keeps its logs).
    tolerance = max(1e-8, expected * 0.005)
    if received <= 0 or (expected > 0 and received + tolerance < expected):
        return False

    if order.status == PaymentOrder.STATUS_PAID:
        return False
    order.mark_paid(txid)
    order.investment.confirm()
    return True


def test_provider_connection():
    """Test the active crypto gateway. Returns (ok, message)."""
    mode = _mode()
    if mode != "provider":
        return False, f"Payment mode is '{mode}'. Switch to 'provider' to test."
    if _active_gateway() == "blockbee":
        if not _blockbee_api_key():
            return False, "No BlockBee API key configured (Admin > Payments)."
        try:
            _blockbee_request("GET", "btc/info/")
        except ValueError as exc:
            return False, f"BlockBee API key rejected: {exc}"
        # /info/ is not IP-restricted, but address creation and payouts are.
        try:
            _blockbee_request("GET", "trc20/usdt/payout/balance/")
        except ValueError as exc:
            message = str(exc)
            lowered = message.lower()
            if "ip" in lowered or "whitelist" in lowered:
                return False, (
                    "BlockBee key is IP-restricted — allow this server's IP in "
                    f"the BlockBee dashboard. {message}"
                )
            if "v1 api key" in lowered:
                return False, (
                    "BlockBee payout key is V1; upgrade to API Key V2 for "
                    f"payouts. {message}"
                )
            # No payout wallet yet does not stop deposits.
            return True, f"BlockBee deposits OK; payout check: {message}"
        return True, "BlockBee OK (deposits + payouts)."
    return test_plisio_connection()


def _payment_gateway(order=None):
    """Which provider owns a payment order.

    New BlockBee orders are tagged in ``provider_token``; older Plisio orders
    keep their hosted-invoice URL. Anything else follows the active gateway.
    """
    if order is not None:
        if str(getattr(order, "provider_token", "") or "").strip() == "blockbee":
            return "blockbee"
        if "plisio" in str(getattr(order, "checkout_url", "") or "").lower():
            return "plisio"
    return _active_gateway()


def _payout_gateway(net):
    """Which provider owns a payout/withdrawal (the active gateway)."""
    return _active_gateway()


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
        if _active_gateway() == "blockbee":
            return _create_blockbee_payout(
                coin, to_address, amount, net, order_ref, user
            )
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
        if _active_gateway() == "blockbee":
            return _create_blockbee_payment(investment, ref)
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
            if _payment_gateway(order) == "blockbee":
                state, txid = _blockbee_payment_status(order)
            else:
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
            if _payment_gateway(order) == "blockbee":
                state, txid = _blockbee_payment_status(order)
            else:
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
    """Finalize outstanding gateway orders by polling the active provider.

    - Confirms pending investments whose gateway payment reached a filled state.
    - Finalizes PROCESSING withdrawals/payouts whose gateway payout reached a
      terminal state (completed or failed/refunded).
    Returns (investments_confirmed, transfers_finalized) counts.
    """
    from api.models import PaymentOrder, Payout, Withdrawal

    if _mode() != "provider":
        return 0, 0
    if _active_gateway() == "blockbee":
        if not _blockbee_api_key():
            return 0, 0
    elif not _plisio_api_key():
        return 0, 0

    paid_orders = 0
    orders = PaymentOrder.objects.filter(status=PaymentOrder.STATUS_PENDING).exclude(
        order_ref=""
    )
    for order in orders:
        try:
            if _payment_gateway(order) == "blockbee":
                state, txid = _blockbee_payment_status(order)
            else:
                state, txid = _plisio_payment_status(
                    order.provider_order_id or order.order_ref
                )
        except ValueError:
            continue
        if _apply_payment_status(order, state, txid) == "paid":
            paid_orders += 1

    def _payout_status(provider_id):
        if str(provider_id).startswith("bb:"):
            return _blockbee_payout_status(provider_id)
        return _plisio_payout_status(provider_id)

    transfers = 0
    for wd in Withdrawal.objects.filter(
        status=Withdrawal.STATUS_PROCESSING
    ).exclude(provider_id="").select_related("coin", "user"):
        try:
            status, txid = _payout_status(wd.provider_id)
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
                old_withdrawable = wallet.withdrawable_balance
                wallet.withdrawable_balance += wd.amount
                wallet.save(update_fields=["withdrawable_balance", "updated_at"])
                _log_refund(wd, old_withdrawable, "Gateway payout failed")
                wd.status = Withdrawal.STATUS_FAILED
                wd.reject_reason = f"Gateway payout {status.lower()}."
                wd.save(update_fields=["status", "reject_reason", "updated_at"])
                transfers += 1

    for po in Payout.objects.filter(
        status=Payout.STATUS_PROCESSING
    ).exclude(provider_id="").select_related("coin"):
        try:
            status, txid = _payout_status(po.provider_id)
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