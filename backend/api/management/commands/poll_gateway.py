from django.core.management.base import BaseCommand

from api.services import reconcile_gateway


class Command(BaseCommand):
    help = "Poll PayRam for the final status of outstanding payments and withdrawals."

    def handle(self, *args, **options):
        paid_orders, transfers = reconcile_gateway()
        self.stdout.write(
            self.style.SUCCESS(
                f"reconcile done: {paid_orders} payment(s) confirmed, "
                f"{transfers} withdrawal(s)/payout(s) finalized."
            )
        )