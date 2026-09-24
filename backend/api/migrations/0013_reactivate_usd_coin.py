from django.db import migrations


def reactivate_usd_conis(apps, schema_editor):
    Coin = apps.get_model("api", "Coin")
    Coin.objects.filter(symbol__iexact="USD").update(is_active=True)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0012_deactivate_usd_coin"),
    ]

    operations = [
        migrations.RunPython(reactivate_usd_conis, noop),
    ]