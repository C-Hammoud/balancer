# Budgeting app initial migration (BRD data model)

import django.db.models.deletion
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Group",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80)),
                ("order", models.PositiveSmallIntegerField(default=0)),
            ],
            options={"ordering": ["order", "name"]},
        ),
        migrations.CreateModel(
            name="Category",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80)),
                ("include_in_reports", models.BooleanField(default=True, help_text="Include in expense totals and budget reports")),
                ("order", models.PositiveSmallIntegerField(default=0)),
                ("group", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="categories", to="budgeting.group")),
            ],
            options={"ordering": ["group", "order", "name"], "verbose_name_plural": "Categories"},
        ),
        migrations.CreateModel(
            name="Commitment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=200)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("start_date", models.DateField()),
                ("term_months", models.PositiveIntegerField(help_text="Term in months")),
                ("frequency", models.CharField(choices=[("monthly", "Monthly"), ("quarterly", "Quarterly"), ("yearly", "Yearly")], default="monthly", max_length=20)),
                ("payment_amount", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("balloon", models.DecimalField(decimal_places=2, default=Decimal("0"), help_text="Balloon payment at end if any", max_digits=14)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="budgeting_commitments", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["start_date"]},
        ),
        migrations.CreateModel(
            name="UploadTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100)),
                ("column_mapping", models.JSONField(default=dict, help_text='e.g. {"date": "A", "description": "B", "amount": "C"}')),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="budgeting_upload_templates", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="Transaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField()),
                ("month", models.CharField(db_index=True, max_length=7)),
                ("description", models.CharField(max_length=500)),
                ("classification", models.CharField(blank=True, choices=[("fixed", "Fixed"), ("variable", "Variable")], max_length=20, null=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("direction", models.CharField(choices=[("income", "Income"), ("expense", "Expense"), ("transfer", "Transfer")], max_length=20)),
                ("source_account", models.CharField(blank=True, max_length=100)),
                ("external_id", models.CharField(blank=True, db_index=True, help_text="Bank transaction id for deduplication", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="transactions", to="budgeting.category")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="budgeting_transactions", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-date", "-id"]},
        ),
        migrations.CreateModel(
            name="MerchantCategoryLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("keyword", models.CharField(db_index=True, max_length=120)),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="merchant_links", to="budgeting.category")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="budgeting_merchant_links", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["keyword"], "unique_together": {("keyword", "category")}},
        ),
        migrations.CreateModel(
            name="FinancialStanding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("snapshot_date", models.DateField()),
                ("total_assets", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("current_assets", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("fixed_assets", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("total_liabilities", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("short_term_liabilities", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("long_term_liabilities", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="budgeting_financial_standings", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-snapshot_date"]},
        ),
        migrations.CreateModel(
            name="Savings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("year", models.PositiveIntegerField()),
                ("month", models.PositiveSmallIntegerField()),
                ("actual", models.DecimalField(blank=True, decimal_places=2, help_text="Actual savings (income - expenses - commitments)", max_digits=14, null=True)),
                ("target", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("goal_status", models.CharField(choices=[("met", "Met"), ("missed", "Missed"), ("pending", "Pending")], default="pending", max_length=20)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="budgeting_savings", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-year", "-month"], "unique_together": {("user", "year", "month")}},
        ),
        migrations.CreateModel(
            name="CommitmentScheduleLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("due_date", models.DateField()),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("status", models.CharField(choices=[("paid", "Paid"), ("outstanding", "Outstanding")], default="outstanding", max_length=20)),
                ("sequence", models.PositiveSmallIntegerField(default=0)),
                ("commitment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="schedule_lines", to="budgeting.commitment")),
            ],
            options={"ordering": ["commitment", "due_date"]},
        ),
        migrations.CreateModel(
            name="Budget",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("year", models.PositiveIntegerField()),
                ("month", models.PositiveSmallIntegerField()),
                ("forecast", models.DecimalField(decimal_places=2, default=Decimal("0"), max_digits=14)),
                ("category", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="budgets", to="budgeting.category")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="budgeting_budgets", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["year", "month", "category"], "unique_together": {("user", "category", "year", "month")}},
        ),
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(fields=["user", "month"], name="budgeting_t_user_id_0b0a0d_idx"),
        ),
        migrations.AddIndex(
            model_name="transaction",
            index=models.Index(fields=["user", "date"], name="budgeting_t_user_id_0c1b1e_idx"),
        ),
    ]
