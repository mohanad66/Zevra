from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from datetime import datetime, timedelta, time as dt_time, timezone as dt_timezone

from api.models import Coin, PayoutWindow, User, Wallet, sync_payout_windows


class PayoutWindowClaimTests(TestCase):
    def setUp(self):
        self.coin = Coin.objects.create(name="Tether", symbol="USDT", is_active=True)
        self.user = User.objects.create_user(email="claimer@example.com", password="pass12345")
        wallet = Wallet.ensure(self.user, self.coin)
        wallet.invested_balance = Decimal("100")
        wallet.save(update_fields=["invested_balance"])

    def _open_window(self):
        window = PayoutWindow.objects.create(
            title="Daily payout",
            percent=Decimal("10"),
            duration_hours=1,
            target_mode=PayoutWindow.TARGET_ALL,
        )
        window.activate()
        window.refresh_from_db()
        return window

    def test_user_can_claim_once_per_open(self):
        window = self._open_window()
        ok, _, grants = window.grant_to(self.user)
        self.assertTrue(ok)
        self.assertEqual(len(grants), 1)

        ok2, message, _ = window.grant_to(self.user)
        self.assertFalse(ok2)
        self.assertIn("already claimed", message.lower())

    def test_reopening_after_close_allows_claiming_again(self):
        window = self._open_window()
        self.assertTrue(window.grant_to(self.user)[0])

        window.close()
        window.refresh_from_db()
        self.assertFalse(window.is_active)

        window.activate()
        window.refresh_from_db()
        self.assertFalse(window.claimed_by.filter(pk=self.user.pk).exists())

        ok, _, grants = window.grant_to(self.user)
        self.assertTrue(ok)
        self.assertEqual(len(grants), 1)

    def test_reopening_after_expiry_allows_claiming_again(self):
        window = self._open_window()
        self.assertTrue(window.grant_to(self.user)[0])

        window.ends_at = timezone.now() - timedelta(hours=1)
        window.save(update_fields=["ends_at"])
        self.assertFalse(window.is_open)

        window.activate()
        window.refresh_from_db()
        self.assertFalse(window.claimed_by.filter(pk=self.user.pk).exists())

    def test_reactivating_open_window_keeps_claims(self):
        window = self._open_window()
        self.assertTrue(window.grant_to(self.user)[0])

        window.activate()
        window.refresh_from_db()
        self.assertTrue(window.claimed_by.filter(pk=self.user.pk).exists())

        ok, message, _ = window.grant_to(self.user)
        self.assertFalse(ok)
        self.assertIn("already claimed", message.lower())


class PayoutWindowScheduleTests(TestCase):
    def setUp(self):
        Coin.objects.create(name="Tether", symbol="USDT", is_active=True)
        self.user = User.objects.create_user(email="sched@example.com", password="pass12345")

    def _auto_window(self, **kwargs):
        defaults = dict(
            title="Auto",
            percent=Decimal("5"),
            mode=PayoutWindow.MODE_AUTOMATIC,
            frequency=PayoutWindow.FREQ_DAILY,
            open_time=dt_time(10, 0),
            close_time=dt_time(12, 0),
        )
        defaults.update(kwargs)
        return PayoutWindow.objects.create(**defaults)

    def test_manual_windows_have_no_occurrence(self):
        window = PayoutWindow.objects.create(title="Manual", percent=Decimal("5"))
        self.assertIsNone(window.current_occurrence())

    def test_daily_occurrence_inside_and_outside(self):
        window = self._auto_window()
        inside = datetime(2026, 5, 1, 11, 0, tzinfo=dt_timezone.utc)
        outside = datetime(2026, 5, 1, 9, 0, tzinfo=dt_timezone.utc)
        self.assertIsNotNone(window.current_occurrence(inside))
        self.assertIsNone(window.current_occurrence(outside))

    def test_overnight_occurrence_spans_midnight(self):
        window = self._auto_window(open_time=dt_time(23, 0), close_time=dt_time(1, 0))
        after_midnight = datetime(2026, 5, 2, 0, 30, tzinfo=dt_timezone.utc)
        occurrence = window.current_occurrence(after_midnight)
        self.assertIsNotNone(occurrence)
        start, end = occurrence
        self.assertEqual(start, datetime(2026, 5, 1, 23, 0, tzinfo=dt_timezone.utc))
        self.assertEqual(end, datetime(2026, 5, 2, 1, 0, tzinfo=dt_timezone.utc))

    def test_weekly_occurrence_only_on_selected_weekday(self):
        base = datetime(2026, 5, 1, 12, 0, tzinfo=dt_timezone.utc)
        window = self._auto_window(
            frequency=PayoutWindow.FREQ_WEEKLY,
            weekday=base.weekday(),
            open_time=dt_time(0, 0),
            close_time=dt_time(23, 59),
        )
        self.assertIsNotNone(window.current_occurrence(base))
        self.assertIsNone(window.current_occurrence(base + timedelta(days=1)))

    def test_monthly_occurrence_uses_day_of_month(self):
        window = self._auto_window(
            frequency=PayoutWindow.FREQ_MONTHLY,
            day_of_month=15,
            open_time=dt_time(0, 0),
            close_time=dt_time(23, 59),
        )
        on_day = datetime(2026, 5, 15, 12, 0, tzinfo=dt_timezone.utc)
        off_day = datetime(2026, 5, 16, 12, 0, tzinfo=dt_timezone.utc)
        self.assertIsNotNone(window.current_occurrence(on_day))
        self.assertIsNone(window.current_occurrence(off_day))

    def test_sync_opens_window_within_occurrence(self):
        window = self._auto_window()
        now = datetime(2026, 5, 1, 11, 0, tzinfo=dt_timezone.utc)
        opened = sync_payout_windows(now)
        window.refresh_from_db()
        self.assertIn("Auto", opened)
        self.assertTrue(window.is_active)
        self.assertEqual(window.opens_at, datetime(2026, 5, 1, 10, 0, tzinfo=dt_timezone.utc))
        self.assertEqual(window.ends_at, datetime(2026, 5, 1, 12, 0, tzinfo=dt_timezone.utc))

    def test_sync_closes_window_outside_occurrence(self):
        window = self._auto_window()
        sync_payout_windows(datetime(2026, 5, 1, 11, 0, tzinfo=dt_timezone.utc))
        sync_payout_windows(datetime(2026, 5, 1, 13, 0, tzinfo=dt_timezone.utc))
        window.refresh_from_db()
        self.assertFalse(window.is_active)

    def test_sync_clears_claims_once_per_occurrence(self):
        window = self._auto_window()
        window.claimed_by.add(self.user)
        # Opening a fresh occurrence clears prior claims...
        sync_payout_windows(datetime(2026, 5, 1, 11, 0, tzinfo=dt_timezone.utc))
        window.refresh_from_db()
        self.assertFalse(window.claimed_by.filter(pk=self.user.pk).exists())
        # ...but repeat syncs inside the same occurrence keep them.
        window.claimed_by.add(self.user)
        sync_payout_windows(datetime(2026, 5, 1, 11, 30, tzinfo=dt_timezone.utc))
        window.refresh_from_db()
        self.assertTrue(window.claimed_by.filter(pk=self.user.pk).exists())

    def test_sync_keeps_only_one_window_active(self):
        first = self._auto_window(title="First")
        second = self._auto_window(title="Second")
        sync_payout_windows(datetime(2026, 5, 1, 11, 0, tzinfo=dt_timezone.utc))
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertNotEqual(first.is_active, second.is_active)
        self.assertEqual(
            PayoutWindow.objects.filter(is_active=True).count(), 1
        )
        self.assertTrue(sync_payout_windows(datetime(2026, 5, 1, 11, 5, tzinfo=dt_timezone.utc)) == [])
