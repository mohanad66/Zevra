import secrets
import uuid
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db import models
from django.db.models import Sum
from django.utils import timezone

VALID_NETWORKS = ["TRC20", "ERC20", "BEP20", "BEP2", "SOL", "TON"]


class UserManager(DjangoUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Users require an email address.")
        email = self.normalize_email(email)
        username = extra_fields.pop("username", None) or email
        user = self.model(username=username, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    email = models.EmailField(unique=True, null=True, blank=True)
    phone = models.CharField(max_length=30, blank=True, default="")
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    invite_code = models.CharField(max_length=20, unique=True, blank=True)
    referred_by = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="referrals"
    )
    kyc_verified = models.BooleanField(default=False)
    kyc_rejected = models.BooleanField(default=False)
    is_frozen = models.BooleanField(default=False)
    banned_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["phone"], condition=~models.Q(phone=""), name="unique_phone_nonblank"
            )
        ]

    @property
    def login_name(self):
        return self.email or self.phone

    def save(self, *args, **kwargs):
        if not self.username:
            self.username = self.email or f"user_{uuid.uuid4().hex[:12]}"
        if not self.invite_code:
            self.invite_code = secrets.token_hex(4).upper()
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.login_name

    @property
    def is_banned(self):
        return bool(self.banned_until and self.banned_until > timezone.now())

    def __str__(self):
        return self.login_name


class Coin(models.Model):
    name = models.CharField(max_length=60)
    symbol = models.CharField(max_length=20, unique=True)
    chain = models.CharField(max_length=30, default="TRC20", choices=[(n, n) for n in VALID_NETWORKS])
    icon = models.ImageField(upload_to="coins/", null=True, blank=True)
    contract_address = models.CharField(max_length=120, blank=True, default="")
    reference_price = models.DecimalField(max_digits=20, decimal_places=8, default=1)
    is_stable = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    min_invest = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.symbol})"


class Wallet(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="wallets")
    coin = models.ForeignKey(Coin, on_delete=models.CASCADE, related_name="wallets")
    invested_balance = models.DecimalField(max_digits=30, decimal_places=8, default=0)
    withdrawable_balance = models.DecimalField(max_digits=30, decimal_places=8, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("user", "coin")

    def __str__(self):
        return f"{self.user.email} - {self.coin.symbol}: {self.invested_balance} / {self.withdrawable_balance}"

    @classmethod
    def ensure(cls, user, coin):
        wallet, _ = cls.objects.get_or_create(user=user, coin=coin)
        return wallet

    def snapshot(self):
        return {
            "coin": self.coin.symbol,
            "invested_balance": str(self.invested_balance),
            "withdrawable_balance": str(self.withdrawable_balance),
        }


class Investment(models.Model):
    STATUS_PENDING = "pending"
    STATUS_CONFIRMED = "confirmed"
    STATUS_REJECTED = "rejected"
    STATUS = [
        (STATUS_PENDING, "Pending"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_REJECTED, "Rejected"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="investments")
    coin = models.ForeignKey(Coin, on_delete=models.PROTECT, related_name="investments")
    amount = models.DecimalField(max_digits=30, decimal_places=8)
    status = models.CharField(max_length=20, choices=STATUS, default=STATUS_PENDING)
    source_address = models.CharField(max_length=150, blank=True, default="")
    tx_hash = models.CharField(max_length=150, blank=True, default="")
    admin_note = models.CharField(max_length=500, blank=True, default="")
    rejected_reason = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} +{self.amount} {self.coin.symbol} [{self.status}]"

    def confirm(self):
        if self.status != self.STATUS_PENDING:
            return
        self.status = self.STATUS_CONFIRMED
        self.save(update_fields=["status", "updated_at"])
        wallet = Wallet.ensure(self.user, self.coin)
        wallet.invested_balance += self.amount
        wallet.save(update_fields=["invested_balance", "updated_at"])
        from api.referrals import distribute_referral_awards

        distribute_referral_awards(self)


class Payout(models.Model):
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS = [
        (STATUS_PROCESSING, "Processing"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="payouts")
    coin = models.ForeignKey(Coin, on_delete=models.PROTECT, related_name="payouts")
    amount = models.DecimalField(max_digits=30, decimal_places=8)
    status = models.CharField(max_length=20, choices=STATUS, default=STATUS_PROCESSING)
    destination_address = models.CharField(max_length=150, blank=True, default="")
    percent = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    is_bonus = models.BooleanField(default=False)
    payout_window = models.ForeignKey(
        "PayoutWindow", null=True, blank=True, on_delete=models.SET_NULL, related_name="payout_claims"
    )
    note = models.CharField(max_length=500, blank=True, default="")
    tx_hash = models.CharField(max_length=150, blank=True, default="")
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="issued_payouts"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def credit_wallet(self):
        """Credit an internal bonus/profit into the user's withdrawable balance."""
        wallet = Wallet.ensure(self.user, self.coin)
        wallet.withdrawable_balance += self.amount
        wallet.save(update_fields=["withdrawable_balance", "updated_at"])


class PayoutWindow(models.Model):
    """A time-boxed payout the admin opens for users to claim.

    When active, eligible users see a claim button; claiming credits their
    withdrawable balance with ``percent`` % of their invested balance (per coin).
    ``coin`` may be left empty to apply to every coin the user has invested in.
    """

    TARGET_ALL = "all"
    TARGET_SPECIFIC = "specific"
    TARGET = [
        (TARGET_ALL, "All users"),
        (TARGET_SPECIFIC, "Specific users"),
    ]

    title = models.CharField(max_length=120)
    percent = models.DecimalField(max_digits=7, decimal_places=2)
    coin = models.ForeignKey(
        Coin, null=True, blank=True, on_delete=models.SET_NULL, related_name="payout_windows"
    )
    duration_hours = models.PositiveIntegerField(default=168)
    is_active = models.BooleanField(default=False)
    opens_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    target_mode = models.CharField(max_length=10, choices=TARGET, default=TARGET_ALL)
    target_users = models.ManyToManyField(
        User, blank=True, related_name="targeted_windows"
    )
    claimed_by = models.ManyToManyField(
        User, blank=True, related_name="claimed_windows"
    )
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_windows"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.percent}%)"

    def activate(self):
        """Open the window. Returns the updated ``ends_at``."""
        now = timezone.now()
        self.activated_at = now
        self.opens_at = now
        self.ends_at = now + timedelta(hours=self.duration_hours)
        self.is_active = True
        self.save(update_fields=["activated_at", "opens_at", "ends_at", "is_active"])
        return self.ends_at

    def close(self):
        """Close the window (also used to undo an accidental activation)."""
        self.is_active = False
        self.save(update_fields=["is_active"])

    @property
    def is_open(self):
        now = timezone.now()
        return (
            self.is_active
            and self.opens_at is not None
            and self.ends_at is not None
            and self.opens_at <= now <= self.ends_at
        )

    @property
    def time_left_hours(self):
        if not self.is_open or self.ends_at is None:
            return 0
        return max(0.0, (self.ends_at - timezone.now()).total_seconds() / 3600)

    def is_eligible_for(self, user):
        if user.is_frozen or not user.is_active:
            return False
        if (
            self.target_mode == self.TARGET_SPECIFIC
            and not self.target_users.filter(pk=user.pk).exists()
        ):
            return False
        wallets = Wallet.objects.filter(user=user, invested_balance__gt=0)
        if self.coin_id:
            wallets = wallets.filter(coin_id=self.coin_id)
        return wallets.exists()

    def eligible_user_ids(self):
        """Users that have something to claim (invested balance in scope)."""
        qs = User.objects.filter(is_active=True)
        if self.coin_id:
            qs = qs.filter(wallets__coin_id=self.coin_id, wallets__invested_balance__gt=0)
        else:
            qs = qs.filter(wallets__invested_balance__gt=0)
        if self.target_mode == self.TARGET_SPECIFIC:
            qs = qs.filter(pk__in=self.target_users.all())
        return qs.values_list("pk", flat=True).distinct()

    def preview_for(self, user):
        """Per-coin amount the user would receive right now."""
        rows = []
        coin = self.coin
        wallets = user.wallets.filter(invested_balance__gt=0).select_related("coin")
        if coin:
            wallets = wallets.filter(coin=coin)
        for w in wallets:
            amount = (
                w.invested_balance * self.percent / Decimal(100)
            ).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
            if amount > 0:
                rows.append(
                    {
                        "coin_symbol": w.coin.symbol,
                        "invested_balance": str(w.invested_balance),
                        "amount": str(amount),
                    }
                )
        return rows

    def grant_to(self, user):
        """Credit the claim to the user. Returns (ok, message_or_list, extra)."""
        if not self.is_open:
            return False, "This payout is not open right now.", []
        if self.target_mode == self.TARGET_SPECIFIC and not self.target_users.filter(
            pk=user.pk
        ).exists():
            return False, "You are not eligible for this payout.", []
        if self.claimed_by.filter(pk=user.pk).exists():
            return False, "You have already claimed this payout.", []
        if user.is_frozen or not user.is_active:
            return False, "Your account is not eligible right now.", []

        grants = []
        for w in user.wallets.filter(invested_balance__gt=0).select_for_update():
            if self.coin_id and w.coin_id != self.coin_id:
                continue
            amount = (
                w.invested_balance * self.percent / Decimal(100)
            ).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
            if amount <= 0:
                continue
            Payout.objects.create(
                user=user,
                coin=w.coin,
                amount=amount,
                status=Payout.STATUS_COMPLETED,
                destination_address="",
                percent=self.percent,
                is_bonus=True,
                payout_window=self,
                note=f"{self.title} payout ({self.percent}%)",
                created_by=self.created_by,
            )
            w.withdrawable_balance += amount
            w.save(update_fields=["withdrawable_balance", "updated_at"])
            grants.append({"coin_symbol": w.coin.symbol, "amount": str(amount)})

        if not grants:
            return False, "You have no invested balance in this payout.", []
        self.claimed_by.add(user)
        return True, "Payout claimed and added to your withdrawable balance.", grants


class PaymentOrder(models.Model):
    """A crypto payment order created when a user invests.

    In ``simulate`` mode the order carries a (fake) deposit address and ``confirm``
    is called by the user; in ``provider`` mode the gateway (e.g. Binance Pay)
    confirms via the signed webhook; in ``manual`` mode an admin confirms the
    investment directly.
    """

    STATUS_PENDING = "pending"
    STATUS_PAID = "paid"
    STATUS_EXPIRED = "expired"
    STATUS_FAILED = "failed"
    STATUS = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PAID, "Paid"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_FAILED, "Failed"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="payment_orders")
    investment = models.OneToOneField(Investment, on_delete=models.CASCADE, related_name="payment_order")
    coin = models.ForeignKey(Coin, on_delete=models.PROTECT, related_name="payment_orders")
    amount = models.DecimalField(max_digits=30, decimal_places=8)
    order_ref = models.CharField(max_length=120, unique=True)
    address = models.CharField(max_length=150, blank=True, default="")
    checkout_url = models.CharField(max_length=500, blank=True, default="")
    provider_order_id = models.CharField(max_length=120, blank=True, default="")
    provider_token = models.CharField(max_length=250, blank=True, default="")
    chain = models.CharField(max_length=30, default="TRC20")
    status = models.CharField(max_length=20, choices=STATUS, default=STATUS_PENDING)
    tx_hash = models.CharField(max_length=150, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def mark_paid(self, tx_hash=""):
        self.status = self.STATUS_PAID
        if tx_hash:
            self.tx_hash = tx_hash
        self.save(update_fields=["status", "tx_hash", "updated_at"])


class Withdrawal(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_REJECTED = "rejected"
    STATUS_CANCELLED = "cancelled"
    STATUS = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="withdrawals")
    coin = models.ForeignKey(Coin, on_delete=models.PROTECT, related_name="withdrawals")
    address = models.CharField(max_length=150)
    network = models.CharField(max_length=30, default="TRC20")
    amount = models.DecimalField(max_digits=30, decimal_places=8)
    fee = models.DecimalField(max_digits=30, decimal_places=8, default=0)
    status = models.CharField(max_length=20, choices=STATUS, default=STATUS_PENDING)
    tx_hash = models.CharField(max_length=150, blank=True, default="")
    reject_reason = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} -{self.amount} {self.coin.symbol} [{self.status}]"


class CryptoAccount(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="crypto_accounts")
    coin = models.ForeignKey(Coin, on_delete=models.PROTECT, related_name="crypto_accounts")
    address = models.CharField(max_length=150)
    label = models.CharField(max_length=60, blank=True, default="")
    is_primary = models.BooleanField(default=False)
    is_platform = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} - {self.coin.symbol}: {self.address}"


class ReferralAward(models.Model):
    STATUS_ACTIVE = "active"
    STATUS_PAID = "paid"
    STATUS = [(STATUS_ACTIVE, "Active"), (STATUS_PAID, "Paid")]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="referral_awards")
    inviter = models.ForeignKey(User, on_delete=models.CASCADE, related_name="invited_users")
    level = models.PositiveSmallIntegerField(help_text="1 = direct, 2 = indirect, 3 = indirect level 2")
    percent = models.DecimalField(max_digits=6, decimal_places=2)
    amount = models.DecimalField(max_digits=30, decimal_places=8)
    coin = models.ForeignKey(Coin, on_delete=models.PROTECT, related_name="referral_awards")
    source_investment = models.ForeignKey(
        Investment, on_delete=models.CASCADE, related_name="referral_awards"
    )
    status = models.CharField(max_length=20, choices=STATUS, default=STATUS_ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"L{self.level} award {self.amount} {self.coin.symbol} to {self.inviter.email}"


class KYCSubmission(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS = [
        (STATUS_PENDING, "Pending"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="kyc_submissions")
    document_type = models.CharField(max_length=40, default="ID")
    document_front = models.ImageField(upload_to="kyc/")
    document_back = models.ImageField(upload_to="kyc/", null=True, blank=True)
    selfie = models.ImageField(upload_to="kyc/", null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default=STATUS_PENDING)
    reason = models.CharField(max_length=500, blank=True, default="")
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"{self.user.email} KYC [{self.status}]"


class PlatformSettings(models.Model):
    key = models.CharField(max_length=40, unique=True)
    value = models.CharField(max_length=300, default="")
    label = models.CharField(max_length=120, blank=True, default="")

    # Well-known setting keys used by the platform
    S_REFERRAL_L1 = "referral_level_1_percent"
    S_REFERRAL_L2 = "referral_level_2_percent"
    S_REFERRAL_L3 = "referral_level_3_percent"
    S_WITHDRAW_COOLDOWN_HOURS = "withdraw_cooldown_hours"
    S_PAYOUT_COOLDOWN_HOURS = "payout_cooldown_hours"
    S_KYC_REQUIRED_TO_INVEST = "kyc_required_to_invest"
    S_KYC_REQUIRED_TO_WITHDRAW = "kyc_required_to_withdraw"
    S_WITHDRAW_FEE_PERCENT = "withdraw_fee_percent"
    S_BONUS_PERCENT = "bonus_payout_percent"
    S_MIN_WITHDRAWAL = "min_withdrawal_amount"
    S_PAYMENT_MODE = "payment_mode"
    S_PAYMENT_PROVIDER_URL = "payment_provider_url"
    S_PAYMENT_PROVIDER_KEY = "payment_provider_key"
    S_PAYMENT_WEBHOOK_TOKEN = "payment_webhook_token"
    S_PAYMENT_CALLBACK_URL = "payment_callback_url"
    S_PAYMENT_STORE_ID = "payment_store_id"
    S_PAYMENT_SUCCESS_URL = "payment_success_url"

    def __str__(self):
        return f"{self.key}={self.value}"

    class Meta:
        verbose_name = "Platform Setting"
        verbose_name_plural = "Platform Settings"

    @classmethod
    def get(cls, key, default=None):
        try:
            return cls.objects.get(key=key).value
        except cls.DoesNotExist:
            return default

    @classmethod
    def get_decimal(cls, key, default=0):
        try:
            return float(cls.get(key, default))
        except (TypeError, ValueError):
            return default

    @classmethod
    def get_bool(cls, key, default=False):
        val = cls.get(key, "1" if default else "0")
        return str(val).lower() in {"1", "true", "yes", "on"}

    @classmethod
    def public_map(cls):
        return {
            "l1_percent": cls.get_decimal(cls.S_REFERRAL_L1, 1),
            "l2_percent": cls.get_decimal(cls.S_REFERRAL_L2, 0.5),
            "l3_percent": cls.get_decimal(cls.S_REFERRAL_L3, 0.25),
            "withdraw_cooldown_hours": cls.get_decimal(cls.S_WITHDRAW_COOLDOWN_HOURS, 24),
            "payout_cooldown_hours": cls.get_decimal(cls.S_PAYOUT_COOLDOWN_HOURS, 0),
            "kyc_required_to_invest": cls.get_bool(cls.S_KYC_REQUIRED_TO_INVEST, False),
            "kyc_required_to_withdraw": cls.get_bool(cls.S_KYC_REQUIRED_TO_WITHDRAW, False),
            "withdraw_fee_percent": cls.get_decimal(cls.S_WITHDRAW_FEE_PERCENT, 1),
            "min_withdrawal": cls.get_decimal(cls.S_MIN_WITHDRAWAL, 10),
        }


class PriceSnapshot(models.Model):
    coin = models.ForeignKey(Coin, on_delete=models.CASCADE, related_name="price_snapshots")
    price = models.DecimalField(max_digits=30, decimal_places=10)
    volume_24h = models.DecimalField(max_digits=30, decimal_places=2, null=True, blank=True)
    change_24h = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    captured_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-captured_at"]

    def __str__(self):
        return f"{self.coin.symbol} ${self.price} @ {self.captured_at:%Y-%m-%d %H:%M}"


def default_referral_levels():
    return {
        PlatformSettings.S_REFERRAL_L1: "1",
        PlatformSettings.S_REFERRAL_L2: "0.5",
        PlatformSettings.S_REFERRAL_L3: "0.25",
    }