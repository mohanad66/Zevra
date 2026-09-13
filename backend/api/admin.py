from decimal import Decimal, ROUND_HALF_UP

from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.db import transaction
from django.utils import timezone

from api.models import (
    Coin,
    CryptoAccount,
    Investment,
    KYCSubmission,
    Payout,
    PayoutWindow,
    PaymentOrder,
    PlatformSettings,
    PriceSnapshot,
    ReferralAward,
    User,
    Wallet,
    Withdrawal,
)
from api.services import send_platform_to_user


class InviteFilter(admin.SimpleListFilter):
    title = "Has investor"
    parameter_name = "has_investor"

    def lookups(self, request, model_admin):
        return (("yes", "Yes"), ("no", "No"))

    def queryset(self, request, queryset):
        if self.value() == "yes":
            return queryset.filter(referred_by__isnull=False)
        if self.value() == "no":
            return queryset.filter(referred_by__isnull=True)
        return queryset


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "email", "full_name", "phone", "invite_code", "referred_by",
        "kyc_verified", "is_frozen", "is_active", "is_staff", "created_at",
    )
    list_filter = ("is_active", "is_staff", "is_superuser", "kyc_verified", "is_frozen", InviteFilter)
    search_fields = ("email", "first_name", "last_name", "phone", "invite_code")
    ordering = ("-created_at",)
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Zevra profile", {"fields": ("phone", "avatar", "invite_code", "referred_by", "kyc_verified", "kyc_rejected", "is_frozen", "banned_until")}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ("Zevra profile", {"fields": ("email", "first_name", "last_name", "phone", "referred_by")}),
    )
    readonly_fields = ("created_at",)

    actions = ["freeze_users", "unfreeze_users", "mark_kyc_approved", "mark_kyc_rejected", "grant_bonus"]

    @admin.action(description="Freeze selected users")
    def freeze_users(self, request, queryset):
        queryset.update(is_frozen=True)

    @admin.action(description="Unfreeze selected users")
    def unfreeze_users(self, request, queryset):
        queryset.update(is_frozen=False)

    @admin.action(description="Approve KYC for selected users")
    def mark_kyc_approved(self, request, queryset):
        queryset.update(kyc_verified=True, kyc_rejected=False)

    @admin.action(description="Reject KYC for selected users")
    def mark_kyc_rejected(self, request, queryset):
        queryset.update(kyc_verified=False, kyc_rejected=True)

    @admin.action(
        description="Grant bonus %% to selected users (uses 'bonus_payout_percent' setting, credited to withdrawable balance)"
    )
    def grant_bonus(self, request, queryset):
        percent = PlatformSettings.get_decimal(PlatformSettings.S_BONUS_PERCENT, 0)
        if percent <= 0:
            self.message_user(
                request,
                f"Set the 'bonus_payout_percent' Platform Setting above 0 first (current: {percent}).",
                level=messages.ERROR,
            )
            return
        granted, total = 0, Decimal("0")
        with transaction.atomic():
            for user in queryset.filter(is_active=True):
                for wallet in user.wallets.filter(invested_balance__gt=0).select_for_update():
                    amount = (
                        wallet.invested_balance * Decimal(str(percent)) / Decimal(100)
                    ).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
                    if amount <= 0:
                        continue
                    payout = Payout.objects.create(
                        user=user,
                        coin=wallet.coin,
                        amount=amount,
                        status=Payout.STATUS_COMPLETED,
                        destination_address="",
                        percent=Decimal(str(percent)).quantize(Decimal("0.01")),
                        is_bonus=True,
                        note=f"Bonus {percent}% on invested {wallet.coin.symbol}",
                        created_by=request.user,
                    )
                    payout.credit_wallet()
                    granted += 1
                    total += amount
        self.message_user(
            request, f"Bonus granted: {granted} credit(s), total {total} {'' if granted else '(no active wallets to credit)'}."
        )


@admin.register(Coin)
class CoinAdmin(admin.ModelAdmin):
    list_display = ("name", "symbol", "chain", "is_stable", "is_active", "reference_price", "min_invest")
    list_editable = ("is_active",)
    list_filter = ("is_stable", "is_active", "chain")
    search_fields = ("name", "symbol", "contract_address")


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("user", "coin", "invested_balance", "withdrawable_balance", "updated_at")
    list_filter = ("coin",)
    search_fields = ("user__email",)
    readonly_fields = ("user", "coin")

    def has_add_permission(self, request):
        return False


@admin.register(Investment)
class InvestmentAdmin(admin.ModelAdmin):
    list_display = ("user", "coin", "amount", "status", "tx_hash", "payment_status", "created_at")
    list_filter = ("status", "coin")
    search_fields = ("user__email", "tx_hash", "source_address")
    readonly_fields = ("created_at", "updated_at")
    actions = ["confirm_investments", "reject_investments"]

    @admin.display(description="payment")
    def payment_status(self, obj):
        order = getattr(obj, "payment_order", None)
        return order.status if order else "—"

    @admin.action(description="Confirm selected investments (credits balance + referral awards)")
    def confirm_investments(self, request, queryset):
        count = 0
        for inv in queryset.filter(status=Investment.STATUS_PENDING):
            inv.confirm()
            order = getattr(inv, "payment_order", None)
            if order and order.status != PaymentOrder.STATUS_PAID:
                order.mark_paid("admin")
            count += 1
        self.message_user(request, f"{count} investment(s) confirmed.")

    @admin.action(description="Reject selected investments")
    def reject_investments(self, request, queryset):
        for inv in queryset.filter(status=Investment.STATUS_PENDING):
            inv.status = Investment.STATUS_REJECTED
            inv.save(update_fields=["status", "updated_at"])
        self.message_user(request, "Investments rejected.")


@admin.register(PayoutWindow)
class PayoutWindowAdmin(admin.ModelAdmin):
    list_display = ("title", "percent", "coin", "duration_hours", "is_active", "opens_at", "ends_at", "target_mode")
    list_filter = ("is_active", "target_mode", "coin")
    search_fields = ("title",)
    readonly_fields = ("activated_at", "opens_at", "ends_at", "created_at", "updated_at")


@admin.register(PaymentOrder)
class PaymentOrderAdmin(admin.ModelAdmin):
    list_display = ("order_ref", "user", "coin", "amount", "chain", "status", "tx_hash", "created_at")
    list_filter = ("status", "coin", "chain")
    search_fields = ("order_ref", "user__email", "address", "tx_hash")
    readonly_fields = ("created_at", "updated_at")

    def has_add_permission(self, request):
        return False


@admin.register(Withdrawal)
class WithdrawalAdmin(admin.ModelAdmin):
    list_display = ("user", "coin", "amount", "fee", "address", "status", "tx_hash", "created_at")
    list_filter = ("status", "coin", "network")
    search_fields = ("user__email", "address", "tx_hash")
    readonly_fields = ("user", "coin", "address", "amount", "fee", "created_at", "updated_at")
    actions = ["approve_withdrawals", "reject_withdrawals"]

    @admin.action(description="Approve & pay selected withdrawals")
    def approve_withdrawals(self, request, queryset):
        sent = 0
        for wd in queryset.filter(status=Withdrawal.STATUS_PENDING):
            try:
                tx = send_platform_to_user(wd.coin, wd.address, wd.amount, wd.network)
                wd.status = Withdrawal.STATUS_COMPLETED
                wd.tx_hash = tx
                wd.save(update_fields=["status", "tx_hash", "updated_at"])
                sent += 1
            except Exception as exc:  # noqa: BLE001
                wd.status = Withdrawal.STATUS_FAILED
                wd.reject_reason = f"Transfer failed: {exc}"
                wd.save(update_fields=["status", "reject_reason", "updated_at"])
        self.message_user(request, f"{sent} withdrawal(s) paid out.")

    @admin.action(description="Reject selected withdrawals (refund balance)")
    def reject_withdrawals(self, request, queryset):
        from api.models import Wallet as WalletModel
        from decimal import Decimal

        count = 0
        for wd in queryset.filter(status=Withdrawal.STATUS_PENDING):
            wallet = WalletModel.ensure(wd.user, wd.coin)
            wallet.withdrawable_balance += wd.amount
            wallet.save(update_fields=["withdrawable_balance", "updated_at"])
            wd.status = Withdrawal.STATUS_REJECTED
            wd.reject_reason = "Rejected by administration"
            wd.save(update_fields=["status", "reject_reason", "updated_at"])
            count += 1
        self.message_user(request, f"{count} withdrawal(s) rejected and refunded.")


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ("user", "coin", "amount", "destination_address", "status", "tx_hash", "created_at")
    list_filter = ("status", "coin")
    search_fields = ("user__email", "destination_address", "tx_hash")
    readonly_fields = ("created_by", "created_at", "updated_at")
    actions = ["pay_payouts", "fail_payouts", "cancel_payouts"]

    def save_model(self, request, obj, form, change):
        obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="Pay selected payouts (auto-transfer from platform wallet)")
    def pay_payouts(self, request, queryset):
        sent = 0
        for po in queryset.filter(status=Payout.STATUS_PROCESSING):
            try:
                tx = send_platform_to_user(po.coin, po.destination_address, po.amount, po.coin.chain)
                po.status = Payout.STATUS_COMPLETED
                po.tx_hash = tx
                po.save(update_fields=["status", "tx_hash", "updated_at"])
                sent += 1
            except Exception as exc:  # noqa: BLE001
                po.status = Payout.STATUS_FAILED
                po.note = f"{po.note}\nTransfer failed: {exc}".strip()
                po.save(update_fields=["status", "note", "updated_at"])
        self.message_user(request, f"{sent} payout(s) sent.")

    @admin.action(description="Mark selected payouts as failed")
    def fail_payouts(self, request, queryset):
        queryset.filter(status=Payout.STATUS_PROCESSING).update(status=Payout.STATUS_FAILED, updated_at=timezone.now())

    @admin.action(description="Cancel selected payouts")
    def cancel_payouts(self, request, queryset):
        queryset.filter(status=Payout.STATUS_PROCESSING).update(status=Payout.STATUS_CANCELLED, updated_at=timezone.now())


@admin.register(CryptoAccount)
class CryptoAccountAdmin(admin.ModelAdmin):
    list_display = ("user", "coin", "address", "label", "is_primary", "is_platform", "created_at")
    list_filter = ("coin", "is_platform")
    search_fields = ("user__email", "address")


@admin.register(ReferralAward)
class ReferralAwardAdmin(admin.ModelAdmin):
    list_display = ("inviter", "user", "level", "percent", "amount", "coin", "status", "created_at")
    list_filter = ("level", "coin", "status")
    search_fields = ("inviter__email", "user__email")
    readonly_fields = ("user", "inviter", "level", "percent", "amount", "coin", "source_investment")


class PendingFilter(admin.SimpleListFilter):
    title = "Status"
    parameter_name = "kycstatus"

    def lookups(self, request, model_admin):
        return KYCSubmission.STATUS + (("any", "Any"),)

    def queryset(self, request, queryset):
        if self.value() in dict(KYCSubmission.STATUS):
            return queryset.filter(status=self.value())
        return queryset


@admin.register(KYCSubmission)
class KYCSubmissionAdmin(admin.ModelAdmin):
    list_display = ("user", "document_type", "status", "submitted_at", "reviewed_at")
    list_filter = (PendingFilter,)
    search_fields = ("user__email",)
    readonly_fields = ("user", "submitted_at")
    actions = ["approve_kyc", "reject_kyc"]

    @admin.action(description="Approve selected KYC submissions")
    def approve_kyc(self, request, queryset):
        for sub in queryset.filter(status=KYCSubmission.STATUS_PENDING):
            sub.status = KYCSubmission.STATUS_APPROVED
            sub.reviewed_at = timezone.now()
            sub.user.kyc_verified = True
            sub.user.kyc_rejected = False
            sub.user.save(update_fields=["kyc_verified", "kyc_rejected"])
            sub.save(update_fields=["status", "reviewed_at"])
        self.message_user(request, "KYC submissions approved.")

    @admin.action(description="Reject selected KYC submissions")
    def reject_kyc(self, request, queryset):
        for sub in queryset.filter(status=KYCSubmission.STATUS_PENDING):
            sub.status = KYCSubmission.STATUS_REJECTED
            sub.reviewed_at = timezone.now()
            sub.user.kyc_verified = False
            sub.user.kyc_rejected = True
            sub.user.save(update_fields=["kyc_verified", "kyc_rejected"])
            sub.save(update_fields=["status", "reviewed_at", "reason"])
        self.message_user(request, "KYC submissions rejected.")


DEFAULT_PLATFORM_SETTINGS = [
    (PlatformSettings.S_REFERRAL_L1, "1", "Referral award - level 1 (direct invite), % of investment"),
    (PlatformSettings.S_REFERRAL_L2, "0.5", "Referral award - level 2, % of investment"),
    (PlatformSettings.S_REFERRAL_L3, "0.25", "Referral award - level 3, % of investment"),
    (PlatformSettings.S_WITHDRAW_COOLDOWN_HOURS, "24", "Minimum hours between user withdrawals"),
    (PlatformSettings.S_PAYOUT_COOLDOWN_HOURS, "0", "Minimum hours between admin payouts to a user"),
    (PlatformSettings.S_KYC_REQUIRED_TO_INVEST, "0", "Require KYC before a user can invest (1/0)"),
    (PlatformSettings.S_KYC_REQUIRED_TO_WITHDRAW, "0", "Require KYC before a user can withdraw (1/0)"),
    (PlatformSettings.S_WITHDRAW_FEE_PERCENT, "1", "Network fee charged on withdrawal, % of amount"),
    (PlatformSettings.S_BONUS_PERCENT, "5", "Profit/seasonal bonus granted by admin, % of invested balance"),
    (PlatformSettings.S_MIN_WITHDRAWAL, "10", "Minimum withdrawal amount"),
    (PlatformSettings.S_PAYMENT_MODE, "simulate", "simulate | provider | manual"),
    (PlatformSettings.S_PAYMENT_PROVIDER_URL, "", "Gateway API base URL (CoinGate / NOWPayments / Binance Pay / Coinbase Commerce)"),
    (PlatformSettings.S_PAYMENT_PROVIDER_KEY, "", "Gateway API key / secret"),
    (PlatformSettings.S_PAYMENT_WEBHOOK_TOKEN, "dev-gateway-secret", "Shared secret signed into webhook callbacks (HMAC-SHA256)"),
]

admin.site.register(PriceSnapshot)


@admin.register(PlatformSettings)
class PlatformSettingsAdmin(admin.ModelAdmin):
    list_display = ("key", "value", "label")
    search_fields = ("key", "label")
    list_editable = ("value",)


from django.http import HttpResponse  # noqa: E402


def seed_platform_settings(modeladmin, request, queryset):
    count = 0
    for key, value, label in DEFAULT_PLATFORM_SETTINGS:
        obj, created = PlatformSettings.objects.get_or_create(key=key, defaults={"value": value, "label": label})
        if created:
            count += 1
    return HttpResponse(f"<script>alert('Created {count} setting(s)');history.back();</script>")


PlatformSettingsAdmin.actions = [seed_platform_settings]
seed_platform_settings.short_description = "Create default platform settings"