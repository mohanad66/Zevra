from decimal import Decimal, ROUND_DOWN

from django.db import transaction
from django.db.models import Count

from api.models import (
    Notification,
    PlatformSettings,
    ReferralAward,
    User,
    Wallet,
)


def referral_tree_counts(user):
    """Return {1: n, 2: n, 3: n} — number of people at each invite level.

    Level 1 are the user's direct invitees, level 2 are their invitees, and
    level 3 the next layer down.
    """
    l1_ids = list(user.referrals.values_list("id", flat=True))
    l2_ids = (
        list(User.objects.filter(referred_by_id__in=l1_ids).values_list("id", flat=True))
        if l1_ids
        else []
    )
    l3_count = (
        User.objects.filter(referred_by_id__in=l2_ids).count() if l2_ids else 0
    )
    return {1: len(l1_ids), 2: len(l2_ids), 3: l3_count}


def bulk_referral_counts(user_ids):
    """Return {user_id: {1,2,3}} counts for many users in three queries."""
    ids = list(set(user_ids))
    empty = {1: 0, 2: 0, 3: 0}
    result = {uid: dict(empty) for uid in ids}
    if not ids:
        return result

    l1 = {
        row["referred_by_id"]: row["count"]
        for row in User.objects.filter(referred_by_id__in=ids)
        .values("referred_by_id")
        .annotate(count=Count("id"))
    }
    l2 = {
        row["referred_by__referred_by_id"]: row["count"]
        for row in User.objects.filter(referred_by__referred_by_id__in=ids)
        .values("referred_by__referred_by_id")
        .annotate(count=Count("id"))
    }
    l3 = {
        row["referred_by__referred_by__referred_by_id"]: row["count"]
        for row in User.objects.filter(
            referred_by__referred_by__referred_by_id__in=ids
        )
        .values("referred_by__referred_by__referred_by_id")
        .annotate(count=Count("id"))
    }
    for uid in ids:
        result[uid] = {
            1: l1.get(uid, 0),
            2: l2.get(uid, 0),
            3: l3.get(uid, 0),
        }
    return result


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
        first_award_for_investor = not ReferralAward.objects.filter(
            inviter=inviter, user=investment.user
        ).exists()
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
        _notify_award(inviter, investment, award, first_award_for_investor)
        inviter = inviter.referred_by


def _notify_award(inviter, investment, award, first_award):
    name = investment.user.full_name or (investment.user.email or investment.user.phone or "investor")
    symbol = award.coin.symbol
    if first_award and award.level == 1:
        title = f"First referral award: {award.percent}% of {name}'s investment"
        title_ar = f"أول مكافأة إحالة: {award.percent}% من استثمار {name}"
        body = f"You earned {award.amount} {symbol} from {name}'s first investment."
        body_ar = f"حصلت على {award.amount} {symbol} من أول استثمار لـ {name}."
    else:
        title = f"Referral award: +{award.amount} {symbol} ({award.percent}%)"
        title_ar = f"مكافأة إحالة: +{award.amount} {symbol} ({award.percent}%)"
        body = f"Earned from {name}'s investment (Level {award.level})."
        body_ar = f"حصلت عليها من استثمار {name} (المستوى {award.level})."
    Notification.send(
        inviter,
        Notification.TYPE_AWARD,
        title=title,
        title_ar=title_ar,
        body=body,
        body_ar=body_ar,
        link="/referrals",
    )