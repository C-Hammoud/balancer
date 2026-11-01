from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ("budgeting", "0005_incomesource_default_for_expenses"),
    ]

    operations = [
        migrations.CreateModel(
            name="PersonalBudget",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("description", models.TextField(blank=True, default="")),
                ("currency", models.CharField(default="USD", max_length=3)),
                ("start_date", models.DateField(blank=True, null=True)),
                ("end_date", models.DateField(blank=True, null=True)),
                ("total_amount", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("active", "Active"),
                            ("completed", "Completed"),
                            ("archived", "Archived"),
                        ],
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("project_tag", models.CharField(blank=True, default="", max_length=80)),
                ("notes", models.TextField(blank=True, default="")),
                ("is_default", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="personal_budgets",
                        to="auth.user",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="PersonalBudgetCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("allocated_amount", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("order", models.PositiveSmallIntegerField(default=0)),
                ("notes", models.TextField(blank=True, default="")),
                (
                    "budget",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="categories",
                        to="budgeting.personalbudget",
                    ),
                ),
            ],
            options={"ordering": ["order", "name"], "verbose_name_plural": "Personal budget categories"},
        ),
        migrations.AddField(
            model_name="transaction",
            name="budget_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="transaction",
            name="budget_category_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddIndex(
            model_name="personalbudget",
            index=models.Index(fields=["user", "status"], name="budgeting_p_user_id_7a8b2a_idx"),
        ),
        migrations.AddIndex(
            model_name="personalbudget",
            index=models.Index(fields=["user", "name"], name="budgeting_p_user_id_name_idx"),
        ),
    ]
