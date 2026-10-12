from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from api.models import Coin, PayoutWindow, User, Wallet


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
