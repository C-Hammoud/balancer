"""
Give every shared (ownerless) category group and subcategory to one user.

Categories created before per-user categories existed have no owner, so they became
read-only shared defaults. On a single-user install, run this once so that user can
edit them again:
  python manage.py claim_shared_categories --username alice
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from budgeting.store import CategoryFS, GroupFS


class Command(BaseCommand):
    help = "Assign all shared (ownerless) category groups and subcategories to one user"

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options["username"]).first()
        if not user:
            raise CommandError(f"User not found: {options['username']}")
        uid = str(user.pk)
        groups = [g for g in GroupFS.list_all(limit=5000) if not g.user_id]
        cats = [c for c in CategoryFS.list_all(limit=10000) if not c.user_id]
        if not options["dry_run"]:
            for obj in groups + cats:
                obj.user_id = uid
                obj.save()
        verb = "Would assign" if options["dry_run"] else "Assigned"
        self.stdout.write(
            self.style.SUCCESS(f"{verb} {len(groups)} group(s) and {len(cats)} subcategory(ies) to {user.username}.")
        )
