from django.db import migrations, models


def mark_existing_setup_complete(apps, schema_editor):
    UserProfile = apps.get_model("api", "UserProfile")
    IncomeSource = apps.get_model("budgeting", "IncomeSource")
    user_ids = set(IncomeSource.objects.values_list("user_id", flat=True))
    if not user_ids:
        return
    UserProfile.objects.filter(user_id__in=user_ids).update(setup_status="complete")


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0001_userprofile"),
        ("budgeting", "0005_incomesource_default_for_expenses"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="phone",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="setup_status",
            field=models.CharField(default="pending", max_length=20),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="setup_skipped_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="setup_completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="setup_nudge_push_due_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="setup_nudge_email_due_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="setup_nudge_push_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="setup_nudge_email_sent_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="notify_weekly_summaries",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="notify_low_balance",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="userprofile",
            name="notify_setup_nudges",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(mark_existing_setup_complete, migrations.RunPython.noop),
    ]
