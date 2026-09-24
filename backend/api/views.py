import json
import os
from datetime import timedelta
from decimal import Decimal

import requests
from django.core.cache import cache
from django.db import models, transaction
from django.db.models.deletion import ProtectedError
from django.http import FileResponse
from django.utils import timezone
from rest_framework import generics, permissions, response, serializers, status, views
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework_simplejwt.tokens import RefreshToken

from api.i18n import tr
from api.models import (
    Coin,
    CryptoAccount,
    Investment,
    KYCSubmission,
    Notification,
    PaymentOrder,
    Payout,
    PayoutWindow,
    PlatformSettings,
    PriceSnapshot,
    ReferralAward,
    User,
    Wallet,
    Withdrawal,
)
from api.serializers import (
    InvestmentInputSerializer,
    InvestmentSerializer,
    KYCSubmissionSerializer,
    PayoutSerializer,
    RegisterSerializer,
    ReferralAwardSerializer,
    ReferralTreeSerializer,
    UserSerializer,
    WalletSerializer,
    WithdrawalInputSerializer,
    WithdrawalSerializer,
    CryptoAccountSerializer,
    ChangePasswordSerializer,
    CoinSerializer,
    AdminCoinSerializer,
    AdminUserSerializer,
    PayoutWindowSerializer,
    UserPayoutWindowSerializer,
    AdminKycSubmissionSerializer,
)
from api.referrals import bulk_referral_counts, referral_tree_counts
from api.services import (
    confirm_payment,
    create_payment_order,
    handle_gateway_webhook,
    handle_payram_payment_webhook,
    handle_payram_payout_webhook,
    verify_btcpay_signature,
    verify_nowpayments_signature,
    verify_payram_signature,
    verify_cryptomus_signature,
    handle_cryptomus_webhook,
    verify_webhook_signature,
    send_platform_to_user,
    test_payram_connection,
    reconcile_gateway,
    payment_order_status,
)

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        data = UserSerializer(user, context={"request": request}).data
        return response.Response(
            {"user": data, "message": tr("Account created. You can now log in.", request)},
            status=status.HTTP_201_CREATED,
        )


class LoginView(views.APIView):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        identifier = (request.data.get("email") or request.data.get("identifier") or "").strip()
        password = request.data.get("password") or ""
        user = None
        if identifier:
            user = User.objects.filter(email__iexact=identifier).first()
            if user is None:
                user = User.objects.filter(phone__iexact=identifier).first()
        if user is None or not user.check_password(password) or not user.is_active:
            return response.Response(
                {"detail": tr("Invalid email/phone or password.", request)},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if user.is_frozen:
            return response.Response(
                {"detail": tr("Your account is frozen. Contact support.", request)},
                status=status.HTTP_403_FORBIDDEN,
            )
        if user.banned_until and user.banned_until > timezone.now():
            return response.Response(
                {"detail": tr("Your account is temporarily suspended. Try again later.", request)},
                status=status.HTTP_403_FORBIDDEN,
            )
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
        refresh = RefreshToken.for_user(user)
        return response.Response(
            {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "user": UserSerializer(user, context={"request": request}).data,
            }
        )


class MeView(generics.RetrieveUpdateAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_object(self):
        return self.request.user


class ChangePasswordView(views.APIView):
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        return response.Response({"message": tr("Password changed successfully.", request)})


class DeleteAccountView(views.APIView):
    def post(self, request):
        user = request.user
        # Freeze then mark inactive. Wallet/history are kept for compliance.
        user.is_active = False
        user.is_frozen = True
        user.save(update_fields=["is_active", "is_frozen"])
        return response.Response({"message": tr("Account deleted.", request)})


# ---------------------------------------------------------------------------
# Coins / Market
# ---------------------------------------------------------------------------

COINGECKO_MAP = {
    "USDT": "tether",
    "USDC": "usd-coin",
    "DAI": "dai",
    "BUSD": "binance-usd",
    "TUSD": "true-usd",
    "FDUSD": "first-digital-usd",
    "USDE": "usde",
    "PYUSD": "paypal-usd",
    "GUSD": "gemini-dollar",
    "SCUSD": "usd-coin-solan",
    "USDP": "pax-dollar",
    "TON": "the-open-network",
    "SOL": "solana",
    "BNB": "bnb",
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "TRX": "tron",
    "XRP": "ripple",
    "LTC": "litecoin",
    "DOGE": "dogecoin",
    "CRO": "crypto-com-chain",
}


def _refresh_market_prices():
    """Fetch live prices from CoinGecko and store a snapshot per active coin."""
    coins = list(Coin.objects.filter(is_active=True))
    by_symbol = {c.symbol.upper(): c for c in coins}
    ids = [COINGECKO_MAP[c.symbol.upper()] for c in coins if c.symbol.upper() in COINGECKO_MAP]
    if not ids:
        return
    try:
        resp = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids": ",".join(ids),
                "vs_currencies": "usd",
                "include_24hr_change": "true",
            },
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return
    for symbol, coin_id in COINGECKO_MAP.items():
        coin = by_symbol.get(symbol)
        if not coin or coin_id not in data:
            continue
        entry = data[coin_id]
        price = entry.get("usd")
        if price is None:
            continue
        PriceSnapshot.objects.create(
            coin=coin,
            price=Decimal(str(price)),
            change_24h=Decimal(str(entry.get("usd_24h_change") or 0)),
        )
    # keep the most recent 10 snapshots per coin
    for coin in coins:
        snapshots = PriceSnapshot.objects.filter(coin=coin).order_by("-captured_at")
        keep = [s.id for s in snapshots[:10]]
        snapshots.exclude(id__in=keep).delete()


def _maybe_refresh_market_prices():
    """Refresh CoinGecko prices at most once per interval, across all workers.

    The cache lock means only one request triggers the outbound HTTP call; every
    other request (and the cached MarketView response) is served without it.
    """
    interval = int(os.environ.get("MARKET_REFRESH_SECONDS", "60"))
    if cache.add("market:refresh_lock", 1, interval):
        _refresh_market_prices()


class MarketView(views.APIView):
    permission_classes = [permissions.AllowAny]
    throttle_classes = []  # read-only public market data

    def get(self, request):
        lang = getattr(request, "LANGUAGE_CODE", "en") or "en"
        cache_key = f"market:v1:{lang}"
        cached = cache.get(cache_key)
        if cached is not None:
            return response.Response(cached)

        _maybe_refresh_market_prices()
        coins = Coin.objects.filter(is_active=True).prefetch_related("price_snapshots")
        data = []
        for coin in coins:
            snap = coin.price_snapshots.first()
            price = snap.price if snap else coin.reference_price
            change = snap.change_24h if snap and snap.change_24h is not None else None
            data.append(
                {
                    "coin": CoinSerializer(coin, context={"request": request}).data,
                    "price": str(price),
                    "change_24h": str(change) if change is not None else "0.00",
                    "captured_at": (snap.captured_at if snap else coin.created_at).isoformat(),
                }
            )
        settings = PlatformSettings.public_map()
        payload = {"data": data, "settings": PublicSettings.serialize(settings)}
        cache.set(cache_key, payload, int(os.environ.get("MARKET_CACHE_SECONDS", "30")))
        return response.Response(payload)


class CoinListView(generics.ListAPIView):
    serializer_class = CoinSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None
    throttle_classes = []

    def get_queryset(self):
        return Coin.objects.filter(is_active=True).prefetch_related("price_snapshots")


# ---------------------------------------------------------------------------
# Wallet / balance
# ---------------------------------------------------------------------------


class DashboardView(views.APIView):
    def get(self, request):
        user = request.user
        wallets = Wallet.objects.filter(user=user).select_related("coin")
        total_invested = sum((w.invested_balance for w in wallets), Decimal("0"))
        total_withdrawable = sum((w.withdrawable_balance for w in wallets), Decimal("0"))

        activity = []
        for inv in user.investments.select_related("coin")[:10]:
            activity.append(
                {
                    "type": "invest",
                    "title": f"Invested {inv.amount} {inv.coin.symbol}",
                    "amount": str(inv.amount),
                    "symbol": inv.coin.symbol,
                    "status": inv.status,
                    "created_at": inv.created_at.isoformat(),
                    "id": inv.id,
                }
            )
        for wd in user.withdrawals.select_related("coin")[:10]:
            activity.append(
                {
                    "type": "withdraw",
                    "title": f"Withdrew {wd.amount} {wd.coin.symbol}",
                    "amount": str(wd.amount),
                    "symbol": wd.coin.symbol,
                    "status": wd.status,
                    "created_at": wd.created_at.isoformat(),
                    "id": wd.id,
                }
            )
        for po in user.payouts.select_related("coin")[:10]:
            activity.append(
                {
                    "type": "payout",
                    "title": f"Payout {po.amount} {po.coin.symbol}",
                    "amount": str(po.amount),
                    "symbol": po.coin.symbol,
                    "status": po.status,
                    "created_at": po.created_at.isoformat(),
                    "id": po.id,
                }
            )
        for aw in user.invited_users.select_related("coin")[:10]:
            activity.append(
                {
                    "type": "award",
                    "title": f"Referral L{aw.level} +{aw.amount} {aw.coin.symbol}",
                    "amount": str(aw.amount),
                    "symbol": aw.coin.symbol,
                    "status": aw.status,
                    "created_at": aw.created_at.isoformat(),
                    "id": aw.id,
                }
            )
        activity.sort(key=lambda a: a["created_at"], reverse=True)
        activity = activity[:10]

        return response.Response(
            {
                "wallets": WalletSerializer(wallets, many=True, context={"request": request}).data,
                "totals": {
                    "total_invested": str(total_invested),
                    "total_withdrawable": str(total_withdrawable),
                },
                "activity": activity,
                "user": UserSerializer(user, context={"request": request}).data,
                "settings": PublicSettings.serialize(PlatformSettings.public_map()),
            }
        )


class WalletDetailView(views.APIView):
    def get(self, request, coin_id):
        user = request.user
        try:
            coin = Coin.objects.get(pk=coin_id)
            wallet = Wallet.objects.get(user=user, coin=coin)
        except (Coin.DoesNotExist, Wallet.DoesNotExist):
            return response.Response({"detail": "Wallet not found."}, status=404)

        investments = user.investments.filter(coin=coin).order_by("-created_at")
        withdrawals = user.withdrawals.filter(coin=coin).order_by("-created_at")
        payouts = user.payouts.filter(coin=coin).order_by("-created_at")
        awards = user.referral_awards.filter(coin=coin).order_by("-created_at")

        return response.Response(
            {
                "wallet": WalletSerializer(wallet, context={"request": request}).data,
                "investments": InvestmentSerializer(investments, many=True).data,
                "withdrawals": WithdrawalSerializer(withdrawals, many=True).data,
                "payouts": PayoutSerializer(payouts, many=True).data,
                "awards": ReferralAwardSerializer(awards, many=True).data,
            }
        )


# ---------------------------------------------------------------------------
# Investing
# ---------------------------------------------------------------------------


class InvestView(views.APIView):
    def post(self, request):
        """Create a pending investment + a crypto payment order for it."""
        serializer = InvestmentInputSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        coin = serializer.validated_data["coin"]
        amount = serializer.validated_data["amount"]
        source_address = serializer.validated_data.get("source_address", "")

        if user.is_frozen:
            return response.Response(
                {"detail": tr("Your account is frozen.", request)}, status=403
            )

        with transaction.atomic():
            investment = Investment.objects.create(
                user=user,
                coin=coin,
                amount=amount,
                source_address=source_address,
            )
            order = PaymentOrder.objects.create(
                user=user,
                investment=investment,
                coin=coin,
                amount=amount,
                order_ref="",
            )
            payload = create_payment_order(investment)
            if payload.get("status") == "failed":
                raise serializers.ValidationError(
                    payload.get("message") or "Payment gateway could not create the order."
                )
            if payload.get("order_ref"):
                order.order_ref = payload["order_ref"]
                order.address = payload.get("address", "")
                order.checkout_url = payload.get("checkout_url", "")
                order.chain = payload.get("chain", coin.chain)
                order.provider_order_id = payload.get("provider_order_id", "")
                order.provider_token = payload.get("provider_token", "")
                order.save(
                    update_fields=[
                        "order_ref",
                        "address",
                        "checkout_url",
                        "chain",
                        "provider_order_id",
                        "provider_token",
                    ]
                )

        return response.Response(
            {
                "investment": InvestmentSerializer(investment).data,
                "payment": payload,
                "message": (
                    payload.get("message")
                    or tr(
                        "Investment order created. Complete the crypto payment to confirm it.",
                        request,
                    )
                    if payload.get("status") != "manual"
                    else tr(
                        "Investment submitted. Awaiting payment and admin confirmation.",
                        request,
                    )
                ),
            },
            status=status.HTTP_201_CREATED,
        )


class InvestConfirmView(views.APIView):
    def post(self, request):
        """Confirm an investment after the user reports paying (simulate) or
        the gateway reports success (provider)."""
        order_ref = (request.data.get("order_ref") or "").strip()
        if not order_ref:
            return response.Response(
                {"detail": tr("order_ref is required.", request)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order = PaymentOrder.objects.filter(order_ref=order_ref).first()
        if order is None:
            return response.Response(
                {"detail": tr("Payment order not found.", request)},
                status=status.HTTP_404_NOT_FOUND,
            )
        if order.user_id != request.user.id:
            return response.Response(
                {"detail": tr("Not found.", request)}, status=status.HTTP_404_NOT_FOUND
            )
        ok, tx, message = confirm_payment(order_ref)
        if ok:
            order.investment.confirm()
            return response.Response(
                {
                    "investment": InvestmentSerializer(order.investment).data,
                    "tx_hash": tx,
                    "message": (
                        tr(
                            "Payment received. Your investment is confirmed and your balance is updated.",
                            request,
                        )
                        if message != "already_paid"
                        else tr("This payment was already confirmed.", request)
                    ),
                }
            )
        return response.Response(
            {"detail": tr(message, request)},
            status=status.HTTP_400_BAD_REQUEST,
        )


class InvestStatusView(views.APIView):
    def get(self, request):
        """Poll the gateway for the current state of the user's payment order.

        The checkout page polls this while the user pays so a payment PayRam
        already filled is confirmed without the user ever leaving the site.
        """
        order_ref = (request.query_params.get("order_ref") or "").strip()
        if not order_ref:
            return response.Response(
                {"detail": tr("order_ref is required.", request)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        order = PaymentOrder.objects.filter(order_ref=order_ref).first()
        if order is None or order.user_id != request.user.id:
            return response.Response(
                {"detail": tr("Payment order not found.", request)},
                status=status.HTTP_404_NOT_FOUND,
            )
        data = payment_order_status(order_ref)
        data["message"] = tr(data.get("message", ""), request)
        return response.Response(data)


class GatewayWebhookView(views.APIView):
    permission_classes = [permissions.AllowAny]
    # Provider callbacks arrive from a small set of IPs; never rate-limit them.
    throttle_classes = []

    def post(self, request):
        """Signed callback from the crypto payment/payout gateway.

        Signature schemes accepted (verified over the raw request body):
          * ``X-Payram-Signature`` – HMAC-SHA256 keyed by the PayRam project
            API key (payment + payout webhooks shared on this endpoint).
          * ``X-Gateway-Signature`` – HMAC-SHA256 over the raw body
            (PAYMENT_WEBHOOK_TOKEN) (legacy).
          * ``BTCPay-Sig``          – BTCPay Server webhook: ``sha256=<hex>``
            HMAC-SHA256 over the raw body with the webhook secret (legacy).
          * ``X-NowPayments-Sig``   – NOWPayments IPN: HMAC-SHA512 over the raw
            body (signed JSON string with keys sorted) using the IPN secret key.
        """
        raw = request.body
        sig_payram = request.META.get("HTTP_X_PAYRAM_SIGNATURE", "")
        sig_gateway = request.META.get("HTTP_X_GATEWAY_SIGNATURE", "")
        sig_btcpay = request.META.get("HTTP_BTCPAY_SIG", "")
        sig_nowpayments = request.META.get("HTTP_X_NOWPAYMENTS_SIG", "")
        data = _parse_webhook_body(raw)
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
                handled = handle_gateway_webhook(data)
        if handled:
            return response.Response({"status": "ok"})
        return response.Response({"status": "ignored"}, status=status.HTTP_200_OK)


def _parse_webhook_body(raw):
    """Parse the webhook body as JSON, falling back to form-encoded params."""
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8") or "{}")
    except ValueError:
        pass
    from urllib.parse import parse_qs

    params = parse_qs(raw.decode("utf-8"))
    return {k: v[0] for k, v in params.items()}


# ---------------------------------------------------------------------------
# Admin panel (staff only)
# ---------------------------------------------------------------------------


class IsStaffPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
            and request.user.is_active
        )


class AdminUsersListView(generics.ListAPIView):
    permission_classes = [IsStaffPermission]
    serializer_class = AdminUserSerializer
    pagination_class = None

    def get_queryset(self):
        qs = User.objects.all().order_by("-created_at")
        q = (self.request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(
                models.Q(email__icontains=q)
                | models.Q(first_name__icontains=q)
                | models.Q(last_name__icontains=q)
                | models.Q(phone__icontains=q)
            )
        return qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        user_ids = self.filter_queryset(self.get_queryset()).values_list("id", flat=True)
        ctx["referral_counts"] = bulk_referral_counts(user_ids)
        return ctx


class AdminUserActionView(views.APIView):
    permission_classes = [IsStaffPermission]

    def post(self, request, pk):
        user = User.objects.filter(pk=pk).first()
        if user is None:
            return response.Response({"detail": "User not found."}, 404)
        action = (request.data.get("action") or "").strip()
        if action == "freeze":
            user.is_frozen = True
            user.save(update_fields=["is_frozen"])
            return response.Response({"message": f"{user.email} frozen."})
        if action == "unfreeze":
            user.is_frozen = False
            user.save(update_fields=["is_frozen"])
            return response.Response({"message": f"{user.email} unfrozen."})
        if action == "kyc_approve":
            user.kyc_verified = True
            user.kyc_rejected = False
            user.save(update_fields=["kyc_verified", "kyc_rejected"])
            user.kyc_submissions.filter(status=KYCSubmission.STATUS_PENDING).update(
                status=KYCSubmission.STATUS_APPROVED, reviewed_at=timezone.now()
            )
            return response.Response({"message": f"{user.email} KYC approved."})
        if action == "kyc_reject":
            user.kyc_verified = False
            user.kyc_rejected = True
            user.save(update_fields=["kyc_verified", "kyc_rejected"])
            user.kyc_submissions.filter(status=KYCSubmission.STATUS_PENDING).update(
                status=KYCSubmission.STATUS_REJECTED, reviewed_at=timezone.now()
            )
            return response.Response({"message": f"{user.email} KYC rejected."})
        if action == "ban":
            try:
                hours = int(request.data.get("hours") or 0)
            except (TypeError, ValueError):
                hours = 0
            if hours <= 0:
                return response.Response({"detail": "Provide a positive number of hours."}, 400)
            user.banned_until = timezone.now() + timedelta(hours=hours)
            user.save(update_fields=["banned_until"])
            until = timezone.localtime(user.banned_until)
            return response.Response(
                {"message": f"{user.email} banned until {until:%d %b %Y %H:%M}."}
            )
        if action == "unban":
            user.banned_until = None
            user.save(update_fields=["banned_until"])
            return response.Response({"message": f"{user.email} unbanned."})
        if action == "delete":
            confirm = (request.data.get("confirm") or "").strip().lower()
            if confirm != user.email.lower():
                return response.Response(
                    {"detail": f"Type the user's email ({user.email}) to confirm deletion."}, 400
                )
            if user == request.user:
                return response.Response({"detail": "You cannot delete your own account."}, 400)
            email = user.email
            user.delete()
            return response.Response({"message": f"Account {email} permanently deleted."})
        return response.Response({"detail": f"Unknown action '{action}'."}, 400)


class AdminBalanceAdjustView(views.APIView):
    """Admin adjusts a user's invested / withdrawable balance in one coin."""

    permission_classes = [IsStaffPermission]

    def post(self, request, pk):
        user = User.objects.filter(pk=pk).first()
        if user is None:
            return response.Response({"detail": "User not found."}, 404)
        try:
            coin_id = int(request.data.get("coin_id") or 0)
            coin = Coin.objects.filter(pk=coin_id).first()
            if coin is None:
                return response.Response({"detail": "Choose a valid coin."}, 400)
            invested_delta = Decimal(str(request.data.get("invested_delta") or "0"))
            withdrawable_delta = Decimal(str(request.data.get("withdrawable_delta") or "0"))
        except (TypeError, ValueError):
            return response.Response({"detail": "Invalid balance delta."}, 400)
        if invested_delta == 0 and withdrawable_delta == 0:
            return response.Response({"detail": "No change requested."}, 400)

        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get_or_create(
                user=user, coin=coin
            )[0]
            new_invested = wallet.invested_balance + invested_delta
            new_withdrawable = wallet.withdrawable_balance + withdrawable_delta
            if new_invested < 0 or new_withdrawable < 0:
                return response.Response(
                    {"detail": "Resulting balance cannot be negative."}, 400
                )
            wallet.invested_balance = new_invested
            wallet.withdrawable_balance = new_withdrawable
            wallet.save(update_fields=["invested_balance", "withdrawable_balance", "updated_at"])
            note = (request.data.get("note") or "").strip()
            if withdrawable_delta != 0:
                Payout.objects.create(
                    user=user,
                    coin=coin,
                    amount=abs(withdrawable_delta),
                    status=Payout.STATUS_COMPLETED,
                    destination_address="",
                    is_bonus=True,
                    note=(
                        f"Admin balance adjustment ({withdrawable_delta:+} withdrawable)"
                        + (f": {note}" if note else "")
                    ),
                    created_by=request.user,
                )
        return response.Response({
            "message": f"{user.email} {coin.symbol} balance adjusted.",
            "wallet": {
                "coin_id": coin.id,
                "coin_symbol": coin.symbol,
                "invested_balance": str(wallet.invested_balance),
                "withdrawable_balance": str(wallet.withdrawable_balance),
            },
            "totals": {
                "total_invested": str(user.wallets.aggregate(t=models.Sum("invested_balance"))["t"] or 0),
                "total_withdrawable": str(user.wallets.aggregate(t=models.Sum("withdrawable_balance"))["t"] or 0),
            },
        })


class AdminKycReviewListView(generics.ListAPIView):
    permission_classes = [IsStaffPermission]
    serializer_class = AdminKycSubmissionSerializer
    pagination_class = None

    def get_queryset(self):
        qs = (
            KYCSubmission.objects.select_related("user").prefetch_related("user__wallets")
            .annotate(
                is_pending=models.Case(
                    models.When(status=KYCSubmission.STATUS_PENDING, then=0),
                    default=1,
                    output_field=models.IntegerField(),
                )
            )
            .order_by("is_pending", "-submitted_at")
        )
        status_filter = (self.request.query_params.get("status") or "").strip()
        if status_filter == "approved":
            qs = qs.filter(status=KYCSubmission.STATUS_APPROVED)
        elif status_filter == "rejected":
            qs = qs.filter(status=KYCSubmission.STATUS_REJECTED)
        elif status_filter != "all":
            qs = qs.filter(status=KYCSubmission.STATUS_PENDING)
        return qs


class AdminKycReviewActionView(views.APIView):
    permission_classes = [IsStaffPermission]

    def post(self, request, pk):
        sub = KYCSubmission.objects.filter(pk=pk).select_related("user").first()
        if sub is None:
            return response.Response({"detail": "Submission not found."}, 404)
        action = (request.data.get("action") or "").strip()
        reason = (request.data.get("reason") or "").strip()
        user = sub.user
        if action == "approve":
            if sub.status == KYCSubmission.STATUS_PENDING:
                sub.status = KYCSubmission.STATUS_APPROVED
                sub.reviewed_at = timezone.now()
                sub.save(update_fields=["status", "reason", "reviewed_at"])
            user.kyc_verified = True
            user.kyc_rejected = False
            user.save(update_fields=["kyc_verified", "kyc_rejected"])
            user.kyc_submissions.filter(status=KYCSubmission.STATUS_PENDING).update(
                status=KYCSubmission.STATUS_APPROVED, reviewed_at=timezone.now()
            )
            return response.Response({"message": f"KYC approved for {user.email}."})
        if action == "reject":
            sub.status = KYCSubmission.STATUS_REJECTED
            sub.reason = reason or "Documents could not be verified."
            sub.reviewed_at = timezone.now()
            sub.save(update_fields=["status", "reason", "reviewed_at"])
            user.kyc_verified = False
            user.kyc_rejected = True
            user.save(update_fields=["kyc_verified", "kyc_rejected"])
            return response.Response({"message": f"KYC rejected for {user.email}."})
        return response.Response({"detail": f"Unknown action '{action}'."}, 400)


class AdminKycFileView(views.APIView):
    permission_classes = [IsStaffPermission]
    FIELD_MAP = {
        "front": "document_front",
        "back": "document_back",
        "selfie": "selfie",
    }

    def get(self, request, pk, field):
        """Return one KYC document image through the authed admin API."""
        sub = KYCSubmission.objects.filter(pk=pk).first()
        if sub is None:
            return response.Response({"detail": "Submission not found."}, 404)
        attr = self.FIELD_MAP.get((field or "").lower())
        if attr is None:
            return response.Response({"detail": "Invalid file field."}, 400)
        img = getattr(sub, attr, None)
        if not img:
            return response.Response({"detail": "No file for this field."}, 404)
        try:
            return FileResponse(img.open("rb"))
        except Exception:
            return response.Response({"detail": "Could not open file."}, 500)


class AdminPaymentSettingsView(views.APIView):
    permission_classes = [IsStaffPermission]

    def get(self, request):
        mode = PlatformSettings.get(PlatformSettings.S_PAYMENT_MODE, "simulate")
        url = PlatformSettings.get(PlatformSettings.S_PAYMENT_PROVIDER_URL, "")
        key = PlatformSettings.get(PlatformSettings.S_PAYMENT_PROVIDER_KEY, "")
        secret = PlatformSettings.get(PlatformSettings.S_PAYMENT_PROVIDER_SECRET, "")
        token = PlatformSettings.get(
            PlatformSettings.S_PAYMENT_WEBHOOK_TOKEN, "dev-gateway-secret"
        )

        def mask(v):
            v = str(v).strip()
            if len(v) <= 4:
                return "****"
            return f"{v[-4:]}".rjust(len(v), "*")

        wallets = CryptoAccount.objects.filter(is_platform=True).select_related("coin", "user")

        def env_state(env):
            base_key = (
                PlatformSettings.S_PAYRAM_BASE_URL_PROD
                if env == "production"
                else PlatformSettings.S_PAYRAM_BASE_URL_TEST
            )
            api_key_setting = (
                PlatformSettings.S_PAYRAM_API_KEY_PROD
                if env == "production"
                else PlatformSettings.S_PAYRAM_API_KEY_TEST
            )
            api_key = PlatformSettings.get(api_key_setting, "")
            return {
                "base_url": PlatformSettings.get(base_key, ""),
                "api_key_masked": mask(api_key) if api_key else "",
                "api_key_set": bool(api_key),
            }

        return response.Response({
            "payment_mode": mode,
            "provider": {
                "url": url,
                "key_masked": mask(key) if key else "",
                "key_set": bool(key),
                "secret_masked": mask(secret) if secret else "",
                "secret_set": bool(secret),
                "webhook_token_masked": mask(token) if token else "",
                "webhook_token_set": bool(token),
                "callback_url": PlatformSettings.get(
                    PlatformSettings.S_PAYMENT_CALLBACK_URL, ""
                ),
                "store_id": PlatformSettings.get(
                    PlatformSettings.S_PAYMENT_STORE_ID, ""
                ),
                "success_url": PlatformSettings.get(
                    PlatformSettings.S_PAYMENT_SUCCESS_URL, ""
                ),
            },
            "payram": {
                "mode": PlatformSettings.get(PlatformSettings.S_PAYRAM_MODE, "test")
                or "test",
                "test": env_state("test"),
                "production": env_state("production"),
            },
            "platform_wallets": [
                {
                    "id": w.id,
                    "coin_id": w.coin_id,
                    "coin_symbol": w.coin.symbol,
                    "address": w.address,
                    "label": w.label,
                    "owner": w.user.email,
                }
                for w in wallets
            ],
        })

    def post(self, request):
        mode = (request.data.get("payment_mode") or "").strip().lower()
        if mode in {"simulate", "provider", "manual"}:
            PlatformSettings.objects.update_or_create(
                key=PlatformSettings.S_PAYMENT_MODE,
                defaults={"value": mode, "label": "simulate | provider | manual"},
            )
        elif mode:
            return response.Response({"detail": "Invalid payment mode."}, 400)
        payram_mode = (request.data.get("payram_mode") or "").strip().lower()
        if payram_mode in {"test", "production"}:
            PlatformSettings.objects.update_or_create(
                key=PlatformSettings.S_PAYRAM_MODE,
                defaults={"value": payram_mode, "label": "PayRam environment: test | production"},
            )
        elif payram_mode:
            return response.Response({"detail": "Invalid PayRam mode."}, 400)
        for field_name, key, label in (
            ("provider_url", PlatformSettings.S_PAYMENT_PROVIDER_URL, "(legacy) provider API base URL"),
            ("provider_key", PlatformSettings.S_PAYMENT_PROVIDER_KEY, "(legacy) provider API key"),
            ("provider_secret", PlatformSettings.S_PAYMENT_PROVIDER_SECRET, "(legacy) provider API secret"),
            ("store_id", PlatformSettings.S_PAYMENT_STORE_ID, "(legacy) merchant store ID"),
            ("webhook_token", PlatformSettings.S_PAYMENT_WEBHOOK_TOKEN, "Webhook HMAC/secret"),
            ("callback_url", PlatformSettings.S_PAYMENT_CALLBACK_URL, "(legacy) Webhook callback URL"),
            ("success_url", PlatformSettings.S_PAYMENT_SUCCESS_URL, "Success redirect URL"),
            ("payram_base_url_test", PlatformSettings.S_PAYRAM_BASE_URL_TEST, "PayRam test BASE_URL (Site URL)"),
            ("payram_api_key_test", PlatformSettings.S_PAYRAM_API_KEY_TEST, "PayRam test project API key"),
            ("payram_base_url_production", PlatformSettings.S_PAYRAM_BASE_URL_PROD, "PayRam production BASE_URL (Site URL)"),
            ("payram_api_key_production", PlatformSettings.S_PAYRAM_API_KEY_PROD, "PayRam production project API key"),
        ):
            val = (request.data.get(field_name) or "").strip()
            if field_name in request.data and val:
                PlatformSettings.objects.update_or_create(
                    key=key, defaults={"value": val, "label": label}
                )
            val = (request.data.get(field_name) or "").strip()
            if val:
                PlatformSettings.objects.update_or_create(
                    key=key, defaults={"value": val, "label": label}
                )
        coin_id = request.data.get("wallet_coin_id")
        address = (request.data.get("wallet_address") or "").strip()
        if coin_id and address:
            coin = Coin.objects.filter(pk=coin_id).first()
            if coin is None:
                return response.Response({"detail": "Invalid wallet coin."}, 400)
            CryptoAccount.objects.create(
                user=request.user,
                coin=coin,
                address=address,
                label=(request.data.get("wallet_label") or "Platform wallet"),
                is_platform=True,
            )
            return response.Response({"message": "Platform wallet saved."}, status=status.HTTP_201_CREATED)
        return response.Response({"message": "Payment settings saved."})


class AdminPaymentWalletDeleteView(views.APIView):
    permission_classes = [IsStaffPermission]

    def delete(self, request, pk):
        wallets = CryptoAccount.objects.filter(pk=pk, is_platform=True)
        if not wallets.exists():
            return response.Response({"detail": "Platform wallet not found."}, 404)
        wallets.delete()
        return response.Response({"message": "Platform wallet removed."})


class AdminProviderTestView(views.APIView):
    permission_classes = [IsStaffPermission]

    def post(self, request):
        ok, message = test_payram_connection()
        return response.Response({"ok": ok, "message": message})


class AdminOrdersView(generics.ListAPIView):
    permission_classes = [IsStaffPermission]
    pagination_class = None

    def get_queryset(self):
        qs = PaymentOrder.objects.select_related("user", "coin", "investment")
        status_filter = (self.request.query_params.get("status") or "").strip()
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def serialize(self, obj):
        return {
            "id": obj.id,
            "order_ref": obj.order_ref,
            "user_id": obj.user_id,
            "user_email": obj.user.email,
            "coin_id": obj.coin_id,
            "coin_symbol": obj.coin.symbol,
            "amount": str(obj.amount),
            "chain": obj.chain,
            "status": obj.status,
            "address": obj.address,
            "checkout_url": obj.checkout_url,
            "tx_hash": obj.tx_hash,
            "investment_status": obj.investment.status,
            "created_at": obj.created_at,
        }

    def list(self, request, *args, **kwargs):
        try:
            reconcile_gateway()
        except Exception:  # noqa: BLE001
            pass
        rows = [self.serialize(o) for o in self.get_queryset()]
        return response.Response(rows)


class AdminOrderConfirmView(views.APIView):
    permission_classes = [IsStaffPermission]

    def post(self, request, pk):
        order = PaymentOrder.objects.select_related("investment").filter(pk=pk).first()
        if order is None:
            return response.Response({"detail": "Payment order not found."}, 404)
        if order.status != PaymentOrder.STATUS_PENDING:
            return response.Response({"message": "This order is already processed."})
        order.mark_paid("admin")
        order.investment.confirm()
        return response.Response(
            {"message": f"Order {order.order_ref} marked paid and investment confirmed."}
        )


class AdminCoinListView(generics.ListCreateAPIView):
    permission_classes = [IsStaffPermission]
    pagination_class = None
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    serializer_class = AdminCoinSerializer
    queryset = Coin.objects.all()

    def perform_create(self, serializer):
        serializer.save()


class AdminCoinDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsStaffPermission]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    serializer_class = AdminCoinSerializer
    queryset = Coin.objects.all()

    def destroy(self, request, *args, **kwargs):
        coin = self.get_object()
        try:
            with transaction.atomic():
                coin.delete()
        except ProtectedError:
            return response.Response(
                {"detail": tr("Cannot delete this coin because it has investments.", request)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return response.Response(status=status.HTTP_204_NO_CONTENT)


def _windows_config_for(request):
    """Payout percent/duration the window opens with (admin overrides or platform settings)."""
    data = request.data
    percent = PlatformSettings.get_decimal(PlatformSettings.S_PAYOUT_PERCENT, 10)
    if data.get("percent") not in (None, ""):
        try:
            percent = float(str(data.get("percent")))
        except (TypeError, ValueError):
            return None, None, "Invalid percent."
    duration = max(
        1, int(PlatformSettings.get_decimal(PlatformSettings.S_PAYOUT_DURATION_HOURS, 48))
    )
    if data.get("duration_hours") not in (None, ""):
        try:
            duration = max(1, int(data.get("duration_hours")))
        except (TypeError, ValueError):
            return None, None, "Invalid duration."
    return percent, duration, None


def _activate_window(window, request):
    """Close any other open payout window and open this one, notifying users."""
    PayoutWindow.objects.filter(is_active=True).exclude(pk=window.pk).update(
        is_active=False
    )
    ends_at = window.activate()
    scope = (
        "all users"
        if window.target_mode == PayoutWindow.TARGET_ALL
        else f"{window.target_users.count()} selected users"
    )
    user_ids = None
    if window.target_mode == PayoutWindow.TARGET_SPECIFIC:
        user_ids = list(window.target_users.values_list("pk", flat=True))
    Notification.broadcast(
        Notification.TYPE_PAYOUT,
        title=f"New daily payout window: {window.title}",
        title_ar=f"نافذة دفعات يومية جديدة: {window.title}",
        body=f"A {window.percent}% payout is now available for you to claim.",
        body_ar=f"دفعة بنسبة {window.percent}% متاحة الآن لك للمطالبة بها.",
        link="/payouts",
        user_ids=user_ids,
        created_by=request.user,
    )
    return response.Response(
        {
            "message": f"'{window.title}' opened ({scope}) until {ends_at:%d %b %Y %H:%M}.",
            "ends_at": ends_at,
        }
    )


class AdminWindowsView(generics.ListAPIView):
    permission_classes = [IsStaffPermission]
    serializer_class = PayoutWindowSerializer
    pagination_class = None

    def get_queryset(self):
        qs = PayoutWindow.objects.select_related("coin").prefetch_related("claimed_by")
        status_filter = (self.request.query_params.get("status") or "").strip()
        if status_filter == "active":
            qs = qs.filter(is_active=True)
        elif status_filter == "closed":
            qs = qs.filter(is_active=False)
        return qs

    def post(self, request):
        """Create the payout window and (usually) open it right away.

        Percent and duration default to the platform settings when not provided,
        so opening a window is a single action (no separate "create" step).
        """
        data = request.data
        percent, duration, err = _windows_config_for(request)
        if err:
            return response.Response({"detail": err}, 400)
        title = str(data.get("title") or "Payout window").strip() or "Payout window"
        window = PayoutWindow.objects.create(
            title=title[:120],
            percent=Decimal(str(percent)),
            duration_hours=duration,
            created_by=request.user,
        )
        if data.get("target_user_ids") is not None:
            ids = data.get("target_user_ids")
            if not isinstance(ids, list):
                return response.Response(
                    {"detail": "target_user_ids must be a list of user ids."}, 400
                )
            user_ids = []
            for i in ids:
                try:
                    user_ids.append(int(i))
                except (TypeError, ValueError):
                    return response.Response(
                        {"detail": "target_user_ids must be a list of user ids."}, 400
                    )
            valid = set(User.objects.filter(pk__in=user_ids).values_list("pk", flat=True))
            window.target_users.set(valid)
            window.target_mode = (
                PayoutWindow.TARGET_SPECIFIC if valid else PayoutWindow.TARGET_ALL
            )
            window.save(update_fields=["target_mode"])
        if bool(data.get("active")):
            return _activate_window(window, request)
        return response.Response(
            {
                "message": f"'{window.title}' created.",
                "id": window.pk,
                "window": PayoutWindowSerializer(
                    window, context={"request": request}
                ).data,
            }
        )


class AdminWindowToggleView(views.APIView):
    permission_classes = [IsStaffPermission]

    def _apply_target(self, window, ids):
        user_ids = []
        for i in ids:
            try:
                user_ids.append(int(i))
            except (TypeError, ValueError):
                return None
        valid = set(User.objects.filter(pk__in=user_ids).values_list("pk", flat=True))
        window.target_users.set(valid)
        window.target_mode = (
            PayoutWindow.TARGET_SPECIFIC if valid else PayoutWindow.TARGET_ALL
        )
        return valid

    def post(self, request, pk):
        window = PayoutWindow.objects.filter(pk=pk).first()
        if window is None:
            return response.Response({"detail": "Window not found."}, 404)
        data = request.data

        if "active" not in data:
            # Config-only update: percent and/or target users.
            updated = []
            if "percent" in data:
                try:
                    window.percent = Decimal(str(data.get("percent")))
                except Exception:
                    return response.Response({"detail": "Invalid percent."}, 400)
                window.save(update_fields=["percent"])
                updated.append("percent")
            if "target_user_ids" in data:
                ids = data.get("target_user_ids")
                if not isinstance(ids, list):
                    return response.Response({"detail": "target_user_ids must be a list of user ids."}, 400)
                if self._apply_target(window, ids) is None:
                    return response.Response({"detail": "target_user_ids must be a list of user ids."}, 400)
                window.save(update_fields=["target_mode"])
                updated.append("target")
            if not updated:
                return response.Response({"detail": "Nothing to update."}, 400)
            return response.Response({"message": f"'{window.title}' updated."})

        activate = bool(data.get("active"))
        if activate:
            # On open the percent and duration are (re)applied from the platform
            # settings unless explicitly overridden, so the admin can change the
            # window percentage/time purely via the Settings tab.
            percent, duration, err = _windows_config_for(request)
            if err:
                return response.Response({"detail": err}, 400)
            window.percent = Decimal(str(percent))
            window.duration_hours = duration
            target_changed = False
            if "target_user_ids" in data:
                ids = data.get("target_user_ids")
                if not isinstance(ids, list):
                    return response.Response({"detail": "target_user_ids must be a list of user ids."}, 400)
                if self._apply_target(window, ids) is None:
                    return response.Response({"detail": "target_user_ids must be a list of user ids."}, 400)
                target_changed = True
            window.save(update_fields=["percent", "duration_hours", "target_mode"])
            return _activate_window(window, request)
        window.close()
        return response.Response({"message": f"'{window.title}' closed."})


# ---------------------------------------------------------------------------
# Payout windows (users)
# ---------------------------------------------------------------------------


class PayoutWindowStatusView(views.APIView):
    def get(self, request):
        """Open payout windows the user can claim, with per-coin previews."""
        windows = []
        for w in PayoutWindow.objects.select_related("coin").filter(is_active=True):
            if w.is_open and w.is_eligible_for(request.user):
                windows.append(UserPayoutWindowSerializer(w, context={"request": request}).data)
        return response.Response(windows)


class PayoutWindowClaimView(views.APIView):
    def post(self, request):
        window_id = request.data.get("window_id")
        window = PayoutWindow.objects.filter(pk=window_id).first()
        if window is None:
            return response.Response({"detail": tr("Payout not found.", request)}, 404)
        with transaction.atomic():
            ok, message, grants = window.grant_to(request.user)
        if not ok:
            return response.Response({"detail": tr(message, request)}, 400)
        return response.Response(
            {"message": tr(message, request), "grants": grants, "window": window.title}
        )


# ---------------------------------------------------------------------------
# Withdrawals
# ---------------------------------------------------------------------------


class WithdrawalCreateView(views.APIView):
    def post(self, request):
        serializer = WithdrawalInputSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        coin = serializer.validated_data["coin"]
        amount = serializer.validated_data["amount"]
        fee = serializer.validated_data["fee"]
        address = serializer.validated_data["address"]
        network = serializer.validated_data.get("network", coin.chain)

        with transaction.atomic():
            wallet = Wallet.objects.select_for_update().get(user=user, coin=coin)
            if wallet.withdrawable_balance < amount:
                return response.Response(
                    {"amount": "Insufficient withdrawable balance."}, status=400
                )
            wallet.withdrawable_balance -= amount
            wallet.save(update_fields=["withdrawable_balance", "updated_at"])
            withdrawal = Withdrawal.objects.create(
                user=user, coin=coin, address=address,
                network=network, amount=amount, fee=fee,
            )

        mode = PlatformSettings.get(PlatformSettings.S_PAYOUT_MODE, "manual")
        if mode == "automatic":
            ok, message = send_platform_to_user(withdrawal)  # → PayRam payout API
            if not ok:
                # roll back balance or mark withdrawal failed — needs a decision
                withdrawal.mark_failed(message)
            else:
                withdrawal.mark_sent()
        return response.Response(
            {
                "withdrawal": WithdrawalSerializer(withdrawal).data,
                "message": tr(
                    "Withdrawal request created and is pending approval. "
                    "Funds are reserved and will be sent to your address once approved.",
                    request,
                ),
            },
            status=status.HTTP_201_CREATED,
        )


class WithdrawalListView(generics.ListAPIView):
    serializer_class = WithdrawalSerializer
    pagination_class = None

    def get_queryset(self):
        return self.request.user.withdrawals.select_related("coin")


# ---------------------------------------------------------------------------
# Payouts (read-only for users; created/approved by admins)
# ---------------------------------------------------------------------------


class PayoutListView(generics.ListAPIView):
    serializer_class = PayoutSerializer
    pagination_class = None

    def get_queryset(self):
        return self.request.user.payouts.select_related("coin")


# ---------------------------------------------------------------------------
# Crypto accounts (user receiving addresses)
# ---------------------------------------------------------------------------


class CryptoAccountListCreateView(generics.ListCreateAPIView):
    serializer_class = CryptoAccountSerializer
    pagination_class = None

    def get_queryset(self):
        return self.request.user.crypto_accounts.select_related("coin")


class CryptoAccountDeleteView(generics.DestroyAPIView):
    serializer_class = CryptoAccountSerializer

    def get_queryset(self):
        return self.request.user.crypto_accounts


# ---------------------------------------------------------------------------
# KYC
# ---------------------------------------------------------------------------


class KYCSubmitView(views.APIView):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def post(self, request):
        serializer = KYCSubmissionSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        submission = serializer.save(user=request.user)
        return response.Response(
            {
                "submission": KYCSubmissionSerializer(submission).data,
                "message": tr("KYC documents submitted for review.", request),
            },
            status=status.HTTP_201_CREATED,
        )


class KYCStatusView(views.APIView):
    def get(self, request):
        user = request.user
        submissions = user.kyc_submissions.order_by("-submitted_at")
        latest = submissions.first()
        return response.Response(
            {
                "kyc_verified": user.kyc_verified,
                "kyc_rejected": user.kyc_rejected,
                "status": (
                    latest.status if latest
                    else ("verified" if user.kyc_verified else "not_submitted")
                ),
                "reason": latest.reason if latest else "",
                "required_to_invest": PlatformSettings.get_bool(
                    PlatformSettings.S_KYC_REQUIRED_TO_INVEST, False
                ),
                "required_to_withdraw": PlatformSettings.get_bool(
                    PlatformSettings.S_KYC_REQUIRED_TO_WITHDRAW, False
                ),
                "submissions": KYCSubmissionSerializer(submissions, many=True).data,
            }
        )


# ---------------------------------------------------------------------------
# Referrals
# ---------------------------------------------------------------------------


class ReferralView(views.APIView):
    def get(self, request):
        user = request.user
        levels = {}
        for level in (1, 2, 3):
            levels[level] = sum(
                (a.amount for a in user.invited_users.filter(level=level)), Decimal("0")
            )
        # Count referrals per level down the invite tree (awards only exist once
        # an invitee invests, so count the users themselves to reflect signups).
        counts = referral_tree_counts(user)
        awards = user.invited_users.select_related("coin", "user").order_by("-created_at")
        data = {
            "invite_code": user.invite_code,
            "referral_link": user.invite_code,
            "direct_invites": counts[1],
            "level1_count": counts[1],
            "level2_count": counts[2],
            "level3_count": counts[3],
            "total_referrals": counts[1] + counts[2] + counts[3],
            "level1_earned": str(levels[1]),
            "level2_earned": str(levels[2]),
            "level3_earned": str(levels[3]),
            "total_earned": str(levels[1] + levels[2] + levels[3]),
            "awards": ReferralAwardSerializer(awards, many=True).data,
        }
        serializer = ReferralTreeSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        return response.Response(serializer.data)


# ---------------------------------------------------------------------------
# Public settings
# ---------------------------------------------------------------------------


class PublicSettings:
    @staticmethod
    def serialize(settings_map):
        return {
            "referral_levels": [
                {"level": 1, "percent": settings_map["l1_percent"]},
                {"level": 2, "percent": settings_map["l2_percent"]},
                {"level": 3, "percent": settings_map["l3_percent"]},
            ],
            "withdraw_cooldown_hours": settings_map["withdraw_cooldown_hours"],
            "payout_cooldown_hours": settings_map["payout_cooldown_hours"],
            "kyc_required_to_invest": settings_map["kyc_required_to_invest"],
            "kyc_required_to_withdraw": settings_map["kyc_required_to_withdraw"],
            "min_withdrawal": settings_map["min_withdrawal"],
            "withdraw_fee_percent": settings_map["withdraw_fee_percent"],
            "default_lang": settings_map.get("default_lang", "en"),
        }


class PublicSettingsView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        settings = PlatformSettings.public_map()
        return response.Response(PublicSettings.serialize(settings))


# ---------------------------------------------------------------------------
# Referral invite resolver (used on registration & invest)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


def _notification_data(request, msg):
    """Serialize a notification for the requesting user, localizing text."""
    lang = (request.META.get("HTTP_X_LANG") or "en").lower()
    ar = lang.startswith("ar")
    is_admin_view = msg.user_id is None
    return {
        "id": msg.id,
        "type": msg.type,
        "title": (msg.title_ar or msg.title) if ar else msg.title,
        "body": (msg.body_ar or msg.body) if ar else msg.body,
        "link": msg.link,
        "is_read": msg.is_read if msg.user_id else msg.read_by.filter(pk=request.user.pk).exists(),
        "created_at": msg.created_at,
        "global": is_admin_view,
    }


def _global_notification_cutoff(user):
    """Earliest global broadcast a user should see.

    Global announcements live as a single row (``user`` is null) that everyone
    shares. Without a lower bound, an account created today would receive every
    payout-window/announcement ever sent. Cap it at the user's join time (and a
    90-day window for older accounts).
    """
    ninety_days = timezone.now() - timedelta(days=90)
    joined = getattr(user, "date_joined", None)
    return max(ninety_days, joined) if joined else ninety_days


class NotificationListView(views.APIView):
    def get(self, request):
        limit = int(request.query_params.get("limit") or 20)
        mine = request.user.notifications.select_related("created_by")[:limit]
        globs = Notification.objects.filter(
            user__isnull=True, created_at__gte=_global_notification_cutoff(request.user)
        )
        items = list(mine)
        items.extend(globs)
        items.sort(key=lambda n: n.created_at, reverse=True)
        items = items[:limit]
        return response.Response([_notification_data(request, m) for m in items])


class NotificationUnreadCountView(views.APIView):
    def get(self, request):
        mine = request.user.notifications.filter(is_read=False).count()
        globs = (
            Notification.objects.filter(
                user__isnull=True,
                created_at__gte=_global_notification_cutoff(request.user),
            )
            .exclude(read_by=request.user)
            .count()
        )
        return response.Response({"count": mine + globs})


class NotificationMarkReadView(views.APIView):
    def post(self, request):
        ids = request.data.get("ids") or []
        user = request.user
        if isinstance(ids, list) and ids:
            user.notifications.filter(id__in=ids).update(is_read=True)
            for n in Notification.objects.filter(user__isnull=True, id__in=ids):
                n.read_by.add(user)
        else:
            user.notifications.filter(is_read=False).update(is_read=True)
            globals_qs = Notification.objects.filter(
                user__isnull=True,
                created_at__gte=_global_notification_cutoff(user),
            ).exclude(read_by=user)
            for n in globals_qs:
                n.read_by.add(user)
        return response.Response({"message": tr("Marked as read.", request)})


# ---------------------------------------------------------------------------
# Admin: notifications / announcements
# ---------------------------------------------------------------------------


class AdminNotificationView(views.APIView):
    permission_classes = [IsStaffPermission]

    def get(self, request):
        items = Notification.objects.select_related("created_by").order_by("-created_at")[:50]
        data = []
        for n in items:
            row = _notification_data(request, n)
            row["recipient"] = n.user.email if n.user_id else "all users"
            data.append(row)
        return response.Response(data)

    def post(self, request):
        title = (request.data.get("title") or "").strip()
        if not title:
            return response.Response({"detail": "title is required."}, 400)
        target = (request.data.get("target") or "all").strip()
        user_ids = None
        if target == "invested":
            user_ids = list(
                Wallet.objects.filter(invested_balance__gt=0)
                .values_list("user_id", flat=True)
                .distinct()
            )
        Notification.broadcast(
            Notification.TYPE_ANNOUNCEMENT,
            title=title,
            title_ar=(request.data.get("title_ar") or "").strip(),
            body=(request.data.get("body") or "").strip(),
            body_ar=(request.data.get("body_ar") or "").strip(),
            link=(request.data.get("link") or "").strip(),
            user_ids=user_ids,
            created_by=request.user,
        )
        return response.Response({"message": "Announcement sent."})


# ---------------------------------------------------------------------------
# Admin: platform settings
# ---------------------------------------------------------------------------

PLATFORM_SETTINGS_META = [
    ("referral_level_1_percent", "num", "Referral Level 1 (%)"),
    ("referral_level_2_percent", "num", "Referral Level 2 (%)"),
    ("referral_level_3_percent", "num", "Referral Level 3 (%)"),
    ("min_investment_amount", "num", "Minimum investment"),
    ("withdraw_cooldown_months", "num", "Withdraw cooldown (months)"),
    ("withdraw_cooldown_weeks", "num", "Withdraw cooldown (weeks)"),
    ("withdraw_cooldown_days", "num", "Withdraw cooldown (days)"),
    ("withdraw_cooldown_hours", "num", "Withdraw cooldown (hours)"),
    ("payout_cooldown_months", "num", "Payout cooldown (months)"),
    ("payout_cooldown_weeks", "num", "Payout cooldown (weeks)"),
    ("payout_cooldown_days", "num", "Payout cooldown (days)"),
    ("payout_cooldown_hours", "num", "Payout cooldown (hours)"),
    ("payout_percent", "num", "Payout percent used when opening a window (%)"),
    ("payout_duration_hours", "num", "Payout window duration (hours)"),
    ("kyc_required_to_invest", "bool", "Require KYC to invest"),
    ("kyc_required_to_withdraw", "bool", "Require KYC to withdraw"),
    ("withdraw_fee_percent", "num", "Withdraw fee (%)"),
    ("min_withdrawal_amount", "num", "Minimum withdrawal"),
    ("bonus_payout_percent", "num", "Bonus payout (%)"),
    ("default_lang", "str", "Default language (en/ar)"),
]


class AdminPlatformSettingsView(views.APIView):
    permission_classes = [IsStaffPermission]

    def get(self, request):
        data = {}
        for key, ktype, label in PLATFORM_SETTINGS_META:
            raw = PlatformSettings.get(key, "")
            if ktype == "bool":
                data[key] = PlatformSettings.get_bool(key, False)
            elif ktype == "num":
                data[key] = PlatformSettings.get_decimal(key, 0)
            else:
                data[key] = raw or "en"
        data["_meta"] = [
            {"key": key, "type": ktype, "label": label}
            for key, ktype, label in PLATFORM_SETTINGS_META
        ]
        return response.Response(data)

    def post(self, request):
        key_map = {row[0] for row in PLATFORM_SETTINGS_META}
        updated = []
        for key, value in request.data.items():
            if key not in key_map:
                continue
            ktype = next(t for k, t, _ in PLATFORM_SETTINGS_META if k == key)
            if ktype == "bool":
                val = "1" if str(value).lower() in {"1", "true", "yes", "on"} else "0"
            elif ktype == "num":
                try:
                    val = str(Decimal(str(value)))
                except Exception:
                    return response.Response({"detail": f"Invalid numeric value for {key}."}, 400)
            else:
                val = str(value).strip()[:40] or "en"
            PlatformSettings.objects.update_or_create(
                key=key, defaults={"value": val}
            )
            updated.append(key)
        if not updated:
            return response.Response({"detail": "No known settings provided."}, 400)
        return response.Response({"message": "Platform settings updated.", "keys": updated})