"""
Budgeting Application — Data model per BRD.
Entities: Transaction, Category, Group, Budget, Savings, Commitment, FinancialStanding, reference LOVs.
"""
from django.db import models
from django.conf import settings
from decimal import Decimal


class Group(models.Model):
    """Category group (e.g. Home, Food, Transportation). user=None is a shared default."""
    name = models.CharField(max_length=80)
    order = models.PositiveSmallIntegerField(default=0)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="budget_groups",
    )

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class Category(models.Model):
    """Category belonging to a Group; include_in_reports controls reporting. user=None is shared."""
    name = models.CharField(max_length=80)
    group = models.ForeignKey(Group, on_delete=models.PROTECT, related_name="categories")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="budget_categories",
    )
    include_in_reports = models.BooleanField(
        default=True,
        help_text="Include in expense totals and budget reports",
    )
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["group", "order", "name"]
        verbose_name_plural = "Categories"

    def __str__(self):
        return f"{self.group.name} — {self.name}"


class Classification(models.TextChoices):
    FIXED = "fixed", "Fixed"
    VARIABLE = "variable", "Variable"


class AccountType(models.TextChoices):
    BANK = "bank", "Bank"
    CREDIT_CARD = "credit_card", "Credit Card"
    WALLET = "wallet", "Wallet"
    OTHER = "other", "Other"


class Direction(models.TextChoices):
    INCOME = "income", "Income"
    EXPENSE = "expense", "Expense"
    TRANSFER = "transfer", "Transfer"


class TransactionStatus(models.TextChoices):
    SETTLED = "settled", "Settled"
    PENDING = "pending", "Pending"


class Frequency(models.TextChoices):
    MONTHLY = "monthly", "Monthly"
    QUARTERLY = "quarterly", "Quarterly"
    YEARLY = "yearly", "Yearly"


class Transaction(models.Model):
    """
    Bank/credit transaction: date, description, category, amount, direction.
    Transfers are excluded from expense totals.
    """
    date = models.DateField()
    month = models.CharField(max_length=7, db_index=True)  # YYYY-MM
    description = models.CharField(max_length=500)
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    classification = models.CharField(
        max_length=20,
        choices=Classification.choices,
        null=True,
        blank=True,
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    direction = models.CharField(max_length=20, choices=Direction.choices)
    currency = models.CharField(max_length=3, default="USD")
    note = models.TextField(blank=True, default="")
    time = models.CharField(max_length=8, blank=True, default="")
    income_source_id = models.CharField(max_length=64, blank=True, default="")
    commitment_id = models.CharField(max_length=64, blank=True, default="")
    schedule_line_id = models.CharField(max_length=64, blank=True, default="")
    include_in_utilization = models.BooleanField(default=False)
    budget_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    budget_category_id = models.CharField(max_length=64, blank=True, default="")
    # Transfers: destination account (one row moves money from income_source_id to here).
    # Empty on legacy transfers, which were stored as two rows ("Transfer to/from ...").
    to_account_id = models.CharField(max_length=64, blank=True, default="")
    # pending: authorised but not posted yet. Pending expenses count as spent; pending income
    # does not count until settled.
    status = models.CharField(max_length=16, choices=TransactionStatus.choices, default=TransactionStatus.SETTLED)
    source_account = models.CharField(max_length=100, blank=True)
    external_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text="Bank transaction id for deduplication",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="budgeting_transactions",
    )

    class Meta:
        ordering = ["-date", "-id"]
        indexes = [
            models.Index(fields=["user", "month"]),
            models.Index(fields=["user", "date"]),
        ]

    def __str__(self):
        return f"{self.date} {self.description[:40]} {self.amount} {self.direction}"


class MerchantCategoryLink(models.Model):
    """Keyword → Category mapping for automatic transaction classification."""
    keyword = models.CharField(max_length=120, db_index=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="merchant_links")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="budgeting_merchant_links",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["keyword"]
        unique_together = [["keyword", "category"]]

    def __str__(self):
        return f"{self.keyword} → {self.category.name}"


class Budget(models.Model):
    """Forecast amount per category or parent group per month/year."""
    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="group_budgets",
        null=True,
        blank=True,
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="budgets",
        null=True,
        blank=True,
    )
    year = models.PositiveIntegerField()
    month = models.PositiveSmallIntegerField()  # 1–12
    forecast = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="budgeting_budgets",
    )

    class Meta:
        ordering = ["year", "month", "category"]
        # Uniqueness enforced in store layer (group vs subcategory budgets)

    def __str__(self):
        return f"{self.category.name} {self.year}-{self.month:02d} = {self.forecast}"


class GoalStatus(models.TextChoices):
    MET = "met", "Met"
    MISSED = "missed", "Missed"
    PENDING = "pending", "Pending"


class Savings(models.Model):
    """Monthly saving: actual (derived or manual), target, goal status."""
    year = models.PositiveIntegerField()
    month = models.PositiveSmallIntegerField()
    actual = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Actual savings (income - expenses - commitments)",
    )
    target = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    goal_status = models.CharField(
        max_length=20,
        choices=GoalStatus.choices,
        default=GoalStatus.PENDING,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="budgeting_savings",
    )

    class Meta:
        ordering = ["-year", "-month"]
        unique_together = [["user", "year", "month"]]

    def __str__(self):
        return f"{self.year}-{self.month:02d} target={self.target} actual={self.actual} ({self.goal_status})"


class Commitment(models.Model):
    """Loan/commitment: amount, start, term, frequency, payment, balloon."""
    name = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    start_date = models.DateField()
    term_months = models.PositiveIntegerField(help_text="Term in months")
    frequency = models.CharField(max_length=20, choices=Frequency.choices, default=Frequency.MONTHLY)
    payment_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    balloon = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Balloon payment at end if any",
    )
    currency = models.CharField(max_length=3, default="USD")
    reminder_enabled = models.BooleanField(default=True)
    reminder_days_before = models.PositiveSmallIntegerField(default=3)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="budgeting_commitments",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_date"]

    def __str__(self):
        return f"{self.name} — {self.amount}"


class CommitmentScheduleLine(models.Model):
    """Single line in a loan schedule: due date, amount, status."""
    class ScheduleStatus(models.TextChoices):
        PAID = "paid", "Paid"
        OUTSTANDING = "outstanding", "Outstanding"

    commitment = models.ForeignKey(
        Commitment,
        on_delete=models.CASCADE,
        related_name="schedule_lines",
    )
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(
        max_length=20,
        choices=ScheduleStatus.choices,
        default=ScheduleStatus.OUTSTANDING,
    )
    sequence = models.PositiveSmallIntegerField(default=0)
    paid_date = models.DateField(null=True, blank=True)
    reminder_sent = models.BooleanField(default=False)

    class Meta:
        ordering = ["commitment", "due_date"]

    def __str__(self):
        return f"{self.commitment.name} {self.due_date} {self.amount} ({self.status})"


class FinancialStanding(models.Model):
    """Snapshot of assets and liabilities."""
    snapshot_date = models.DateField()
    total_assets = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    current_assets = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    fixed_assets = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total_liabilities = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    short_term_liabilities = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    long_term_liabilities = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    notes = models.TextField(blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="budgeting_financial_standings",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-snapshot_date"]

    def __str__(self):
        return f"Standing {self.snapshot_date} A={self.total_assets} L={self.total_liabilities}"


class UploadTemplate(models.Model):
    """Saved column mapping for CSV/XLS bank statement import."""
    name = models.CharField(max_length=100)
    column_mapping = models.JSONField(
        default=dict,
        help_text="e.g. {\"date\": \"A\", \"description\": \"B\", \"amount\": \"C\"}",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="budgeting_upload_templates",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class TypeCategoryMap(models.Model):
    """Maps expense consumption_type to a budgeting category. user null = global default."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="type_category_maps",
        null=True,
        blank=True,
    )
    consumption_type = models.CharField(max_length=32, default="other")
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="type_maps")

    class Meta:
        ordering = ["consumption_type"]


class BudgetThreshold(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="budget_thresholds",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="thresholds",
        null=True,
        blank=True,
    )
    warn_pct = models.DecimalField(max_digits=5, decimal_places=1, default=Decimal("80"))
    critical_pct = models.DecimalField(max_digits=5, decimal_places=1, default=Decimal("100"))
    email_enabled = models.BooleanField(default=True)

    class Meta:
        ordering = ["category_id"]


class IncomeSource(models.Model):
    """Financial account (bank, card, wallet) used on transactions."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="income_sources",
    )
    name = models.CharField(max_length=120)
    account_type = models.CharField(
        max_length=20,
        choices=AccountType.choices,
        default=AccountType.BANK,
    )
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_default_for_expenses = models.BooleanField(
        default=False,
        help_text="Pre-selected account when adding expense transactions",
    )

    class Meta:
        ordering = ["order", "name"]


class BudgetAlert(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="budget_alerts",
    )
    year = models.PositiveIntegerField()
    month = models.PositiveSmallIntegerField()
    category_id = models.CharField(max_length=120, blank=True, default="")
    severity = models.CharField(max_length=20, default="WARN")
    title = models.CharField(max_length=200, blank=True, default="")
    description = models.TextField(blank=True, default="")
    alert_type = models.CharField(max_length=32, default="utilization")
    utilization_pct = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    actual = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    forecast = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    commitment_id = models.CharField(max_length=64, blank=True, default="")
    schedule_line_id = models.CharField(max_length=64, blank=True, default="")
    due_date = models.CharField(max_length=32, blank=True, default="")
    commitment_name = models.CharField(max_length=200, blank=True, default="")
    is_resolved = models.BooleanField(default=False)
    # "user" = dismissed by the user (stays resolved while the condition holds);
    # "auto" = condition cleared during re-evaluation (reopens if it returns).
    resolution = models.CharField(max_length=16, blank=True, default="")
    resolved_at = models.DateTimeField(null=True, blank=True)
    snoozed_until = models.DateTimeField(null=True, blank=True)
    email_sent = models.BooleanField(default=False)
    fingerprint = models.CharField(max_length=255, blank=True, default="", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class PersonalBudgetStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"
    ARCHIVED = "archived", "Archived"


class PersonalBudget(models.Model):
    """
    User-owned financial plan (e.g. Vacation, Home Renovation).
    Distinct from monthly Budget forecast lines.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="personal_budgets",
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    currency = models.CharField(max_length=3, default="USD")
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    status = models.CharField(
        max_length=20,
        choices=PersonalBudgetStatus.choices,
        default=PersonalBudgetStatus.DRAFT,
    )
    project_tag = models.CharField(max_length=80, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    is_default = models.BooleanField(default=False)
    # Sub-budget of the monthly plan (e.g. a trip): its money is reserved in the plan and expenses
    # tagged to it count only here, not in the regular category budgets.
    in_plan = models.BooleanField(default=False)
    # Reserve total_amount over funding_months months starting at funding_start (first of a month).
    funding_start = models.DateField(null=True, blank=True)
    funding_months = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["user", "name"]),
        ]

    def __str__(self):
        return self.name


class PersonalBudgetCategory(models.Model):
    """Category line within a personal budget (Accommodation, Flights, …)."""

    budget = models.ForeignKey(
        PersonalBudget,
        on_delete=models.CASCADE,
        related_name="categories",
    )
    name = models.CharField(max_length=120)
    allocated_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    order = models.PositiveSmallIntegerField(default=0)
    notes = models.TextField(blank=True, default="")
    group_id = models.CharField(max_length=64, blank=True, default="")
    category_id = models.CharField(max_length=64, blank=True, default="")
    parent_id = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "Personal budget categories"

    def __str__(self):
        return f"{self.budget.name} — {self.name}"


class PersonalBudgetMemberRole(models.TextChoices):
    VIEWER = "viewer", "Viewer"
    EDITOR = "editor", "Editor"


class PersonalBudgetMember(models.Model):
    """Sharing access to a personal budget (per-budget, not per-user globally)."""

    budget = models.ForeignKey(
        PersonalBudget,
        on_delete=models.CASCADE,
        related_name="members",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="shared_personal_budgets",
    )
    role = models.CharField(
        max_length=20,
        choices=PersonalBudgetMemberRole.choices,
        default=PersonalBudgetMemberRole.VIEWER,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["budget", "user"], name="uniq_personal_budget_member"),
        ]

    def __str__(self):
        return f"{self.budget.name} → {self.user_id} ({self.role})"


class PersonalBudgetNotification(models.Model):
    """In-app notifications for personal budget events."""

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="personal_budget_notifications",
    )
    budget = models.ForeignKey(
        PersonalBudget,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    shared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="personal_budget_shares_sent",
    )
    role = models.CharField(max_length=20, default=PersonalBudgetMemberRole.VIEWER)
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True, default="")
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class PersonalBudgetInvite(models.Model):
    """Pending share for an email address not yet registered."""

    budget = models.ForeignKey(
        PersonalBudget,
        on_delete=models.CASCADE,
        related_name="pending_invites",
    )
    email = models.EmailField(max_length=254)
    role = models.CharField(
        max_length=20,
        choices=PersonalBudgetMemberRole.choices,
        default=PersonalBudgetMemberRole.VIEWER,
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="personal_budget_invites_sent",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["budget", "email"], name="uniq_personal_budget_invite"),
        ]

    def __str__(self):
        return f"{self.budget.name} → {self.email} (pending)"


class UserPreferences(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="locale_preferences",
        primary_key=True,
    )
    timezone = models.CharField(max_length=64, blank=True, default="")
    country = models.CharField(max_length=8, blank=True, default="")
    default_currency = models.CharField(max_length=3, default="USD")
    updated_at = models.DateTimeField(auto_now=True)


# --- Budget planning ---------------------------------------------------------


class IncomeStream(models.Model):
    """Expected recurring income the user enters (salary, rent received, freelance...)."""

    FREQUENCIES = (
        ("monthly", "Monthly"),
        ("biweekly", "Every two weeks"),
        ("weekly", "Weekly"),
        ("yearly", "Yearly"),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="income_streams")
    name = models.CharField(max_length=120)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    frequency = models.CharField(max_length=16, choices=FREQUENCIES, default="monthly")
    account_id = models.CharField(max_length=64, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]


class GroupBucket(models.Model):
    """Per-user needs/wants/savings classification of a category group."""

    BUCKETS = (("needs", "Needs"), ("wants", "Wants"), ("savings", "Savings"))

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="group_buckets")
    group_id = models.CharField(max_length=64)
    bucket = models.CharField(max_length=16, choices=BUCKETS, default="wants")

    class Meta:
        unique_together = [("user", "group_id")]


class BudgetPlan(models.Model):
    """A suggested (or accepted) monthly plan: income - commitments split into budgets and savings."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="budget_plans")
    year = models.PositiveIntegerField()
    month = models.PositiveSmallIntegerField()
    plan_type = models.CharField(max_length=32)
    status = models.CharField(max_length=16, default="suggested", db_index=True)
    reason = models.CharField(max_length=32, blank=True, default="manual")
    currency = models.CharField(max_length=3, default="USD")
    income_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    commitments_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    available = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    needs_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    wants_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    savings_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    lines = models.JSONField(default=list, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    # Sub-budgets (trips, projects) reserved inside this month's available money.
    sub_budgets = models.JSONField(default=list, blank=True)
    reserved_total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "year", "month"])]


class Notification(models.Model):
    """General in-app notification (plan suggestions, ...). Links to an app route."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="app_notifications")
    kind = models.CharField(max_length=40)
    title = models.CharField(max_length=200)
    body = models.TextField(blank=True, default="")
    link = models.CharField(max_length=300, blank=True, default="")
    related_id = models.CharField(max_length=64, blank=True, default="")
    fingerprint = models.CharField(max_length=255, blank=True, default="", db_index=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


# --- Risk management ---------------------------------------------------------


class PlannedItem(models.Model):
    """Expected future money in or out (rent, subscriptions, a one-off bill or payment)."""

    KINDS = (("income", "Income"), ("expense", "Expense"))
    FREQUENCIES = (
        ("once", "Once"),
        ("weekly", "Weekly"),
        ("biweekly", "Every two weeks"),
        ("monthly", "Monthly"),
        ("yearly", "Yearly"),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="planned_items")
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=16, choices=KINDS, default="expense")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    frequency = models.CharField(max_length=16, choices=FREQUENCIES, default="monthly")
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    account_id = models.CharField(max_length=64, blank=True, default="")
    category_id = models.CharField(max_length=64, blank=True, default="")
    is_essential = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start_date", "name"]


class RiskSettings(models.Model):
    """Per-user overrides of the risk thresholds (null = use the default)."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="risk_settings")
    dti_warn = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    dti_high = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    balloon_warn = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    balloon_high = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    debt_assets_warn = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    debt_assets_high = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    emergency_warn_months = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    emergency_high_months = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    cash_flow_warn_pct = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    horizon_months = models.PositiveSmallIntegerField(null=True, blank=True)
    included_account_ids = models.JSONField(default=list, blank=True)
    alerts_enabled = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class RiskSnapshot(models.Model):
    """The day's risk score (one row per user per day) for the history chart."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="risk_snapshots")
    as_of = models.DateField()
    score = models.PositiveSmallIntegerField(null=True, blank=True)
    level = models.CharField(max_length=16, blank=True, default="")
    factors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-as_of"]
        unique_together = [("user", "as_of")]
