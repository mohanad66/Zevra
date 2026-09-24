"""
Run from the project root AFTER patch_cryptomus.py:

    python3 patch_cryptomus_inline.py

Makes the invoice response carry the exact crypto amount/currency Cryptomus
calculated (payer_amount/payer_currency) so the Invest page can show the
deposit address, amount and a QR code inline, instead of only a link to
Cryptomus's hosted page.
"""
p = "backend/api/services.py"
s = open(p).read()

old = '''    url = str(result.get("url") or "")
    if not url:
        return {"status": "failed", "address": "", "checkout_url": "",
                "message": "Cryptomus created the payment but returned no checkout url.", **common}
    return {
        "status": "pending",
        "address": str(result.get("address") or ""),
        "checkout_url": url,
        "provider_order_id": str(result.get("uuid") or order_ref),
        **common,
    }'''
new = '''    url = str(result.get("url") or "")
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
    }'''
assert s.count(old) == 1, "return block not found (already patched, or a different version)"
s = s.replace(old, new, 1)
open(p, "w").write(s)
print("services.py patched: invoice response now carries pay_amount/pay_currency for inline display")