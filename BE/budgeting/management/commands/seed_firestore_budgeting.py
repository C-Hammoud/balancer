"""
Seed default budgeting groups, categories, and expense-type maps.
Uses the active DATA_STORE (sqlite or firestore).
Run: python manage.py seed_firestore_budgeting
"""
from django.core.management.base import BaseCommand
from budgeting.store import GroupFS, CategoryFS, TypeCategoryMapFS


DEFAULT_GROUPS = [
    ("Home", 0),
    ("Food", 1),
    ("Transportation", 2),
    ("Utilities", 3),
    ("Health", 4),
    ("Other", 5),
]

DEFAULT_CATEGORIES = [
    # (name, group_name, include_in_reports, order)
    ("Rent / Mortgage", "Home", True, 0),
    ("Maintenance", "Home", True, 1),
    ("Groceries", "Food", True, 0),
    ("Restaurants", "Food", True, 1),
    ("Fuel", "Transportation", True, 0),
    ("Public transport", "Transportation", True, 1),
    ("Electricity", "Utilities", True, 0),
    ("Water", "Utilities", True, 1),
    ("Insurance", "Health", True, 0),
    ("Medical", "Health", True, 1),
    ("Other", "Other", True, 0),
]

# expense consumption_type → (category_name, group_name)
DEFAULT_TYPE_MAPS = [
    ("market", "Groceries", "Food"),
    ("food", "Restaurants", "Food"),
    ("transport", "Fuel", "Transportation"),
    ("other", "Other", "Other"),
]


class Command(BaseCommand):
    help = "Seed default budgeting groups, categories, and type maps (sqlite or firestore)"

    def handle(self, *args, **options):
        existing_groups = {g.name: g for g in GroupFS.list_all()}
        group_ids = {}
        for name, order in DEFAULT_GROUPS:
            if name in existing_groups:
                group_ids[name] = existing_groups[name].pk
                self.stdout.write(self.style.WARNING(f"Group already exists: {name}"))
                continue
            g = GroupFS(name=name, order=order)
            g.save()
            group_ids[name] = g.pk
            self.stdout.write(self.style.SUCCESS(f"Created group: {name}"))

        categories = CategoryFS.list_all()
        existing_cat_keys = {(c.name, c.group_id) for c in categories}
        cat_by_name_group = {(c.name, c.group_id): c for c in categories}

        for name, group_name, include_in_reports, order in DEFAULT_CATEGORIES:
            gid = group_ids.get(group_name)
            if not gid:
                self.stdout.write(self.style.ERROR(f"Group not found: {group_name}"))
                continue
            if (name, gid) in existing_cat_keys:
                self.stdout.write(self.style.WARNING(f"Category already exists: {name} ({group_name})"))
                continue
            c = CategoryFS(name=name, group_id=gid, include_in_reports=include_in_reports, order=order)
            c.save()
            existing_cat_keys.add((name, gid))
            cat_by_name_group[(name, gid)] = c
            self.stdout.write(self.style.SUCCESS(f"Created category: {name} ({group_name})"))

        # Refresh category lookup after creates
        categories = CategoryFS.list_all()
        cat_lookup = {}
        for c in categories:
            gname = next((n for n, gid in group_ids.items() if gid == c.group_id), "")
            cat_lookup[(c.name, gname)] = c.pk

        existing_global = {m.consumption_type: m for m in TypeCategoryMapFS.list_global()}
        for ctype, cat_name, group_name in DEFAULT_TYPE_MAPS:
            cat_id = cat_lookup.get((cat_name, group_name))
            if not cat_id:
                self.stdout.write(self.style.ERROR(f"Category not found for type map {ctype}: {cat_name}/{group_name}"))
                continue
            if ctype in existing_global:
                m = existing_global[ctype]
                if m.category_id != cat_id:
                    m.category_id = cat_id
                    m.save()
                    self.stdout.write(self.style.SUCCESS(f"Updated global type map: {ctype} -> {cat_name}"))
                else:
                    self.stdout.write(self.style.WARNING(f"Type map already exists: {ctype}"))
                continue
            TypeCategoryMapFS(user_id="", consumption_type=ctype, category_id=cat_id).save()
            self.stdout.write(self.style.SUCCESS(f"Created global type map: {ctype} -> {cat_name}"))

        from django.conf import settings
        self.stdout.write(self.style.SUCCESS(
            f"Done. Groups, categories, and type maps are in {settings.DATA_STORE}."
        ))
