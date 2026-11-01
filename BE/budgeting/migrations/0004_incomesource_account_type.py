from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("budgeting", "0003_data_store_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="incomesource",
            name="account_type",
            field=models.CharField(
                choices=[
                    ("bank", "Bank"),
                    ("credit_card", "Credit Card"),
                    ("wallet", "Wallet"),
                    ("other", "Other"),
                ],
                default="bank",
                max_length=20,
            ),
        ),
    ]
