"""
Make a user a support admin (or superuser), or remove the role.

  python manage.py set_admin <username or email>               # support admin (is_staff)
  python manage.py set_admin <username or email> --superuser   # also may grant/remove admins
  python manage.py set_admin <username or email> --remove      # back to a normal user

After the first superuser exists, more admins can be added from the web Admin screens.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q


class Command(BaseCommand):
    help = "Grant or remove the support admin role"

    def add_arguments(self, parser):
        parser.add_argument("identifier", help="Username or email")
        parser.add_argument("--superuser", action="store_true", help="Also make the user a superuser")
        parser.add_argument("--remove", action="store_true", help="Remove admin and superuser roles")

    def handle(self, *args, identifier, superuser, remove, **options):
        User = get_user_model()
        matches = list(User.objects.filter(Q(username__iexact=identifier) | Q(email__iexact=identifier))[:2])
        if not matches:
            raise CommandError(f"No user with username or email {identifier!r}.")
        if len(matches) > 1:
            raise CommandError(f"{identifier!r} matches several users; use the username.")
        user = matches[0]
        if remove:
            user.is_staff = False
            user.is_superuser = False
            role = "a normal user"
        else:
            user.is_staff = True
            user.is_superuser = user.is_superuser or superuser
            role = "a superuser" if user.is_superuser else "a support admin"
        user.save(update_fields=["is_staff", "is_superuser"])
        self.stdout.write(self.style.SUCCESS(f"{user.username} is now {role}."))
