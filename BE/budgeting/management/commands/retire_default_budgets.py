"""
Archive every user's automatic "Monthly Expenses" budget (the plan's main budget replaces it) and
untag its transactions. This also happens on its own the next time each user opens their budgets.

  python manage.py retire_default_budgets
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from budgeting.personal_budget_service import retire_default_budget


class Command(BaseCommand):
    help = "Archive the automatic default personal budget of every user"

    def handle(self, *args, **options):
        retired = sum(1 for user in get_user_model().objects.all() if retire_default_budget(user))
        self.stdout.write(self.style.SUCCESS(f"Archived {retired} default budget(s)."))
