from decimal import Decimal, ROUND_DOWN

from django.db import transaction

from api.models import (
    PlatformSettings,
    ReferralAward,
    Wallet,
)


def referral_percent(level):
    key = {
        1: PlatformSettings.S_REFERRAL_L1,
        2: PlatformSettings.S_REFERRAL_L2,
        3: PlatformSettings.S_REFERRAL_L3,
    }[level]
    return Decimal(str(PlatformSettings.get_decimal(key, 0)))


@transaction.atomic
def distribute_referral_awards(investment):
    """Credit referral awards (3 layers) when an investment is confirmed.

    Awards are only credited once, on the invitee's first confirmed investment
    onward. Each ancestor of the investor gets a configurable percentage of the
    invested amount, added to their withdrawable (award) balance.
    """
    if not investment.user.referred_by:
        return

    inviter = investment.user.referred_by
    for level in (1, 2, 3):
        if not inviter or not inviter.is_active:
            break
        percent = referral_percent(level)
        if percent <= 0:
            inviter = inviter.referred_by
            continue
        amount = (investment.amount * percent / Decimal(100)).quantize(
            Decimal("0.00000001"), rounding=ROUND_DOWN
        )
        if amount <= 0:
            inviter = inviter.referred_by
            continue
        award = ReferralAward.objects.create(
            user=investment.user,
            inviter=inviter,
            level=level,
            percent=percent,
            amount=amount,
            coin=investment.coin,
            source_investment=investment,
        )
        wallet = Wallet.ensure(inviter, investment.coin)
        wallet.withdrawable_balance += amount
        wallet.save(update_fields=["withdrawable_balance", "updated_at"])
        inviter = inviter.referred_by