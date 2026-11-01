from django import forms
from decimal import Decimal
from .models import (
    Group,
    Category,
    Transaction,
    Budget,
    Savings,
    Commitment,
    CommitmentScheduleLine,
    FinancialStanding,
    MerchantCategoryLink,
    Direction,
    GoalStatus,
    Frequency,
)


class GroupForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ("name", "order")


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ("name", "group", "include_in_reports", "order")


class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = (
            "date",
            "description",
            "category",
            "classification",
            "amount",
            "direction",
            "source_account",
        )
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "description": forms.TextInput(attrs={"class": "form-control", "maxlength": 500}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "classification": forms.Select(attrs={"class": "form-select"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "direction": forms.Select(attrs={"class": "form-select"}),
            "source_account": forms.TextInput(attrs={"class": "form-control"}),
        }


class BudgetForm(forms.ModelForm):
    class Meta:
        model = Budget
        fields = ("category", "year", "month", "forecast")
        widgets = {
            "category": forms.Select(attrs={"class": "form-select"}),
            "year": forms.NumberInput(attrs={"class": "form-control"}),
            "month": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 12}),
            "forecast": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }


class BudgetEditForm(forms.ModelForm):
    """Edit only forecast for an existing budget."""
    class Meta:
        model = Budget
        fields = ("forecast",)
        widgets = {"forecast": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"})}


class SavingsForm(forms.ModelForm):
    class Meta:
        model = Savings
        fields = ("year", "month", "target", "actual", "goal_status")
        widgets = {
            "year": forms.NumberInput(attrs={"class": "form-control"}),
            "month": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 12}),
            "target": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "actual": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "goal_status": forms.Select(attrs={"class": "form-select"}),
        }


class CommitmentForm(forms.ModelForm):
    class Meta:
        model = Commitment
        fields = (
            "name",
            "amount",
            "start_date",
            "term_months",
            "frequency",
            "payment_amount",
            "balloon",
        )
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "start_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "term_months": forms.NumberInput(attrs={"class": "form-control"}),
            "frequency": forms.Select(attrs={"class": "form-select"}),
            "payment_amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "balloon": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
        }


class FinancialStandingForm(forms.ModelForm):
    class Meta:
        model = FinancialStanding
        fields = (
            "snapshot_date",
            "total_assets",
            "current_assets",
            "fixed_assets",
            "total_liabilities",
            "short_term_liabilities",
            "long_term_liabilities",
            "notes",
        )
        widgets = {
            "snapshot_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "total_assets": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "current_assets": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "fixed_assets": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "total_liabilities": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "short_term_liabilities": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "long_term_liabilities": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
        }


class MerchantCategoryLinkForm(forms.ModelForm):
    class Meta:
        model = MerchantCategoryLink
        fields = ("keyword", "category")
        widgets = {
            "keyword": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. STARBUCKS"}),
            "category": forms.Select(attrs={"class": "form-select"}),
        }


class TransactionUploadForm(forms.Form):
    file = forms.FileField(
        label="Statement file (CSV or Excel)",
        help_text="Upload bank/credit statement. Map columns in next step.",
        widget=forms.FileInput(attrs={"class": "form-control", "accept": ".csv,.xlsx,.xls"}),
    )
