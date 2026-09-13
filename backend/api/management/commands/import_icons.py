"""Download coin logos from CoinGecko and store them on the Coin models.

Usage:
    python manage.py import_icons

The stored files land in media/coins/ and are served through the Coin
serializer's ``icon_url`` field, so the market/wallet/ invest pages render
real logos instead of letter fallbacks.
"""
import io

import requests
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from api.models import Coin

# symbol -> CoinGecko id (https://api.coingecko.com/api/v3/coins/list)
COINGECKO_IDS = {
    "USDT": "tether",
    "USDC": "usd-coin",
    "USD": "usd",
    "DAI": "dai",
    "TON": "the-open-network",
    "SOL": "solana",
    "BTC": "bitcoin",
}


class Command(BaseCommand):
    help = "Fetch coin logos from CoinGecko and attach them to Coin rows."

    def handle(self, *args, **options):
        ids = ",".join(COINGECKO_IDS.values())
        url = f"https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={ids}"
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:
            self.stderr.write(self.style.ERROR(f"CoinGecko request failed: {exc}"))
            return

        image_by_id = {item["id"]: item["image"] for item in resp.json()}
        done, skipped = 0, 0
        for symbol, cg_id in COINGECKO_IDS.items():
            coin = Coin.objects.filter(symbol=symbol).first()
            image_url = image_by_id.get(cg_id)
            if not coin or not image_url:
                skipped += 1
                continue
            try:
                img_resp = requests.get(image_url, timeout=20)
                img_resp.raise_for_status()
                ext = "png" if ".png" in image_url.split("?")[0] else "png"
                coin.icon.save(
                    f"{symbol.lower()}.{ext}",
                    ContentFile(img_resp.content),
                    save=True,
                )
                done += 1
                self.stdout.write(self.style.SUCCESS(f"Icon saved: {symbol}"))
            except requests.RequestException as exc:
                skipped += 1
                self.stderr.write(self.style.WARNING(f"Icon failed for {symbol}: {exc}"))

        self.stdout.write(
            self.style.SUCCESS(f"Done: {done} icons saved, {skipped} skipped.")
        )