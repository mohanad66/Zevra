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

from api.models import PlatformSettings

_PAYRAM_ENVS = ("test", "production")


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
        code = str(payload.get("code") or "")
        if message:
            text = str(message)[:300]
            if "BLOCKCHAIN_NODE_NOT_FOUND" in code or "not found" in text.lower():
                text += (
                    " Configure and enable this blockchain's node and deposit "
                    "wallet in the PayRam dashboard first."
                )
            return text
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

# UI network label (what Invest.jsx sends in `source_address`) -> PayRam
# blockchain code used by the Assign Deposit Address API. Only networks where
# PayRam deploys a real deposit wallet are listed; unsupported choices are
# rejected with a clear message.
_PAYRAM_DEPOSIT_CODES = {
    "TRC20": "TRX",
    "POL": "POLYGON",
    "ERC20": "ETH",
    "BASE": "BASE",
    "BTC": "BTC",
    # BEP20 (BSC) and SOL are added per the owner's request even though PayRam
    # does not currently deploy deposit wallets for those blockchains (its
    # supported node codes are BTC / ETH / BASE / POLYGON / TRX only). If the
    # PayRam instance lacks a BNB / Solana node, the Assign Deposit Address
    # call will simply fail on those choices — same behaviour as a disabled,
    # "coming soon" chip, with the error surfaced back to the user.
    "BEP20": "BSC",
    "SOL": "SOLANA",
}

# Currency code keys PayRam understands when creating payouts (native token
# symbols are used as-is; tokens are addressed by their contract/hot wallet).
_PAYRAM_CURRENCY = {}

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
    "SOL": "SOL",
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
        amount_usd = _payram_usd_amount(coin, amount)
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
    same vocabulary PayRam used (FILLED / OVER_FILLED / CANCELLED / PENDING),
    so the existing _PAYRAM_PAYMENT_PAID / _PAYRAM_PAYMENT_FAILED checks work
    unchanged."""
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
    currency = _PAYRAM_CURRENCY.get(str(coin.symbol).upper(), str(coin.symbol).upper())
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
    PayRam vocabulary (SENT / FAILED / PROCESSING) the existing
    _PAYRAM_PAYOUT_DONE / _PAYRAM_PAYOUT_FAILED checks expect."""
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


_PAYRAM_PAYOUT_CHAINS = {
    "TRC20": "TRX",
    "ERC20": "ETH",
    "ETH20": "ETH",
    "POL": "POLYGON",
    "POLYGON": "POLYGON",
    "BEP20": "BSC",
    "BASE": "BASE",
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
        return _create_payram_payout(coin, to_address, amount, order_ref, user, network)
    # simulate
    return _simulated_hash("send")


def _create_payram_payout(coin, to_address, amount, order_ref=None, user=None, network=""):
    """Create a PayRam payout to the user's address. Returns its PayRam id."""
    env, base, key = _payram_active()
    if not base or not key:
        raise ValueError(
            "PayRam is not configured. Set the BASE_URL and API key for the "
            "active environment in Admin > Payments."
        )
    net = _PAYRAM_PAYOUT_CHAINS.get((network or coin.chain or "").upper())
    if not net:
        raise ValueError(
            f"PayRam does not support payouts on {network or coin.chain or coin.symbol}. "
            "Supported chains: ETH, BASE, POLYGON, TRX, BSC."
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


def _payram_deposit_address(reference_id, blockchain_code):
    """Assign a static PayRam deposit address for the user on a blockchain.

    PayRam reuses this address for every future payment in the same blockchain
    family, so it is safe to show it with the QR code on our own checkout page.
    """
    _, _, key = _payram_active()
    payload = _payram_post(
        f"/deposit-address/reference/{reference_id}",
        {"blockchain_code": blockchain_code},
        key,
    )
    address = str(payload.get("Address") or payload.get("address") or "")
    if not address:
        raise ValueError("PayRam did not return a deposit address.")
    return address


def _create_payram_payment(investment, order_ref):
    """Create a PayRam payment and hand the user a deposit address.

    Returns the checkout payload the frontend renders directly on the Miyar
    Trading site (QR code + address), instead of redirecting to the PayRam
    hosted checkout page:

        {"order_ref", "status", "address", "chain", "amount", "payment_mode",
         "provider_order_id" (PayRam reference_id), "pay_amount", "pay_currency"}

    PayRam monitors the address and pushes a ``FILLED`` webhook (plus we poll
    with ``payment_order_status``) so the order confirms without the user ever
    leaving our frontend.
    """
    coin = investment.coin
    amount = float(investment.amount)
    env, base, key = _payram_active()
    user = investment.user
    net_label = (investment.source_address or "").strip().upper() or coin.chain
    common = {
        "coin_symbol": coin.symbol,
        "chain": net_label,
        "amount": investment.amount,
        "payment_mode": "provider",
        "order_ref": order_ref,
        "gateway": "payram",
    }
    blockchain_code = _PAYRAM_DEPOSIT_CODES.get(net_label)
    if not blockchain_code:
        return {
            "status": "failed",
            "address": "",
            "checkout_url": "",
            "message": f"{net_label} is not supported by the payment gateway. "
            f"Choose one of: {', '.join(sorted(_PAYRAM_DEPOSIT_CODES))}.",
            **common,
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
    if not ref_id:
        return {
            "status": "failed",
            "address": "",
            "checkout_url": "",
            "message": "PayRam created the payment but returned no reference_id.",
            **common,
        }
    try:
        address = _payram_deposit_address(ref_id, blockchain_code)
    except ValueError as exc:
        return {
            "status": "failed",
            "address": "",
            "checkout_url": "",
            "message": str(exc),
            **common,
        }
    return {
        "status": "pending",
        "address": address,
        "checkout_url": "",
        "pay_amount": str(investment.amount),
        "pay_currency": coin.symbol,
        "provider_order_id": ref_id,
        "provider_token": ref_id,
        "amount_usd": f"{amount_usd:.2f}",
        **common,
    }


def _payram_payment_status(reference_id):
    """Poll a PayRam payment by reference id. Returns (state, tx_hash).

    The docs use ``paymentState``; older PayRam releases returned ``status``,
    so both are accepted.
    """
    _, base, key = _payram_active()
    payload = _payram_get(f"/payment/reference/{reference_id}", key)
    state = str(payload.get("paymentState") or payload.get("status") or "").upper()
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


def _apply_payram_payment_status(order, state, tx=""):
    """Apply a PayRam payment state to an order. Idempotent.

    Returns a machine status key: "paid" | "failed" | "pending".
    """
    state = str(state or "").upper()
    if state in _PAYRAM_PAYMENT_PAID:
        if order.status != PaymentOrder.STATUS_PAID:
            order.mark_paid(tx)
            order.investment.confirm()
        return "paid"
    if state in _PAYRAM_PAYMENT_FAILED:
        if order.status != PaymentOrder.STATUS_PAID:
            order.status = PaymentOrder.STATUS_FAILED
            order.save(update_fields=["status", "updated_at"])
        return "failed"
    return "pending"


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
            state, txid = _payram_payment_status(order.provider_order_id or order.order_ref)
        except ValueError as exc:
            return False, "", f"Gateway check failed: {exc}"
        result = _apply_payram_payment_status(order, state, txid)
        if result == "paid":
            return True, order.tx_hash, "paid"
        if result == "failed":
            return False, "", f"Payment {state} on PayRam."
        return False, "", f"Payment still {state or 'unknown'} on PayRam."

    # simulate
    tx = _simulated_hash("receive")
    order.mark_paid(tx)
    return True, tx, "paid"


def payment_order_status(order_ref):
    """Machine-readable status for one payment order (user status checker).

    In provider mode it polls PayRam, so a payment that PayRam already marked
    FILLED is confirmed even when an earlier webhook delivery was missed.

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
            state, txid = _payram_payment_status(order.provider_order_id or order.order_ref)
        except ValueError:
            state, txid = None, ""
        if state:
            _apply_payram_payment_status(order, state, txid)

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

    tx = ""
    info = data.get("payment_info")
    if isinstance(info, list) and info and isinstance(info[0], dict):
        tx = str(info[0].get("transaction_hash") or "")
    previous = order.status
    _apply_payram_payment_status(order, status, tx)
    return order.status != previous


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
    if not key:
        return False, "No PayRam API key configured for the active environment."
    try:
        rows = _payram_get("/ticker", "")
        count = len(rows) if isinstance(rows, list) else 0
    except (requests.RequestException, ValueError) as exc:
        return False, f"Connection failed: {exc}"
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
    _, base, key = _payram_active()
    if not base or not key:
        return 0, 0

    paid_orders = 0
    orders = PaymentOrder.objects.filter(status=PaymentOrder.STATUS_PENDING).exclude(
        order_ref=""
    )
    for order in orders:
        try:
            state, txid = _payram_payment_status(order.provider_order_id or order.order_ref)
        except ValueError:
            continue
        if _apply_payram_payment_status(order, state, txid) == "paid":
            paid_orders += 1

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