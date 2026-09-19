from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from rest_framework import serializers

from api.i18n import tr
from api.referrals import referral_tree_counts
from api.models import (
    Coin,
    CryptoAccount,
    Investment,
    KYCSubmission,
    Notification,
    Payout,
    PayoutWindow,
    PaymentOrder,
    PlatformSettings,
    ReferralAward,
    User,
    Wallet,
    Withdrawal,
)


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={"input_type": "password"})
    invite_code = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=20
    )

    class Meta:
        model = User
        fields = ["email", "password", "first_name", "last_name", "phone", "invite_code"]

    def validate_email(self, value):
        value = (value or "").strip().lower() or None
        if value and User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError(
                tr("An account with this email already exists.", self.context.get("request"))
            )
        return value

    def validate_phone(self, value):
        value = (value or "").strip() or None
        if value and User.objects.filter(phone__iexact=value).exists():
            raise serializers.ValidationError(
                tr("This phone number is already in use.", self.context.get("request"))
            )
        return value

    def validate(self, attrs):
        if not attrs.get("email") and not attrs.get("phone"):
            raise serializers.ValidationError(
                tr(
                    "Provide an email address or a phone number to create an account.",
                    self.context.get("request"),
                )
            )
        return attrs

    def validate_password(self, value):
        try:
            validate_password(value)
        except ValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def create(self, validated_data):
        invite_code = validated_data.pop("invite_code", "") or ""
        invite_code = invite_code.strip().upper()
        referred_by = None
        if invite_code:
            referred_by = User.objects.filter(invite_code=invite_code).first()
            if not referred_by:
                raise serializers.ValidationError(
                    {"invite_code": tr("Invite code is not valid.", self.context.get("request"))}
                )
        password = validated_data.pop("password")
        user = User(**validated_data)
        if referred_by and referred_by != user:
            user.referred_by = referred_by
        user.set_password(password)
        user.save()
        if referred_by:
            who = user.full_name or (user.email or user.phone or "").split()[0]
            Notification.send(
                referred_by,
                Notification.TYPE_INVITE,
                title=f"{who} joined using your invite code",
                title_ar=f"{who} انضم باستخدام رمز الدعوة الخاص بك",
                body="You earn a percentage of every investment they make.",
                body_ar="ستكسب نسبة مئوية من كل استثمار يقوم به.",
                link="/referrals",
            )
        return user


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    avatar_url = serializers.SerializerMethodField()
    has_kyc_pending = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "phone", "avatar", "avatar_url",
            "invite_code", "referral_link", "kyc_verified", "kyc_rejected", "is_frozen",
            "banned_until", "is_staff", "created_at", "full_name", "has_kyc_pending",
        ]
        read_only_fields = ["invite_code", "kyc_verified", "kyc_rejected", "is_frozen", "banned_until", "is_staff", "created_at"]

    referral_link = serializers.SerializerMethodField()

    def get_referral_link(self, obj):
        return obj.invite_code

    def validate_email(self, value):
        value = (value or "").strip().lower()
        if not value:
            raise serializers.ValidationError(
                tr("Email address is required.", self.context.get("request"))
            )
        qs = User.objects.filter(email__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                tr("An account with this email already exists.", self.context.get("request"))
            )
        return value

    def validate_phone(self, value):
        value = (value or "").strip()
        if value:
            qs = User.objects.filter(phone__iexact=value)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    tr("This phone number is already in use.", self.context.get("request"))
                )
        return value

    def get_avatar_url(self, obj):
        if obj.avatar:
            request = self.context.get("request")
            url = obj.avatar.url
            return request.build_absolute_uri(url) if request else url
        return None

    def get_has_kyc_pending(self, obj):
        return obj.kyc_submissions.filter(status=KYCSubmission.STATUS_PENDING).exists()

    def update(self, instance, validated_data):
        # Mutable profile fields (login identifiers are included).
        for field in ("email", "first_name", "last_name", "phone", "avatar"):
            if field in validated_data:
                setattr(instance, field, validated_data[field])
        instance.save()
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.check_password(attrs["old_password"]):
            raise serializers.ValidationError(
                {"old_password": tr("Current password is incorrect.", self.context.get("request"))}
            )
        try:
            validate_password(attrs["new_password"], user)
        except ValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)})
        return attrs


class CoinSerializer(serializers.ModelSerializer):
    icon_url = serializers.SerializerMethodField()
    current_price = serializers.SerializerMethodField()
    price_change_24h = serializers.SerializerMethodField()

    class Meta:
        model = Coin
        fields = [
            "id", "name", "symbol", "chain", "icon", "icon_url", "contract_address",
            "reference_price", "is_stable", "is_active", "min_invest", "current_price",
            "price_change_24h",
        ]

    def get_icon_url(self, obj):
        if obj.icon:
            request = self.context.get("request")
            url = obj.icon.url
            return request.build_absolute_uri(url) if request else url
        return None

    def get_current_price(self, obj):
        snap = obj.price_snapshots.first()
        return str(snap.price) if snap else str(obj.reference_price)

    def get_price_change_24h(self, obj):
        snap = obj.price_snapshots.first()
        return str(snap.change_24h) if snap and snap.change_24h is not None else "0.00"


class AdminCoinSerializer(serializers.ModelSerializer):
    icon_url = serializers.SerializerMethodField()

    class Meta:
        model = Coin
        fields = [
            "id", "name", "symbol", "chain", "contract_address", "reference_price",
            "is_stable", "is_active", "min_invest", "icon", "icon_url",
        ]

    def get_icon_url(self, obj):
        if obj.icon:
            request = self.context.get("request")
            url = obj.icon.url
            return request.build_absolute_uri(url) if request else url
        return None


class WalletSerializer(serializers.ModelSerializer):
    coin = CoinSerializer()
    total = serializers.SerializerMethodField()

    class Meta:
        model = Wallet
        fields = ["coin", "invested_balance", "withdrawable_balance", "total", "updated_at"]

    def get_total(self, obj):
        return str(obj.invested_balance + obj.withdrawable_balance)


class InvestmentInputSerializer(serializers.Serializer):
    coin_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=30, decimal_places=8)
    source_address = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")

    def validate(self, attrs):
        settings = PlatformSettings.public_map()
        if settings["kyc_required_to_invest"] and not self.context["request"].user.kyc_verified:
            raise serializers.ValidationError(
                tr("KYC verification is required to invest.", self.context.get("request"))
            )
        try:
            coin = Coin.objects.get(pk=attrs["coin_id"], is_active=True)
        except Coin.DoesNotExist:
            raise serializers.ValidationError(
                {"coin_id": tr("Invalid or inactive coin.", self.context.get("request"))}
            )
        if attrs["amount"] <= 0:
            raise serializers.ValidationError(
                {"amount": tr("Amount must be greater than zero.", self.context.get("request"))}
            )
        min_required = max(
            coin.min_invest,
            Decimal(str(PlatformSettings.get_decimal(PlatformSettings.S_MIN_INVESTMENT, 0))),
        )
        if attrs["amount"] < min_required:
            raise serializers.ValidationError(
                {
                    "amount": tr(
                        "Minimum investment for {symbol} is {min}.",
                        self.context.get("request"),
                        symbol=coin.symbol,
                        min=min_required,
                    )
                }
            )
        attrs["coin"] = coin
        return attrs


class InvestmentSerializer(serializers.ModelSerializer):
    coin_symbol = serializers.CharField(source="coin.symbol", read_only=True)
    coin_name = serializers.CharField(source="coin.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Investment
        fields = [
            "id", "coin_symbol", "coin_name", "amount", "status", "status_display",
            "source_address", "tx_hash", "admin_note", "rejected_reason", "created_at",
        ]


class WithdrawalInputSerializer(serializers.Serializer):
    coin_id = serializers.IntegerField()
    address = serializers.CharField(max_length=150)
    network = serializers.CharField(max_length=30, required=False)
    amount = serializers.DecimalField(max_digits=30, decimal_places=8)

    def validate(self, attrs):
        user = self.context["request"].user
        settings = PlatformSettings.public_map()
        if settings["kyc_required_to_withdraw"] and not user.kyc_verified:
            raise serializers.ValidationError(
                tr("KYC verification is required to withdraw.", self.context.get("request"))
            )
        if user.is_frozen:
            raise serializers.ValidationError(
                tr("Your account is frozen. Contact support.", self.context.get("request"))
            )

        try:
            coin = Coin.objects.get(pk=attrs["coin_id"], is_active=True)
        except Coin.DoesNotExist:
            raise serializers.ValidationError(
                {"coin_id": tr("Invalid or inactive coin.", self.context.get("request"))}
            )

        amount = attrs["amount"]
        if amount <= 0:
            raise serializers.ValidationError(
                {"amount": tr("Amount must be greater than zero.", self.context.get("request"))}
            )

        min_with = PlatformSettings.get_decimal(PlatformSettings.S_MIN_WITHDRAWAL, 0)
        if min_with and amount < min_with:
            raise serializers.ValidationError(
                {
                    "amount": tr(
                        "Minimum withdrawal is {min} {symbol}.",
                        self.context.get("request"),
                        min=min_with,
                        symbol=coin.symbol,
                    )
                }
            )

        cooldown_hours = PlatformSettings.cooldown_total_hours("withdraw_cooldown", (0, 0, 0, 24))
        if cooldown_hours > 0:
            last_withdrawal = user.withdrawals.exclude(
                status=Withdrawal.STATUS_REJECTED
            ).aggregate(latest=models.Max("created_at"))["latest"]
            if last_withdrawal and last_withdrawal > timezone.now() - timedelta(hours=cooldown_hours):
                raise serializers.ValidationError(
                    tr(
                        "You must wait {hours}h between withdrawals.",
                        self.context.get("request"),
                        hours=cooldown_hours,
                    )
                )

        wallet = Wallet.ensure(user, coin)
        fee_pct = PlatformSettings.get_decimal(PlatformSettings.S_WITHDRAW_FEE_PERCENT, 0)
        fee = (amount * Decimal(fee_pct)) / Decimal(100)
        net = amount - fee
        if net <= 0:
            raise serializers.ValidationError(
                {
                    "amount": tr(
                        "Amount is below the network fee threshold.",
                        self.context.get("request"),
                    )
                }
            )
        if wallet.withdrawable_balance < amount:
            raise serializers.ValidationError(
                {
                    "amount": tr(
                        "Insufficient withdrawable balance.", self.context.get("request")
                    )
                }
            )

        attrs["coin"] = coin
        attrs["fee"] = fee
        attrs["net_amount"] = net
        return attrs


class WithdrawalSerializer(serializers.ModelSerializer):
    coin_symbol = serializers.CharField(source="coin.symbol", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Withdrawal
        fields = [
            "id", "coin_symbol", "address", "network", "amount", "fee", "status",
            "status_display", "tx_hash", "reject_reason", "created_at",
        ]


class PaymentOrderSerializer(serializers.ModelSerializer):
    coin_symbol = serializers.CharField(source="coin.symbol", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    payment_mode = serializers.SerializerMethodField()

    class Meta:
        model = PaymentOrder
        fields = [
            "id", "coin_symbol", "amount", "order_ref", "address", "checkout_url",
            "chain", "status", "status_display", "tx_hash", "payment_mode", "created_at",
        ]

    def get_payment_mode(self, obj):
        return PlatformSettings.get("payment_mode", "simulate")


class PayoutSerializer(serializers.ModelSerializer):
    coin_symbol = serializers.CharField(source="coin.symbol", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Payout
        fields = [
            "id", "coin_symbol", "amount", "percent", "is_bonus", "status",
            "status_display", "destination_address", "note", "tx_hash", "created_at",
        ]


class PayoutWindowSerializer(serializers.ModelSerializer):
    coin_symbol = serializers.CharField(source="coin.symbol", read_only=True, default="")
    is_open = serializers.SerializerMethodField()
    time_left_hours = serializers.SerializerMethodField()
    claimed_count = serializers.SerializerMethodField()
    eligible_count = serializers.SerializerMethodField()
    total_granted = serializers.SerializerMethodField()
    target_users = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=User.objects.all()
    )
    target_emails = serializers.ListField(
        child=serializers.EmailField(), required=False, write_only=True
    )

    class Meta:
        model = PayoutWindow
        fields = [
            "id", "title", "percent", "coin", "coin_symbol", "duration_hours",
            "target_mode", "target_users", "target_emails", "is_active", "is_open", "time_left_hours",
            "activated_at", "opens_at", "ends_at",
            "claimed_count", "eligible_count", "total_granted", "created_at",
        ]
        read_only_fields = ["is_active", "activated_at", "opens_at", "ends_at",
                            "claimed_count", "eligible_count", "total_granted", "created_at"]

    def get_is_open(self, obj):
        return obj.is_open

    def get_time_left_hours(self, obj):
        return obj.time_left_hours

    def get_claimed_count(self, obj):
        return obj.claimed_by.count()

    def get_eligible_count(self, obj):
        return len(set(obj.eligible_user_ids()))

    def get_total_granted(self, obj):
        return str(
            obj.payout_claims.aggregate(total=models.Sum("amount"))["total"] or 0
        )

    def create(self, validated_data):
        target_emails = validated_data.pop("target_emails", [])
        target_users = validated_data.pop("target_users", [])
        if target_emails:
            target_users = list(User.objects.filter(email__in=target_emails))
        coin = validated_data.pop("coin", None)
        window = PayoutWindow.objects.create(coin=coin, **validated_data)
        window.target_users.set(target_users)
        return window


class UserPayoutWindowSerializer(serializers.ModelSerializer):
    coin_symbol = serializers.CharField(source="coin.symbol", read_only=True, default="")
    is_open = serializers.SerializerMethodField()
    time_left_hours = serializers.SerializerMethodField()
    claimed = serializers.SerializerMethodField()
    preview = serializers.SerializerMethodField()

    class Meta:
        model = PayoutWindow
        fields = [
            "id", "title", "percent", "coin_symbol", "is_open", "time_left_hours",
            "claimed", "preview", "ends_at",
        ]

    def get_is_open(self, obj):
        return obj.is_open

    def get_time_left_hours(self, obj):
        return obj.time_left_hours

    def get_claimed(self, obj):
        user = self.context["request"].user
        return obj.claimed_by.filter(pk=user.pk).exists()

    def get_preview(self, obj):
        return obj.preview_for(self.context["request"].user)


class AdminUserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    total_invested = serializers.SerializerMethodField()
    total_withdrawable = serializers.SerializerMethodField()
    wallets = serializers.SerializerMethodField()
    is_banned = serializers.ReadOnlyField()
    direct_invites = serializers.SerializerMethodField()
    level1_count = serializers.SerializerMethodField()
    level2_count = serializers.SerializerMethodField()
    level3_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "phone", "full_name", "kyc_verified", "kyc_rejected",
            "is_frozen", "is_banned", "banned_until", "is_active", "is_staff",
            "invite_code", "referred_by", "direct_invites",
            "level1_count", "level2_count", "level3_count",
            "total_invested", "total_withdrawable", "wallets", "created_at",
        ]

    def _tree_counts(self, obj):
        cache = self.context.setdefault("_referral_counts_cache", {})
        if obj.id in cache:
            return cache[obj.id]
        bulk = self.context.get("referral_counts")
        counts = bulk[obj.id] if bulk and obj.id in bulk else referral_tree_counts(obj)
        cache[obj.id] = counts
        return counts

    def get_direct_invites(self, obj):
        return self._tree_counts(obj)[1]

    def get_level1_count(self, obj):
        return self._tree_counts(obj)[1]

    def get_level2_count(self, obj):
        return self._tree_counts(obj)[2]

    def get_level3_count(self, obj):
        return self._tree_counts(obj)[3]

    def get_total_invested(self, obj):
        return str(obj.wallets.aggregate(total=models.Sum("invested_balance"))["total"] or 0)

    def get_total_withdrawable(self, obj):
        return str(obj.wallets.aggregate(total=models.Sum("withdrawable_balance"))["total"] or 0)

    def get_wallets(self, obj):
        return [
            {
                "coin_id": w.coin_id,
                "symbol": w.coin.symbol,
                "name": w.coin.name,
                "invested_balance": str(w.invested_balance),
                "withdrawable_balance": str(w.withdrawable_balance),
            }
            for w in obj.wallets.select_related("coin").order_by("coin__symbol")
        ]


class CryptoAccountSerializer(serializers.ModelSerializer):
    coin_symbol = serializers.CharField(source="coin.symbol", read_only=True)

    class Meta:
        model = CryptoAccount
        fields = ["id", "coin", "coin_symbol", "address", "label", "is_primary", "created_at"]
        read_only_fields = ["user"]

    def create(self, validated_data):
        validated_data["user"] = self.context["request"].user
        return super().create(validated_data)


class KYCSubmissionSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = KYCSubmission
        fields = [
            "id", "document_type", "first_name", "last_name", "document_front",
            "document_back", "selfie",
            "status", "status_display", "reason", "submitted_at", "reviewed_at",
        ]
        read_only_fields = ["user", "status", "reason", "submitted_at", "reviewed_at"]

    def validate(self, attrs):
        user = self.context["request"].user
        request = self.context.get("request")
        if user.kyc_verified:
            raise serializers.ValidationError(
                tr("Your account is already verified.", request)
            )
        if user.kyc_submissions.filter(status=KYCSubmission.STATUS_PENDING).exists():
            raise serializers.ValidationError(
                tr("You already have a pending KYC review.", request)
            )
        if not (attrs.get("first_name") or "").strip():
            raise serializers.ValidationError(
                {"first_name": tr("First name is required.", request)}
            )
        if not (attrs.get("last_name") or "").strip():
            raise serializers.ValidationError(
                {"last_name": tr("Last name is required.", request)}
            )
        if not attrs.get("document_front"):
            raise serializers.ValidationError(
                {"document_front": tr("Document front image is required.", request)}
            )
        return attrs


class AdminKycSubmissionSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    user_id = serializers.IntegerField(read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    document_front_url = serializers.SerializerMethodField()
    document_back_url = serializers.SerializerMethodField()
    selfie_url = serializers.SerializerMethodField()

    class Meta:
        model = KYCSubmission
        fields = [
            "id", "user_id", "user_email", "document_type", "document_front_url",
            "document_back_url", "selfie_url", "status", "status_display",
            "reason", "submitted_at", "reviewed_at",
        ]

    def _url(self, obj, field):
        img = getattr(obj, field, None)
        if not img:
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(img.url) if request else img.url

    def get_document_front_url(self, obj):
        return self._url(obj, "document_front")

    def get_document_back_url(self, obj):
        return self._url(obj, "document_back")

    def get_selfie_url(self, obj):
        return self._url(obj, "selfie")


class ReferralAwardSerializer(serializers.ModelSerializer):
    coin_symbol = serializers.CharField(source="coin.symbol", read_only=True)
    investor_email = serializers.CharField(source="user.email", read_only=True)

    class Meta:
        model = ReferralAward
        fields = [
            "id", "level", "percent", "amount", "coin_symbol", "investor_email",
            "status", "created_at",
        ]


class ReferralTreeSerializer(serializers.Serializer):
    invite_code = serializers.CharField()
    referral_link = serializers.CharField()
    level1_earned = serializers.CharField()
    level2_earned = serializers.CharField()
    level3_earned = serializers.CharField()
    total_earned = serializers.CharField()
    direct_invites = serializers.IntegerField()
    level1_count = serializers.IntegerField()
    level2_count = serializers.IntegerField()
    level3_count = serializers.IntegerField()
    total_referrals = serializers.IntegerField()
    awards = ReferralAwardSerializer(many=True)


class MarketSerializer(serializers.Serializer):
    coin = CoinSerializer()
    price = serializers.CharField()
    change_24h = serializers.CharField()
    captured_at = serializers.DateTimeField()


class SettingsSerializer(serializers.Serializer):
    referral_levels = serializers.SerializerMethodField()
    withdraw_cooldown_hours = serializers.CharField()
    payout_cooldown_hours = serializers.CharField()
    kyc_required_to_invest = serializers.BooleanField()
    kyc_required_to_withdraw = serializers.BooleanField()
    min_withdrawal = serializers.CharField()
    withdraw_fee_percent = serializers.CharField()

    def get_referral_levels(self, obj):
        return [
            {"level": 1, "percent": obj["l1_percent"]},
            {"level": 2, "percent": obj["l2_percent"]},
            {"level": 3, "percent": obj["l3_percent"]},
        ]