from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from api.admin import DEFAULT_PLATFORM_SETTINGS
from api.models import Coin, PlatformSettings

User = get_user_model()


class Command(BaseCommand):
    help = "Seed default platform settings, sample coins and an admin account."

    def add_arguments(self, parser):
        parser.add_argument("--admin-email", default=None)
        parser.add_argument("--admin-password", default=None)

    def handle(self, *args, **options):
        # Platform settings
        created_settings = 0
        for key, value, label in DEFAULT_PLATFORM_SETTINGS:
            _, created = PlatformSettings.objects.get_or_create(
                key=key, defaults={"value": value, "label": label}
            )
            if created:
                created_settings += 1
        self.stdout.write(self.style.SUCCESS(f"Platform settings: {created_settings} created."))

        # Sample stable & liquid coins (admins can add/edit/remove these in the admin panel)
        sample_coins = [
            ("Tether USD", "USDT", "TRC20", "1.0", True),
            ("USD Coin", "USDC", "TRC20", "1.0", True),
            ("USD", "USD", "TRC20", "1.0", True),
            ("Dai", "DAI", "ERC20", "1.0", True),
            ("Toncoin", "TON", "TON", "5.5", False),
            ("Solana", "SOL", "SOL", "140.0", False),
            ("Bitcoin", "BTC", "ERC20", "64000.0", False),
        ]
        for name, symbol, chain, price, stable in sample_coins:
            coin, created = Coin.objects.update_or_create(
                symbol=symbol,
                defaults={
                    "name": name,
                    "chain": chain,
                    "reference_price": price,
                    "is_stable": stable,
                },
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f"Coin created: {name} ({symbol})"))

        # Admin user
        email = options["admin_email"] or "admin@miyartrading.com"
        password = options["admin_password"] or "admin123"
        if not User.objects.filter(email=email).exists():
            User.objects.create_superuser(username=email, email=email, password=password)
            self.stdout.write(self.style.SUCCESS(f"Admin created: {email} / {password}"))
        else:
            self.stdout.write(f"Admin already exists: {email}")

        self.stdout.write(self.style.SUCCESS("Seed complete."))