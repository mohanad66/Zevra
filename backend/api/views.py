import json
from datetime import timedelta
from decimal import Decimal

import requests
from django.db import models, transaction
from django.utils import timezone
from rest_framework import generics, permissions, response, status, views
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework_simplejwt.tokens import RefreshToken

from api.models import (
    Coin,
    CryptoAccount,
    Investment,
    KYCSubmission,
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
    PaymentOrderSerializer,
    RegisterSerializer,
    ReferralAwardSerializer,
    ReferralTreeSerializer,
    SettingsSerializer,
    UserSerializer,
    WalletSerializer,
    WithdrawalInputSerializer,
    WithdrawalSerializer,
    CryptoAccountSerializer,
    ChangePasswordSerializer,
    CoinSerializer,
    AdminUserSerializer,
    PayoutWindowSerializer,
    UserPayoutWindowSerializer,
    AdminKycSubmissionSerializer,
)
from api.services import (
    confirm_payment,
    create_payment_order,
    handle_gateway_webhook,
    verify_btcpay_signature,
    verify_nowpayments_signature,
    verify_webhook_signature,
    send_platform_to_user,
    estimated_network_fee,
    test_gateway_connection,
)

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        data = UserSerializer(user, context={"request": request}).data
        return response.Response(
            {"user": data, "message": "Account created. You can now log in."},
            status=status.HTTP_201_CREATED,
        )


class LoginView(views.APIView):
    permission_classes = [permissions.AllowAny]

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
                {"detail": "Invalid email/phone or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if user.is_frozen:
            return response.Response(
                {"detail": "Your account is frozen. Contact support."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if user.banned_until and user.banned_until > timezone.now():
            return response.Response(
                {"detail": "Your account is temporarily suspended. Try again later."},
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
        return response.Response({"message": "Password changed successfully."})


class LogoutView(views.APIView):
    def post(self, request):
        try:
            refresh = request.data.get("refresh")
            if refresh:
                RefreshToken(refresh).blacklist()
        except Exception:
            pass
        return response.Response({"message": "Logged out."})


class DeleteAccountView(views.APIView):
    def post(self, request):
        user = request.user
        # Freeze then mark inactive. Wallet/history are kept for compliance.
        user.is_active = False
        user.is_frozen = True
        user.save(update_fields=["is_active", "is_frozen"])
        return response.Response({"message": "Account deleted."})


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


class MarketView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def _refresh_market_prices(self):
        try:
            _refresh_market_prices()
        except Exception:
            pass

    def get(self, request):
        self._refresh_market_prices()
        coins = Coin.objects.filter(is_active=True)
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
        return response.Response({"data": data, "settings": PublicSettings.serialize(settings)})


class CoinListView(generics.ListAPIView):
    serializer_class = CoinSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

    def get_queryset(self):
        return Coin.objects.filter(is_active=True)


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
            return response.Response({"detail": "Your account is frozen."}, status=403)

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
                    or (
                        "Investment order created. Complete the crypto payment to confirm it."
                        if payload.get("status") != "manual"
                        else "Investment submitted. Awaiting payment and admin confirmation."
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
                {"detail": "order_ref is required."}, status=status.HTTP_400_BAD_REQUEST
            )
        order = PaymentOrder.objects.filter(order_ref=order_ref).first()
        if order is None:
            return response.Response(
                {"detail": "Payment order not found."}, status=status.HTTP_404_NOT_FOUND
            )
        if order.user_id != request.user.id:
            return response.Response(
                {"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND
            )
        ok, tx, message = confirm_payment(order_ref)
        if ok:
            order.investment.confirm()
            return response.Response(
                {
                    "investment": InvestmentSerializer(order.investment).data,
                    "tx_hash": tx,
                    "message": (
                        "Payment received. Your investment is confirmed and your balance is updated."
                        if message != "already_paid"
                        else "This payment was already confirmed."
                    ),
                }
            )
        return response.Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)


class GatewayWebhookView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        """Signed callback from the crypto payment gateway.

        Three signature schemes are accepted:
          * ``X-Gateway-Signature`` – HMAC-SHA256 over the raw body
            (PAYMENT_WEBHOOK_TOKEN).
          * ``BTCPay-Sig``          – BTCPay Server webhook: ``sha256=<hex>``
            HMAC-SHA256 over the raw body with the webhook secret.
          * ``X-NowPayments-Sig``   – NOWPayments IPN: HMAC-SHA512 over the raw
            body (signed JSON string with keys sorted) using the IPN secret key.
        """
        raw = request.body
        sig_gateway = request.META.get("HTTP_X_GATEWAY_SIGNATURE", "")
        sig_btcpay = request.META.get("HTTP_BTCPAY_SIG", "")
        sig_nowpayments = request.META.get("HTTP_X_NOWPAYMENTS_SIG", "")
        ok = (
            bool(sig_gateway and verify_webhook_signature(raw, sig_gateway))
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
        if handle_gateway_webhook(data):
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


class AdminPaymentSettingsView(views.APIView):
    permission_classes = [IsStaffPermission]

    def get(self, request):
        mode = PlatformSettings.get(PlatformSettings.S_PAYMENT_MODE, "simulate")
        url = PlatformSettings.get(PlatformSettings.S_PAYMENT_PROVIDER_URL, "")
        key = PlatformSettings.get(PlatformSettings.S_PAYMENT_PROVIDER_KEY, "")
        token = PlatformSettings.get(
            PlatformSettings.S_PAYMENT_WEBHOOK_TOKEN, "dev-gateway-secret"
        )

        def mask(v):
            v = str(v).strip()
            if len(v) <= 4:
                return "****"
            return f"{v[-4:]}".rjust(len(v), "*")

        wallets = CryptoAccount.objects.filter(is_platform=True).select_related("coin", "user")
        return response.Response({
            "payment_mode": mode,
            "provider": {
                "url": url,
                "key_masked": mask(key) if key else "",
                "key_set": bool(key),
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
        for field_name, key, label in (
            ("provider_url", PlatformSettings.S_PAYMENT_PROVIDER_URL, "BTCPay instance base URL"),
            ("provider_key", PlatformSettings.S_PAYMENT_PROVIDER_KEY, "BTCPay API key"),
            ("store_id", PlatformSettings.S_PAYMENT_STORE_ID, "BTCPay store ID"),
            ("webhook_token", PlatformSettings.S_PAYMENT_WEBHOOK_TOKEN, "Webhook HMAC/secret"),
            ("callback_url", PlatformSettings.S_PAYMENT_CALLBACK_URL, "Webhook callback URL"),
            ("success_url", PlatformSettings.S_PAYMENT_SUCCESS_URL, "Success redirect URL"),
        ):
            val = (request.data.get(field_name) or "").strip()
            if field_name in request.data and val:
                PlatformSettings.objects.update_or_create(
                    key=key, defaults={"value": val, "label": label}
                )
            elif field_name in request.data:
                PlatformSettings.objects.filter(key=key).delete()
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
        ok, message = test_gateway_connection()
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


class AdminWindowsView(generics.ListCreateAPIView):
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

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


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
            # Optional percent + target on open.
            if "percent" in data:
                try:
                    window.percent = Decimal(str(data.get("percent")))
                except Exception:
                    return response.Response({"detail": "Invalid percent."}, 400)
            target_changed = False
            if "target_user_ids" in data:
                ids = data.get("target_user_ids")
                if not isinstance(ids, list):
                    return response.Response({"detail": "target_user_ids must be a list of user ids."}, 400)
                if self._apply_target(window, ids) is None:
                    return response.Response({"detail": "target_user_ids must be a list of user ids."}, 400)
                target_changed = True
            if "percent" in data or target_changed:
                window.save(update_fields=["percent", "target_mode"])
            # Keep a single open payout at a time: close any others.
            PayoutWindow.objects.filter(is_active=True).exclude(pk=window.pk).update(
                is_active=False
            )
            ends_at = window.activate()
            scope = "all users" if window.target_mode == PayoutWindow.TARGET_ALL else (
                f"{window.target_users.count()} selected users"
            )
            return response.Response(
                {
                    "message": f"'{window.title}' opened ({scope}) until {ends_at:%d %b %Y %H:%M}.",
                    "ends_at": ends_at,
                }
            )
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
            return response.Response({"detail": "Payout not found."}, 404)
        with transaction.atomic():
            ok, message, grants = window.grant_to(request.user)
        if not ok:
            return response.Response({"detail": message}, 400)
        return response.Response(
            {"message": message, "grants": grants, "window": window.title}
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
                user=user,
                coin=coin,
                address=address,
                network=network,
                amount=amount,
                fee=fee,
            )
        return response.Response(
            {
                "withdrawal": WithdrawalSerializer(withdrawal).data,
                "message": (
                    "Withdrawal request created and is pending approval. "
                    "Funds are reserved and will be sent to your address once approved."
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
                "message": "KYC documents submitted for review.",
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
        awards = user.invited_users.select_related("coin", "user").order_by("-created_at")
        data = {
            "invite_code": user.invite_code,
            "referral_link": user.invite_code,
            "direct_invites": user.referrals.count(),
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
        }


class PublicSettingsView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        settings = PlatformSettings.public_map()
        return response.Response(PublicSettings.serialize(settings))


# ---------------------------------------------------------------------------
# Referral invite resolver (used on registration & invest)
# ---------------------------------------------------------------------------


def get_referral_levels_for(coin, amount):
    from api.referrals import referral_percent

    return {lvl: str(referral_percent(lvl)) for lvl in (1, 2, 3)}