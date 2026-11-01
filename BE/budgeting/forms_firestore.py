"""
Forms for budgeting app when using Firestore (no Django model binding).
Choices for category etc. are injected in the view from Firestore data.
"""
from django import forms
from decimal import Decimal
from .models import Direction, GoalStatus, Frequency


class TransactionFormFS(forms.Form):
    date = forms.DateField(widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    description = forms.CharField(max_length=500, widget=forms.TextInput(attrs={"class": "form-control"}))
    category_id = forms.ChoiceField(required=False, widget=forms.Select(attrs={"class": "form-select"}))
    classification = forms.ChoiceField(required=False, choices=[("", "—"), ("fixed", "Fixed"), ("variable", "Variable")], widget=forms.Select(attrs={"class": "form-select"}))
    amount = forms.DecimalField(widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}))
    direction = forms.ChoiceField(choices=Direction.choices, widget=forms.Select(attrs={"class": "form-select"}))
    source_account = forms.CharField(required=False, max_length=100, widget=forms.TextInput(attrs={"class": "form-control"}))

    def __init__(self, *args, category_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category_id"].choices = category_choices or [("", "—")]


class BudgetEditFormFS(forms.Form):
    forecast = forms.DecimalField(widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}))


class SavingsFormFS(forms.Form):
    year = forms.IntegerField(widget=forms.NumberInput(attrs={"class": "form-control"}))
    month = forms.IntegerField(min_value=1, max_value=12, widget=forms.NumberInput(attrs={"class": "form-control"}))
    target = forms.DecimalField(widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}))
    actual = forms.DecimalField(required=False, widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}))
    goal_status = forms.ChoiceField(choices=GoalStatus.choices, widget=forms.Select(attrs={"class": "form-select"}))


class CommitmentFormFS(forms.Form):
    name = forms.CharField(max_length=200, widget=forms.TextInput(attrs={"class": "form-control"}))
    amount = forms.DecimalField(widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}))
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    term_months = forms.IntegerField(widget=forms.NumberInput(attrs={"class": "form-control"}))
    frequency = forms.ChoiceField(choices=Frequency.choices, widget=forms.Select(attrs={"class": "form-select"}))
    payment_amount = forms.DecimalField(widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}))
    balloon = forms.DecimalField(required=False, initial=0, widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}))


class FinancialStandingFormFS(forms.Form):
    snapshot_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    total_assets = forms.DecimalField(initial=0, widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}))
    current_assets = forms.DecimalField(initial=0, widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}))
    fixed_assets = forms.DecimalField(initial=0, widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}))
    total_liabilities = forms.DecimalField(initial=0, widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}))
    short_term_liabilities = forms.DecimalField(initial=0, widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}))
    long_term_liabilities = forms.DecimalField(initial=0, widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}))
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}))


class MerchantCategoryLinkFormFS(forms.Form):
    keyword = forms.CharField(max_length=120, widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. STARBUCKS"}))
    category_id = forms.ChoiceField(widget=forms.Select(attrs={"class": "form-select"}))

    def __init__(self, *args, category_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category_id"].choices = category_choices or []


class TransactionUploadForm(forms.Form):
    file = forms.FileField(
        label="Statement file (CSV or Excel)",
        help_text="Upload bank/credit statement. Map columns in next step.",
        widget=forms.FileInput(attrs={"class": "form-control", "accept": ".csv,.xlsx,.xls"}),
    )


class TypeCategoryMapFormFS(forms.Form):
    consumption_type = forms.ChoiceField(
        choices=[
            ("market", "Market"),
            ("transport", "Transport"),
            ("food", "Food"),
            ("other", "Other"),
        ],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    category_id = forms.ChoiceField(widget=forms.Select(attrs={"class": "form-select"}))

    def __init__(self, *args, category_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category_id"].choices = category_choices or []


class BudgetThresholdFormFS(forms.Form):
    category_id = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Leave blank for global default.",
    )
    warn_pct = forms.DecimalField(
        min_value=1,
        max_value=200,
        initial=80,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "1"}),
    )
    critical_pct = forms.DecimalField(
        min_value=1,
        max_value=200,
        initial=100,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "1"}),
    )
    email_enabled = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    def __init__(self, *args, category_choices=None, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [("", "— Global default —")] + list(category_choices or [])
        self.fields["category_id"].choices = choices

    def clean(self):
        cleaned = super().clean()
        warn = cleaned.get("warn_pct")
        critical = cleaned.get("critical_pct")
        if warn is not None and critical is not None and warn > critical:
            self.add_error("warn_pct", "Warn % should be less than or equal to critical %.")
        return cleaned
