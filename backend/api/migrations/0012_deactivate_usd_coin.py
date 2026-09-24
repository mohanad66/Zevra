from django.db import migrations


def deactivate_usd_conis(apps, schema_editor):
    Coin = apps.get_model("api", "Coin")
    Coin.objects.filter(symbol__iexact="USD").update(is_active=False)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0011_investment_api_investm_status_a80ff4_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(deactivate_usd_conis, noop),
    ]