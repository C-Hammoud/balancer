from django.contrib import admin
from .models import (
    Group,
    Category,
    Transaction,
    MerchantCategoryLink,
    Budget,
    Savings,
    Commitment,
    CommitmentScheduleLine,
    FinancialStanding,
    UploadTemplate,
)


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "order")


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "group", "include_in_reports", "order")
    list_filter = ("group", "include_in_reports")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "description", "category", "amount", "direction", "user")
    list_filter = ("direction", "user")
    search_fields = ("description", "external_id")
    date_hierarchy = "date"


@admin.register(MerchantCategoryLink)
class MerchantCategoryLinkAdmin(admin.ModelAdmin):
    list_display = ("keyword", "category", "user")


@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ("category", "year", "month", "forecast", "user")
    list_filter = ("year", "user")


@admin.register(Savings)
class SavingsAdmin(admin.ModelAdmin):
    list_display = ("year", "month", "actual", "target", "goal_status", "user")
    list_filter = ("goal_status", "user")


class CommitmentScheduleLineInline(admin.TabularInline):
    model = CommitmentScheduleLine
    extra = 0


@admin.register(Commitment)
class CommitmentAdmin(admin.ModelAdmin):
    list_display = ("name", "amount", "start_date", "term_months", "payment_amount", "user")
    inlines = [CommitmentScheduleLineInline]


@admin.register(FinancialStanding)
class FinancialStandingAdmin(admin.ModelAdmin):
    list_display = ("snapshot_date", "total_assets", "total_liabilities", "user")
    date_hierarchy = "snapshot_date"


@admin.register(UploadTemplate)
class UploadTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "user")
