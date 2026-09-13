"""Crypto transfer / payment provider.

The platform moves coins between the platform wallet and users. There are two
integration points, switched by the PlatformSetting ``payment_mode``:

* **Investments** (user pays the platform): ``create_payment_order`` creates a
  payment order that is confirmed by ``confirm_payment`` (simulate), the signed
  gateway webhook (provider), or the Django admin (manual).
* **Withdrawals / payouts** (platform pays the user): ``send_platform_to_user``
  broadcasts a transfer to a user's wallet once approved.

Modes:
    simulate – fake deposit address + fake tx hashes (default)
    provider – POST data to the configured gateway / blockchain RPC
    manual   – a human operator moves coins off-line and enters tx hashes in admin

Provider integration (payment_mode == "provider"):
    Controlled through Admin > Payments (also settable via env):
        PAYMENT_PROVIDER_URL  - BTCPay Server instance base URL (no /api/v1),
                                 e.g. https://testnet.btcpayserver.org
        PAYMENT_PROVIDER_KEY  - BTCPay API key (sent as "Authorization: token ...")
        PAYMENT_STORE_ID      - BTCPay store id that invoices / payouts belong to
        PAYMENT_WEBHOOK_TOKEN - BTCPay webhook secret used to verify "BTCPay-Sig"
        PAYMENT_CALLBACK_URL  - public URL BTCPay POSTs webhooks to
        PAYMENT_SUCCESS_URL   - frontend URL users are redirected to after paying
"""
import hashlib
import hmac
import os
import secrets

import requests
from django.utils import timezone

from api.models import PlatformSettings


def _provider_setting(key, env_name, default=""):
    """Read provider config from PlatformSettings first, then env."""
    val = PlatformSettings.get(key, "")
    if val is not None and val != "":
        return val
    return os.environ.get(env_name, default)


def _webhook_token():
    return _provider_setting(
        PlatformSettings.S_PAYMENT_WEBHOOK_TOKEN,
        "PAYMENT_WEBHOOK_TOKEN",
        "dev-gateway-secret",
    )


def _provider_callback_url():
    """Public URL the gateway POSTs webhooks (IPN) to.

    BTCPay Server cannot reach ``127.0.0.1``, so this must point at a publicly
    reachable host (tunnel / deployed backend), e.g.
    ``https://<tunnel>/api/gateway/webhook/``.
    """
    return _provider_setting(
        PlatformSettings.S_PAYMENT_CALLBACK_URL,
        "PAYMENT_CALLBACK_URL",
    )


def _btcpay_store_id():
    """BTCPay store id that invoices and payouts belong to."""
    return _provider_setting(
        PlatformSettings.S_PAYMENT_STORE_ID,
        "PAYMENT_STORE_ID",
    )


def _btcpay_success_url():
    """Frontend URL users are redirected to after settling a BTCPay invoice."""
    return _provider_setting(
        PlatformSettings.S_PAYMENT_SUCCESS_URL,
        "PAYMENT_SUCCESS_URL",
    )


def _platform_deposit_address(coin):
    """Platform's deposit address for a coin (is_platform CryptoAccount)."""
    from api.models import CryptoAccount
    acc = CryptoAccount.objects.select_related("user").filter(
        coin=coin, is_platform=True
    ).first()
    if acc:
        return acc.address
    return _fake_address(coin)


def test_gateway_connection():
    """Test provider connectivity. Returns (ok, message)."""
    mode = _mode()
    if mode != "provider":
        return False, f"Payment mode is '{mode}'. Switch to 'provider' to test."
    base_url = _provider_setting(
        PlatformSettings.S_PAYMENT_PROVIDER_URL,
        "PAYMENT_PROVIDER_URL",
    ).strip().rstrip("/")
    key = _provider_setting(
        PlatformSettings.S_PAYMENT_PROVIDER_KEY,
        "PAYMENT_PROVIDER_KEY",
    )
    if not base_url:
        return False, "No provider URL configured."
    if not key:
        return False, "No API key configured."
    try:
        # BTCPay: GET /api/v1/api-keys/current validates the key.
        r = requests.get(
            f"{base_url}/api/v1/api-keys/current",
            headers={"Authorization": f"token {key}"},
            timeout=10,
        )
        if r.ok:
            try:
                data = r.json()
                perms = data.get("permissions") or []
                return True, f"BTCPay API key OK ({len(perms)} permissions)."
            except Exception:
                return True, "BTCPay API key OK."
        if r.status_code in (401, 403):
            return False, "Invalid BTCPay API key."
        return False, f"Provider responded HTTP {r.status_code}: {r.text[:200]}"
    except requests.RequestException as exc:
        return False, f"Connection failed: {exc}"

# Environment keys used when payment_mode == "provider"
#   PAYMENT_PROVIDER_URL  - BTCPay instance base URL (no /api/v1)
#   PAYMENT_PROVIDER_KEY  - BTCPay API key
#   PAYMENT_STORE_ID      - BTCPay store id
#   PAYMENT_WEBHOOK_TOKEN - BTCPay webhook secret for BTCPay-Sig verification


def _mode():
    mode = PlatformSettings.get("payment_mode", "simulate").lower()
    return mode if mode in {"simulate", "provider", "manual"} else "simulate"


def send_platform_to_user(coin, to_address, amount, network=""):
    """Admin/platform wallet -> user wallet. Returns tx_hash or ''.

    Used by payouts and withdrawals once admin approves them.
    """
    amount = float(amount)
    if amount <= 0:
        raise ValueError("Amount must be positive")
    mode = _mode()
    if mode == "manual":
        # A human operator transfers off-line and fills in the tx hash in admin.
        return ""
    if mode == "provider":
        # BTCPay: broadcast directly from the store wallet to the user's address
        # using the Greenfield wallet-transactions endpoint. This transfers the
        # coins automatically once admin approves the payout / withdrawal.
        base_url = _provider_setting(
            PlatformSettings.S_PAYMENT_PROVIDER_URL,
            "PAYMENT_PROVIDER_URL",
        ).strip().rstrip("/")
        key = _provider_setting(
            PlatformSettings.S_PAYMENT_PROVIDER_KEY,
            "PAYMENT_PROVIDER_KEY",
        )
        store = _btcpay_store_id()
        if not base_url or not key or not store:
            raise ValueError(
                "BTCPay is not configured. Set the provider URL, API key and store ID in Admin > Payments."
            )
        crypto = str(coin.symbol or "BTC").upper()
        body = {
            "destination": to_address,
            "amount": str(round(amount, 8)),
            "subtractFees": True,
        }
        try:
            r = requests.post(
                f"{base_url}/api/v1/stores/{store}/payment-methods/onchain/{crypto}/wallet/transactions",
                headers={"Authorization": f"token {key}", "Content-Type": "application/json"},
                json=body,
                timeout=60,
            )
        except requests.RequestException as exc:
            raise ValueError(f"BTCPay send failed: {exc}") from exc
        if not r.ok:
            raise ValueError(f"BTCPay refused the transfer: HTTP {r.status_code} {_btcpay_error_detail(r)}")
        data = r.json()
        tx = str(
            data.get("transactionId")
            or data.get("result", {}).get("transactionId")
            or ""
        )
        if not tx:
            raise ValueError("BTCPay accepted the transfer but returned no transaction id.")
        return tx
    # simulate
    return _simulated_hash("send")


def receive_from_user(coin, from_address, amount, network=""):
    """User wallet -> platform wallet. Returns tx_hash or ''.

    Kept for the old auto-confirm invest flow; the current flow uses
    PaymentOrder + confirm_payment / webhook instead. In production this is
    confirmed by a deposit watcher (webhook / on-chain scan).
    """
    if _mode() == "manual":
        return ""
    return _simulated_hash("receive")


def _simulated_hash(kind):
    return f"SIM-{timezone.now():%Y%m%d%H%M%S}-{secrets.token_hex(6)}"


def _fake_address(coin):
    """Deterministic fake deposit address so simulate mode looks realistic."""
    net = (coin.chain or "TRC20").upper()
    prefix = {"TRC20": "T", "BEP20": "0x", "BEP2": "bnb1", "ERC20": "0x", "SOL": "", "TON": "UQ"}[net]
    return f"{prefix}{secrets.token_hex(20)}"


def estimated_network_fee(coin, amount):
    """Return simulated network fee estimate for the withdrawal fee."""
    return 0.0


# ---------------------------------------------------------------------------
# Investment / payment checkout
# ---------------------------------------------------------------------------


def verify_webhook_signature(raw_body, signature):
    """Verify an HMAC-SHA256 signature over the raw POST body."""
    if not signature:
        return False
    expected = hmac.new(_webhook_token().encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_nowpayments_signature(raw_body, signature):
    """Verify a NOWPayments IPN signature (HMAC-SHA512 over the raw body).

    NOWPayments signs ``JSON.stringify(sorted params)`` with the IPN secret
    key and delivers it in the ``x-nowpayments-sig`` header.
    """
    if not signature:
        return False
    expected = hmac.new(_webhook_token().encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_btcpay_signature(raw_body, signature):
    """Verify a BTCPay webhook signature (``BTCPay-Sig: sha256=<hex>``).

    HMAC-SHA256 over the raw POST body with the webhook secret.
    """
    if not signature:
        return False
    signature = signature.strip()
    if "=" in signature:
        signature = signature.split("=", 1)[-1].strip()
    expected = hmac.new(_webhook_token().encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


_BTCPAY_PAID_EVENTS = {"invoicesettled", "invoiceprocessingsettled"}
_BTCPAY_FAILED_EVENTS = {"invoiceexpired", "invoiceinvalid"}
_BTCPAY_PAID_STATUSES = {"settled"}
_BTCPAY_FAILED_STATUSES = {"expired", "invalid"}


def _btcpay_error_detail(r):
    """Best-effort human-readable error message from a BTCPay error response."""
    detail = r.text[:300]
    try:
        err = r.json()
        if isinstance(err, dict):
            detail = err.get("message") or err.get("code") or detail
    except Exception:
        pass
    return detail


def _create_btcpay_order(coin, amount, order_ref):
    """Create a BTCPay Server invoice and return the checkout payload.

    Uses PAYMENT_PROVIDER_URL/KEY/STORE_ID (DB first, then env). The customer
    pays at ``checkoutLink`` (BTCPay's hosted checkout); BTCPay's webhook
    (BTCPay-Sig) confirms the order when the invoice is Settled.
    """
    base_url = _provider_setting(
        PlatformSettings.S_PAYMENT_PROVIDER_URL,
        "PAYMENT_PROVIDER_URL",
    ).strip().rstrip("/")
    key = _provider_setting(
        PlatformSettings.S_PAYMENT_PROVIDER_KEY,
        "PAYMENT_PROVIDER_KEY",
    )
    store = _btcpay_store_id()
    common = {
        "coin_symbol": coin.symbol,
        "chain": coin.chain,
        "amount": _amount_str(coin, amount),
        "payment_mode": "provider",
    }
    if not base_url or not key or not store:
        return {
            "order_ref": order_ref,
            "status": "failed",
            "address": "",
            "checkout_url": "",
            "message": "Gateway is not configured. Set the provider URL, API key and store ID in Admin > Payments.",
            **common,
        }

    body = {
        "amount": str(round(float(amount), 8)),
        "currency": str(coin.symbol).upper(),
        "orderId": order_ref,
        "metadata": {"orderId": order_ref, "coin": coin.symbol, "chain": coin.chain},
    }
    success_url = _btcpay_success_url()
    if success_url:
        body["redirectURL"] = success_url
    headers = {"Authorization": f"token {key}", "Content-Type": "application/json"}
    try:
        r = requests.post(
            f"{base_url}/api/v1/stores/{store}/invoices",
            headers=headers,
            json=body,
            timeout=30,
        )
        if not r.ok:
            return {
                "order_ref": order_ref,
                "status": "failed",
                "address": "",
                "checkout_url": "",
                "message": f"Gateway responded HTTP {r.status_code}: {_btcpay_error_detail(r)}",
                **common,
            }
        data = r.json()
        invoice_id = str(data.get("id") or "")
        return {
            "order_ref": order_ref,
            "status": "pending",
            "address": "",
            "checkout_url": data.get("checkoutLink") or "",
            "provider_order_id": invoice_id,
            "provider_token": invoice_id,
            **common,
        }
    except requests.RequestException as exc:
        return {
            "order_ref": order_ref,
            "status": "failed",
            "address": "",
            "checkout_url": "",
            "message": f"Gateway connection failed: {exc}",
            **common,
        }


def _amount_str(coin, amount):
    try:
        return f"{float(amount):.{8}f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(amount)


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

    if mode == "manual":
        # The user sends manually and the admin confirms the investment.
        return {"order_ref": "", "status": "manual", "address": "", "checkout_url": "", **common}

    ref = f"ORD-{timezone.now():%Y%m%d%H%M%S}-{secrets.token_hex(4).upper()}"
    if mode == "provider":
        # Provider mode: create a real BTCPay Server invoice; the customer pays
        # at checkout_url. BTCPay's webhook confirms the order once Settled,
        # and/or the user polls the invoice status with "I have paid".
        return _create_btcpay_order(coin, amount, ref)

    # simulate: show the platform's deposit address and confirm on "I paid".
    return {
        "order_ref": ref,
        "status": "pending",
        "address": _platform_deposit_address(coin),
        "checkout_url": "",
        **common,
    }


def confirm_payment(order_ref):
    """Confirm a payment order and return (ok, tx_hash, message).

    simulate: trusts the user's confirmation (order was "paid" off-screen).
    provider: queries BTCPay's invoice; only returns ok when the invoice is Settled.
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
        # Query the BTCPay invoice and only confirm when it is Settled.
        base_url = _provider_setting(
            PlatformSettings.S_PAYMENT_PROVIDER_URL,
            "PAYMENT_PROVIDER_URL",
        ).strip().rstrip("/")
        key = _provider_setting(
            PlatformSettings.S_PAYMENT_PROVIDER_KEY,
            "PAYMENT_PROVIDER_KEY",
        )
        store = _btcpay_store_id()
        if not base_url or not key or not store:
            return False, "", "Gateway is not configured."
        if not order.provider_order_id:
            return False, "", "No BTCPay invoice for this order."
        try:
            r = requests.get(
                f"{base_url}/api/v1/stores/{store}/invoices/{order.provider_order_id}",
                headers={"Authorization": f"token {key}"},
                timeout=15,
            )
        except requests.RequestException as exc:
            return False, "", f"Gateway check failed: {exc}"
        if not r.ok:
            return False, "", f"Gateway responded HTTP {r.status_code}."
        data = r.json()
        status = (data.get("status") or "").lower()
        if status in _BTCPAY_PAID_STATUSES:
            tx = str(data.get("transactionId") or "")
            order.mark_paid(tx)
            order.investment.confirm()
            return True, order.tx_hash, "paid"
        if status in _BTCPAY_FAILED_STATUSES:
            order.status = PaymentOrder.STATUS_FAILED
            order.save(update_fields=["status", "updated_at"])
            return False, "", f"Payment {status} on BTCPay."
        return False, "", f"Payment still {status or 'unknown'} on BTCPay."

    # simulate
    tx = _simulated_hash("receive")
    order.mark_paid(tx)
    return True, tx, "paid"


def handle_gateway_webhook(data):
    """Apply a verified gateway callback.

    Generic payload:   {"order_ref": str, "status": "PAID"|..., "tx_hash": str|""}
    NOWPayments IPN:   {"order_id": str, "payment_status": str, ...}
    BTCPay webhook:    {"type": "InvoiceSettled", "invoiceId": str, ...}
    Returns True when the callback was applied (accepted or order updated).
    """
    from api.models import PaymentOrder

    # BTCPay webhook shape: {"type": "InvoiceSettled", "invoiceId": "...", ...}
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