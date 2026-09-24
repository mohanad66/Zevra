"""
Switch payments AND payouts from PayRam to Cryptomus.

Run from the project root (~/Zevra/Zevra), AFTER the three earlier patches
(patch_services_network.py, patch_manual_networks.py, patch_payouts.py):

    python3 patch_cryptomus.py

Then set in .env (see the message this script prints) and rebuild:

    docker compose up -d --build api

This does NOT delete the old PayRam code -- it adds Cryptomus functions next
to it and redirects the call sites (create_payment_order, confirm_payment,
reconcile_gateway, send_platform_to_user, test_payram_connection, and the
gateway webhook) to use them. The old PayRam functions become unused but are
left in place, so nothing else breaks if something needs to be compared.
"""
import re

# =============================================================================
# 1. models.py -- Cryptomus settings keys
# =============================================================================
p = "backend/api/models.py"
s = open(p).read()
anchor = '    S_PAYRAM_API_KEY_PROD = "payram_api_key_production"'
assert anchor in s, "PlatformSettings PayRam keys block not found"
if "S_CRYPTOMUS_MERCHANT_ID" not in s:
    s = s.replace(
        anchor,
        anchor + '\n\n'
        '    S_CRYPTOMUS_MERCHANT_ID = "cryptomus_merchant_id"\n'
        '    S_CRYPTOMUS_PAYMENT_KEY = "cryptomus_payment_key"\n'
        '    S_CRYPTOMUS_PAYOUT_KEY = "cryptomus_payout_key"',
        1,
    )
    open(p, "w").write(s)
    print("models.py patched: Cryptomus settings keys added")
else:
    print("models.py: Cryptomus settings keys already present, skipped")

# =============================================================================
# 2. services.py
# =============================================================================
p = "backend/api/services.py"
s = open(p).read()

def rep(old, new, count=1, label=""):
    global s
    n = s.count(old)
    assert n == count, f"{label or old[:60]!r}: expected {count} occurrence(s), found {n}"
    s = s.replace(old, new, count)

# --- 2a. imports: need base64 -----------------------------------------------
if "\nimport base64\n" not in s:
    rep("import hashlib\nimport hmac\n", "import base64\nimport hashlib\nimport hmac\n",
        label="import block")

# --- 2b. Cryptomus config + HTTP + gateway functions (inserted once) --------
if "_cryptomus_merchant_id" not in s:
    anchor = "_PAYRAM_PAYOUT_CHAINS = {"
    assert anchor in s, "anchor for Cryptomus block not found"
    cryptomus_block = '''# ---------------------------------------------------------------------------
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
    if not url:
        return {"status": "failed", "address": "", "checkout_url": "",
                "message": "Cryptomus created the payment but returned no checkout url.", **common}
    return {
        "status": "pending",
        "address": str(result.get("address") or ""),
        "checkout_url": url,
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
        po.note = f"{po.note}\\nCryptomus payout {status or 'failed'}.".strip()
        po.save(update_fields=["status", "note", "updated_at"])
        return True
    return False


'''
    rep(anchor, cryptomus_block + anchor, label="Cryptomus block insertion")
    print("services.py patched: Cryptomus config/HTTP/webhook functions added")
else:
    print("services.py: Cryptomus functions already present, skipped block insert")

# --- 2c. create_payment_order: provider branch -> Cryptomus -----------------
old_manual_branch = '''    if mode == "provider":
        net = (investment.source_address or "").strip().upper()
        if net in _MANUAL_NETWORKS:
            manual = {
                **common,
                "order_ref": ref,
                "chain": net,
                "payment_mode": "manual",
                "checkout_url": "",
            }
            if str(coin.chain or "").upper() != net:
                return {**manual, "status": "failed", "address": "",
                        "message": f"Choose the {net} coin to pay on {net}."}
            address = _real_platform_address(coin)
            if not address:
                return {**manual, "status": "failed", "address": "",
                        "message": f"{net} payments are not set up yet."}
            return {**manual, "status": "manual", "address": address}
        return _create_payram_payment(investment, ref)'''
old_plain_branch = '''    if mode == "provider":
        return _create_payram_payment(investment, ref)'''
new_branch = '''    if mode == "provider":
        return _create_cryptomus_payment(investment, ref)'''
if old_manual_branch in s:
    rep(old_manual_branch, new_branch, label="create_payment_order provider branch (manual-SOL variant)")
    print("services.py patched: create_payment_order now calls Cryptomus "
          "(manual-SOL workaround removed -- Cryptomus supports SOL directly)")
elif old_plain_branch in s:
    rep(old_plain_branch, new_branch, label="create_payment_order provider branch (plain variant)")
    print("services.py patched: create_payment_order now calls Cryptomus")
elif "_create_cryptomus_payment(investment, ref)" in s:
    print("services.py: create_payment_order already calls Cryptomus, skipped")
else:
    raise AssertionError("create_payment_order provider branch not found in a recognised form")

# --- 2d. confirm_payment: provider branch -----------------------------------
old = '''            status, txid = _payram_payment_status(order.provider_order_id or order.order_ref)
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
        return False, "", f"Payment still {status or 'unknown'} on PayRam."'''
new = '''            status, txid = _cryptomus_payment_status(order.order_ref)
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
            return False, "", f"Payment {status} on Cryptomus."
        return False, "", f"Payment still {status or 'unknown'} on Cryptomus."'''
if old in s:
    rep(old, new, label="confirm_payment provider branch")
    print("services.py patched: confirm_payment now polls Cryptomus")
elif "_cryptomus_payment_status(order.order_ref)" in s:
    print("services.py: confirm_payment already uses Cryptomus, skipped")
else:
    raise AssertionError("confirm_payment provider branch not found")

# --- 2e. send_platform_to_user: provider branch ------------------------------
old = '''    if mode == "provider":
        return _create_payram_payout(coin, to_address, amount, order_ref, user)'''
new = '''    if mode == "provider":
        return _create_cryptomus_payout(coin, to_address, amount, network, order_ref, user)'''
if old in s:
    rep(old, new, label="send_platform_to_user provider branch")
    print("services.py patched: send_platform_to_user now creates Cryptomus payouts")
elif "_create_cryptomus_payout(coin, to_address, amount, network, order_ref, user)" in s:
    print("services.py: send_platform_to_user already uses Cryptomus, skipped")
else:
    raise AssertionError("send_platform_to_user provider branch not found")

# --- 2f. reconcile_gateway: config guard + 3 status calls --------------------
old_guard = '''    if _mode() != "provider":
        return 0, 0
    env, base, key = _payram_active()
    if not base or not key:
        return 0, 0'''
new_guard = '''    if _mode() != "provider":
        return 0, 0
    if not _cryptomus_merchant_id() or not _cryptomus_payment_key():
        return 0, 0'''
if old_guard in s:
    rep(old_guard, new_guard, label="reconcile_gateway config guard")
    print("services.py patched: reconcile_gateway guard now checks Cryptomus config")
elif "_cryptomus_merchant_id() or not _cryptomus_payment_key()" in s:
    print("services.py: reconcile_gateway guard already Cryptomus, skipped")
else:
    raise AssertionError("reconcile_gateway config guard not found")

rep(
    'status, txid = _payram_payment_status(order.provider_order_id or order.order_ref)',
    'status, txid = _cryptomus_payment_status(order.order_ref)',
    label="reconcile_gateway payment status call",
) if 'status, txid = _payram_payment_status(order.provider_order_id or order.order_ref)' in s else None

rep(
    '''    for wd in Withdrawal.objects.filter(
        status=Withdrawal.STATUS_PROCESSING
    ).exclude(provider_id="").select_related("coin", "user"):
        try:
            status, txid = _payram_payout_status(wd.provider_id)''',
    '''    for wd in Withdrawal.objects.filter(
        status=Withdrawal.STATUS_PROCESSING
    ).exclude(provider_id="").select_related("coin", "user"):
        try:
            status, txid = _cryptomus_payout_status(wd.provider_id)''',
    label="reconcile_gateway withdrawal payout status call",
) if '''    for wd in Withdrawal.objects.filter(
        status=Withdrawal.STATUS_PROCESSING
    ).exclude(provider_id="").select_related("coin", "user"):
        try:
            status, txid = _payram_payout_status(wd.provider_id)''' in s else None

rep(
    '''                wd.status = Withdrawal.STATUS_FAILED
                wd.reject_reason = f"PayRam payout {status.lower()}."''',
    '''                wd.status = Withdrawal.STATUS_FAILED
                wd.reject_reason = f"Cryptomus payout {status.lower()}."''',
) if '''                wd.status = Withdrawal.STATUS_FAILED
                wd.reject_reason = f"PayRam payout {status.lower()}."''' in s else None

rep(
    '''    for po in Payout.objects.filter(
        status=Payout.STATUS_PROCESSING
    ).exclude(provider_id="").select_related("coin"):
        try:
            status, txid = _payram_payout_status(po.provider_id)''',
    '''    for po in Payout.objects.filter(
        status=Payout.STATUS_PROCESSING
    ).exclude(provider_id="").select_related("coin"):
        try:
            status, txid = _cryptomus_payout_status(po.provider_id)''',
    label="reconcile_gateway payout status call",
) if '''    for po in Payout.objects.filter(
        status=Payout.STATUS_PROCESSING
    ).exclude(provider_id="").select_related("coin"):
        try:
            status, txid = _payram_payout_status(po.provider_id)''' in s else None

rep(
    '''                po.note = f"{po.note}\\nPayRam payout {status.lower()}.".strip()''',
    '''                po.note = f"{po.note}\\nCryptomus payout {status.lower()}.".strip()''',
) if '''                po.note = f"{po.note}\\nPayRam payout {status.lower()}.".strip()''' in s else None

print("services.py patched: reconcile_gateway now polls Cryptomus (idempotent, safe to re-run)")

# --- 2g. test_payram_connection: test Cryptomus instead ----------------------
old = '''def test_payram_connection():
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
    return True, f"PayRam OK ({env}, {count} currencies ticker)."'''
new = '''def test_payram_connection():
    """Test the active Cryptomus credentials. Returns (ok, message).

    Kept under its old name so AdminProviderTestView (views.py) needs no edit.
    """
    mode = _mode()
    if mode != "provider":
        return False, f"Payment mode is '{mode}'. Switch to 'provider' to test."
    merchant = _cryptomus_merchant_id()
    payment_key = _cryptomus_payment_key()
    if not merchant or not payment_key:
        return False, "CRYPTOMUS_MERCHANT_ID / CRYPTOMUS_PAYMENT_API_KEY are not configured."
    try:
        result = _cryptomus_post("/payment/services", {}, payment_key)
    except ValueError as exc:
        return False, f"Connection failed: {exc}"
    count = len(result) if isinstance(result, list) else 0
    payout_key = _cryptomus_payout_key()
    note = ""
    if payout_key:
        try:
            _cryptomus_post("/payout/services", {}, payout_key)
        except ValueError as exc:
            note = f" Payout key check: {exc}"
    else:
        note = " No payout key set (payouts will fail until CRYPTOMUS_PAYOUT_API_KEY is set)."
    return True, f"Cryptomus OK ({count} payment services).{note}"'''
if old in s:
    rep(old, new, label="test_payram_connection body")
    print("services.py patched: test_payram_connection now tests Cryptomus")
elif '"Cryptomus OK (' in s:
    print("services.py: test_payram_connection already tests Cryptomus, skipped")
else:
    raise AssertionError("test_payram_connection body not found in a recognised form")

open(p, "w").write(s)

# =============================================================================
# 3. views.py -- wire the Cryptomus webhook into the gateway dispatcher
# =============================================================================
p = "backend/api/views.py"
s = open(p).read()

old_import_tail = "    verify_payram_signature,"
assert old_import_tail in s, "verify_payram_signature import line not found in views.py"
if "verify_cryptomus_signature" not in s:
    rep_v = s.replace(
        old_import_tail,
        old_import_tail + "\n    verify_cryptomus_signature,\n    handle_cryptomus_webhook,",
        1,
    )
    assert rep_v != s
    s = rep_v
    print("views.py patched: Cryptomus imports added")
else:
    print("views.py: Cryptomus imports already present, skipped")

old_dispatch = '''        ok = (
            bool(sig_payram and verify_payram_signature(raw, sig_payram))
            or bool(sig_gateway and verify_webhook_signature(raw, sig_gateway))
            or bool(sig_btcpay and verify_btcpay_signature(raw, sig_btcpay))
            or bool(sig_nowpayments and verify_nowpayments_signature(raw, sig_nowpayments))
        )
        if not ok:
            return response.Response(
                {"detail": "Bad signature."}, status=status.HTTP_400_BAD_REQUEST
            )
        data = _parse_webhook_body(raw)
        if data is None:
            return response.Response(
                {"detail": "Invalid payload."}, status=status.HTTP_400_BAD_REQUEST
            )
        event = str(data.get("event_type") or "").lower()
        if event.startswith("payout."):
            handled = handle_payram_payout_webhook(data)
        elif data.get("reference_id") or data.get("invoice_id") or data.get("paymentState"):
            handled = handle_payram_payment_webhook(data)
        else:
            handled = handle_gateway_webhook(data)'''
new_dispatch = '''        data = _parse_webhook_body(raw)
        header_ok = (
            bool(sig_payram and verify_payram_signature(raw, sig_payram))
            or bool(sig_gateway and verify_webhook_signature(raw, sig_gateway))
            or bool(sig_btcpay and verify_btcpay_signature(raw, sig_btcpay))
            or bool(sig_nowpayments and verify_nowpayments_signature(raw, sig_nowpayments))
        )
        # Cryptomus signs the JSON body itself ("sign" field), not a header.
        is_cryptomus = isinstance(data, dict) and "sign" in data and not header_ok
        cryptomus_ok = is_cryptomus and verify_cryptomus_signature(data)
        if not (header_ok or cryptomus_ok):
            return response.Response(
                {"detail": "Bad signature."}, status=status.HTTP_400_BAD_REQUEST
            )
        if data is None:
            return response.Response(
                {"detail": "Invalid payload."}, status=status.HTTP_400_BAD_REQUEST
            )
        if cryptomus_ok:
            handled = handle_cryptomus_webhook(data)
        else:
            event = str(data.get("event_type") or "").lower()
            if event.startswith("payout."):
                handled = handle_payram_payout_webhook(data)
            elif data.get("reference_id") or data.get("invoice_id") or data.get("paymentState"):
                handled = handle_payram_payment_webhook(data)
            else:
                handled = handle_gateway_webhook(data)'''
if old_dispatch in s:
    rep(old_dispatch, new_dispatch, label="GatewayWebhookView dispatch block")
    print("views.py patched: webhook dispatcher now recognises Cryptomus callbacks")
elif "handled = handle_cryptomus_webhook(data)" in s:
    print("views.py: webhook dispatcher already wired for Cryptomus, skipped")
else:
    raise AssertionError("GatewayWebhookView dispatch block not found in a recognised form")

open(p, "w").write(s)

print("""
Done. Now:

1. Add to .env (get these from the Cryptomus dashboard > Settings):

     CRYPTOMUS_MERCHANT_ID=<merchant uuid>
     CRYPTOMUS_PAYMENT_API_KEY=<Payment API key>
     CRYPTOMUS_PAYOUT_API_KEY=<Payout API key>

   Payment mode stays PAYMENT_MODE=provider (unchanged meaning).

2. In the Cryptomus dashboard, set the webhook URL to:

     https://api.miyartrading.com/api/gateway/webhook/

   (or set PAYMENT_CALLBACK_URL in .env if your API domain differs)

3. Clear any stale PlatformSettings rows for the OLD PayRam config so nothing
   shadows the new .env values (same caution as before):

     docker compose exec api python manage.py shell
     >>> from api.models import PlatformSettings as P
     >>> P.objects.filter(key__startswith="payram").delete()

4. Rebuild:

     docker compose up -d --build api
""")