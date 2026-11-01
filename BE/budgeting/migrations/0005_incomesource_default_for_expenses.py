from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("budgeting", "0004_incomesource_account_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="incomesource",
            name="is_default_for_expenses",
            field=models.BooleanField(
                default=False,
                help_text="Pre-selected account when adding expense transactions",
            ),
        ),
    ]
