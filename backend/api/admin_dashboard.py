"""Custom Django-admin analytics dashboards.

Two pages, both staff-only (wrapped by ``admin.site.admin_view``):

* ``payments_dashboard``      — real (provider-confirmed) payments, growth,
                                live/online users and their latest activity.
* ``balance_edits_dashboard`` — wallets whose balances were edited vs really
                                paid, who edited them and most-edited users.
"""
from datetime import timedelta

from django.contrib import admin
from django.db.models import Count, Sum
from django.db.models.functions import Abs, TruncDate
from django.shortcuts import render
from django.utils import timezone

from api.models import (
    ActivityLog,
    BalanceAudit,
    Coin,
    PaymentOrder,
    User,
    Wallet,
    Withdrawal,
)

ONLINE_WINDOW = timedelta(seconds=300)
GROWTH_DAYS = 14


def _sum(qs, field="amount"):
    return qs.aggregate(t=Sum(field))["t"] or 0


def _real_payments():
    """Paid orders that actually went through the provider (Plisio)."""
    return PaymentOrder.objects.filter(
        status=PaymentOrder.STATUS_PAID, provider_order_id__gt=""
    )


def _paid_payments():
    return PaymentOrder.objects.filter(status=PaymentOrder.STATUS_PAID)


def _growth_series(now):
    """Per-day new users + real payments over the last GROWTH_DAYS days."""
    start = timezone.localdate(now) - timedelta(days=GROWTH_DAYS - 1)
    users = {
        row["d"]: row["c"]
        for row in User.objects.annotate(d=TruncDate("created_at"))
        .filter(d__gte=start)
        .values("d")
        .annotate(c=Count("id"))
    }
    paid = {
        row["d"]: row
        for row in _real_payments()
        .annotate(d=TruncDate("created_at"))
        .filter(d__gte=start)
        .values("d")
        .annotate(c=Count("id"), s=Sum("amount"))
    }
    series = []
    for i in range(GROWTH_DAYS):
        day = start + timedelta(days=i)
        p = paid.get(day)
        series.append(
            {
                "date": day,
                "new_users": users.get(day, 0),
                "payments": p["c"] if p else 0,
                "amount": (p["s"] if p else 0) or 0,
            }
        )
    return series


@admin.site.admin_view
def payments_dashboard(request):
    now = timezone.now()
    today = timezone.localdate(now)
    real = _real_payments()
    paid = _paid_payments()

    def windowed(qs, days):
        return qs.filter(created_at__date__gte=today - timedelta(days=days - 1))

    total_invested = Wallet.objects.aggregate(t=Sum("invested_balance"))["t"] or 0
    total_withdrawable = Wallet.objects.aggregate(t=Sum("withdrawable_balance"))["t"] or 0

    recent_payments = (
        real.select_related("user", "coin")
        .order_by("-created_at")[:50]
    )
    by_coin = (
        real.values("coin__symbol", "coin__name")
        .annotate(count=Count("id"), total=Sum("amount"))
        .order_by("-total", "-count")[:20]
    )
    top_payers = (
        real.values("user_id", "user__email", "user__first_name", "user__last_name")
        .annotate(count=Count("id"), total=Sum("amount"))
        .order_by("-total")[:20]
    )
    online_cutoff = now - ONLINE_WINDOW
    live_users = (
        User.objects.filter(last_seen__gte=online_cutoff)
        .order_by("-last_seen")[:100]
    )
    recent_seen = (
        User.objects.filter(last_seen__isnull=False)
        .order_by("-last_seen")[:60]
    )
    activity_feed = (
        ActivityLog.objects.select_related("user").order_by("-created_at")[:80]
    )

    growth = _growth_series(now)
    context = {
        **admin.site.each_context(request),
        "title": "Payments & Live Activity",
        "now": now,
        "online_count": live_users.count(),
        "kpi": {
            "real_count": real.count(),
            "real_total": _sum(real),
            "real_today": _sum(windowed(real, 1)),
            "real_7d": _sum(windowed(real, 7)),
            "real_30d": _sum(windowed(real, 30)),
            "paid_all_count": paid.count(),
            "pending_count": PaymentOrder.objects.filter(
                status=PaymentOrder.STATUS_PENDING
            ).count(),
            "users_total": User.objects.count(),
            "users_new_today": User.objects.filter(created_at__date=today).count(),
            "users_new_7d": User.objects.filter(
                created_at__date__gte=today - timedelta(days=6)
            ).count(),
            "users_new_30d": User.objects.filter(
                created_at__date__gte=today - timedelta(days=29)
            ).count(),
            "total_invested": total_invested,
            "total_withdrawable": total_withdrawable,
            "withdrawals_paid": _sum(
                Withdrawal.objects.filter(status=Withdrawal.STATUS_COMPLETED)
            ),
            "withdrawals_paid_count": Withdrawal.objects.filter(
                status=Withdrawal.STATUS_COMPLETED
            ).count(),
        },
        "growth": growth,
        "growth_max": max(
            [max(s["new_users"], s["payments"]) for s in growth] or [1]
        )
        or 1,
        "recent_payments": recent_payments,
        "by_coin": by_coin,
        "top_payers": top_payers,
        "live_users": live_users,
        "recent_seen": recent_seen,
        "activity_feed": activity_feed,
        "online_cutoff": online_cutoff,
    }
    return render(request, "admin/dashboard_payments.html", context)


@admin.site.admin_view
def balance_edits_dashboard(request):
    now = timezone.now()
    edited_sources = list(BalanceAudit.EDITED_SOURCES)
    edits = BalanceAudit.objects.filter(source__in=edited_sources)
    real = _real_payments()

    total_edited_amount = edits.aggregate(t=Sum(Abs("delta")))["t"] or 0
    real_total = _sum(real)

    top_edited = (
        edits.values("user_id", "user__email", "user__first_name", "user__last_name")
        .annotate(count=Count("id"), total=Sum(Abs("delta")))
        .order_by("-count", "-total")[:25]
    )
    # Attach each user's most recent edit timestamp (Sum can't produce it).
    latest_rows = []
    for row in top_edited:
        last_row = (
            edits.filter(user_id=row["user_id"])
            .order_by("-created_at")
            .values("created_at")
            .first()
        )
        latest_rows.append(
            {**row, "last_at": last_row["created_at"] if last_row else None}
        )

    recent_edits = (
        edits.select_related("user", "actor", "coin").order_by("-created_at")[:100]
    )
    source_labels = dict(BalanceAudit.SOURCE_CHOICES)
    by_source = [
        {**row, "label": source_labels.get(row["source"], row["source"])}
        for row in edits.values("source")
        .annotate(count=Count("id"), total=Sum(Abs("delta")))
        .order_by("-count")
    ]
    edited_users_count = edits.values("user_id").distinct().count()

    context = {
        **admin.site.each_context(request),
        "title": "Balance Edits",
        "now": now,
        "kpi": {
            "edit_count": edits.count(),
            "edited_users": edited_users_count,
            "edited_total": total_edited_amount,
            "real_total": real_total,
            "real_count": real.count(),
            "coins": Coin.objects.count(),
        },
        "top_edited": latest_rows,
        "recent_edits": recent_edits,
        "by_source": by_source,
    }
    return render(request, "admin/dashboard_balance_edits.html", context)
