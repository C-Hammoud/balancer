from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def mark_existing_users_verified(apps, schema_editor):
    User = apps.get_model("auth", "User")
    UserProfile = apps.get_model("api", "UserProfile")
    for user in User.objects.all().iterator():
        UserProfile.objects.get_or_create(
            user_id=user.pk,
            defaults={"email_verified": True},
        )


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("email_verified", models.BooleanField(default=False)),
                ("email_verified_at", models.DateTimeField(blank=True, null=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "User profile",
                "verbose_name_plural": "User profiles",
            },
        ),
        migrations.RunPython(mark_existing_users_verified, migrations.RunPython.noop),
    ]
