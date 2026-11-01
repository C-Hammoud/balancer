from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("budgeting", "0009_personal_budget_invite"),
    ]

    operations = [
        migrations.AddField(
            model_name="personalbudgetcategory",
            name="group_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="personalbudgetcategory",
            name="category_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="personalbudgetcategory",
            name="parent_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
