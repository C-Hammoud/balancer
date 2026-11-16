from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.validators import UnicodeUsernameValidator
from rest_framework import serializers
from rest_framework.exceptions import APIException
from django.contrib.auth.models import update_last_login
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenObtainSerializer
from rest_framework_simplejwt.settings import api_settings as jwt_settings

from api.constants import COUNTRIES, CURRENCY_CHOICES, TYPE_CHOICES
from api.models import UserProfile
from api.user_profile import get_user_profile, is_email_verified, setup_payload

COUNTRY_CHOICES = list(COUNTRIES.choices)
from budgeting.models import Direction, GoalStatus, Frequency, TransactionStatus

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ("username", "email", "first_name", "last_name", "password", "password_confirm")

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        validated_data.pop("password_confirm")
        password = validated_data.pop("password")
        user = User.objects.create_user(password=password, **validated_data)
        get_user_profile(user)
        return user


class PendingRegistrationUpdateSerializer(serializers.ModelSerializer):
    """Registering again for an account that was never verified: new email and name only."""

    password = serializers.CharField(write_only=True)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name", "password", "password_confirm")

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs

    def update(self, instance, validated_data):
        validated_data.pop("password")
        validated_data.pop("password_confirm")
        return super().update(instance, validated_data)


class AdminUserEditSerializer(serializers.Serializer):
    """
    What support can change on a user (Admin -> user page). Every field is optional (PATCH).
    BASIC_FIELDS: any admin. The rest: superusers only (enforced by the view).
    """

    BASIC_FIELDS = ("username", "email", "first_name", "last_name", "timezone", "country", "default_currency")
    SUPERUSER_FIELDS = (
        "phone",
        "email_verified",
        "setup_status",
        "notify_weekly_summaries",
        "notify_low_balance",
        "notify_setup_nudges",
        "notify_plan_updates",
        "savings_target_pct",
    )

    username = serializers.CharField(max_length=150, validators=[UnicodeUsernameValidator()])
    email = serializers.EmailField(max_length=254)
    first_name = serializers.CharField(max_length=150, allow_blank=True)
    last_name = serializers.CharField(max_length=150, allow_blank=True)
    timezone = serializers.CharField(max_length=64, allow_blank=True)
    country = serializers.ChoiceField(choices=[("", "—"), *COUNTRY_CHOICES], allow_blank=True)
    default_currency = serializers.ChoiceField(choices=CURRENCY_CHOICES)
    phone = serializers.CharField(max_length=32, allow_blank=True)
    email_verified = serializers.BooleanField()
    setup_status = serializers.ChoiceField(choices=[c[0] for c in UserProfile.SETUP_STATUS_CHOICES])
    notify_weekly_summaries = serializers.BooleanField()
    notify_low_balance = serializers.BooleanField()
    notify_setup_nudges = serializers.BooleanField()
    notify_plan_updates = serializers.BooleanField()
    savings_target_pct = serializers.IntegerField(min_value=0, max_value=90)

    def _others(self):
        return User.objects.exclude(pk=self.instance.pk)

    def validate_username(self, value):
        value = value.strip()
        if self._others().filter(username__iexact=value).exists():
            raise serializers.ValidationError("Another account already uses this username.")
        return value

    def validate_email(self, value):
        value = value.strip()
        if self._others().filter(email__iexact=value).exists():
            raise serializers.ValidationError("Another account already uses this email.")
        return value

    def validate_timezone(self, value):
        value = value.strip()
        if value:
            try:
                ZoneInfo(value)
            except (ZoneInfoNotFoundError, ValueError):
                raise serializers.ValidationError("Unknown timezone. Use a name such as Asia/Riyadh.")
        return value


class EmailNotVerified(APIException):
    """400 with plain strings: {"detail": "...", "code": "email_not_verified"}.
    A ValidationError would be re-wrapped by the serializer into lists (code: ["..."]),
    which the clients' `code === 'email_not_verified'` check never matches."""

    status_code = 400
    default_code = "email_not_verified"

    def __init__(self):
        super().__init__()
        self.detail = {
            "detail": (
                "Please verify your email before signing in. "
                "Check your inbox for the welcome email with the verification link."
            ),
            "code": "email_not_verified",
        }


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        # Authenticate only (TokenObtainSerializer), then refuse unverified accounts BEFORE
        # tokens are issued and last_login is written: a refused sign-in is not a login.
        data = TokenObtainSerializer.validate(self, attrs)
        user = User.objects.get(pk=self.user.pk)
        if getattr(settings, "REQUIRE_EMAIL_VERIFICATION", True) and not is_email_verified(user):
            raise EmailNotVerified()
        # Same steps as TokenObtainPairSerializer.validate.
        refresh = self.get_token(self.user)
        data["refresh"] = str(refresh)
        data["access"] = str(refresh.access_token)
        if jwt_settings.UPDATE_LAST_LOGIN:
            update_last_login(None, self.user)
        return data


class EmailVerifyConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()


class EmailVerifyResendSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False, allow_blank=True)


class UserProfileSerializer(serializers.ModelSerializer):
    timezone = serializers.CharField(required=False, allow_blank=True, default="")
    country = serializers.CharField(required=False, allow_blank=True, default="")
    default_currency = serializers.ChoiceField(
        choices=CURRENCY_CHOICES, required=False, allow_blank=True, default=""
    )
    email_verified = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "timezone",
            "country",
            "default_currency",
            "email_verified",
            "is_staff",
            "is_superuser",
        )
        # is_staff = support admin, is_superuser = can also grant/remove the admin role.
        read_only_fields = ("id", "username", "email_verified", "is_staff", "is_superuser")

    def get_email_verified(self, obj) -> bool:
        return is_email_verified(obj)

    def to_representation(self, instance):
        from api.user_preferences import get_user_preferences

        data = super().to_representation(instance)
        data.update(get_user_preferences(instance))
        data.update(setup_payload(instance))
        return data


class FirebaseLoginSerializer(serializers.Serializer):
    id_token = serializers.CharField()


class PasswordResetRequestSerializer(serializers.Serializer):
    """Email or username for the account to reset."""

    identifier = serializers.CharField(max_length=254)


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs


class TransactionSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    date = serializers.DateField()
    time = serializers.CharField(required=False, allow_blank=True, default="", max_length=8)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    category_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    classification = serializers.ChoiceField(
        choices=[("", "—"), ("fixed", "Fixed"), ("variable", "Variable")],
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    currency = serializers.ChoiceField(choices=CURRENCY_CHOICES, required=False, default="USD")
    note = serializers.CharField(required=False, allow_blank=True, default="", max_length=1000)
    direction = serializers.ChoiceField(choices=Direction.choices)
    source_account = serializers.CharField(required=False, allow_blank=True, default="")
    account_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    income_source_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    commitment_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    schedule_line_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    include_in_utilization = serializers.BooleanField(required=False, default=False)
    budget_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    budget_category_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    # Transfers: destination account. When set, the transfer is one row (out of account_id,
    # into to_account_id) instead of the legacy pair of rows.
    to_account_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    status = serializers.ChoiceField(choices=TransactionStatus.choices, required=False, default=TransactionStatus.SETTLED)

    def validate(self, attrs):
        direction = attrs.get("direction")
        desc = (attrs.get("description") or "").strip()
        account_id = (attrs.get("account_id") or attrs.get("income_source_id") or "").strip()
        attrs["account_id"] = account_id
        commitment_id = (attrs.get("commitment_id") or "").strip()
        to_account_id = (attrs.get("to_account_id") or "").strip()
        attrs["to_account_id"] = to_account_id if direction == "transfer" else ""
        if direction == "transfer" and to_account_id and to_account_id == account_id:
            raise serializers.ValidationError(
                {"to_account_id": ["Choose a different account to transfer to."]}
            )

        if direction == "income" and not desc:
            raise serializers.ValidationError(
                {"description": ["Enter what this income is (e.g. Salary)."]}
            )
        if not account_id:
            raise serializers.ValidationError(
                {"account_id": ["Select the account this transaction was done from."]}
            )
        if direction == "expense" and not commitment_id and not desc:
            raise serializers.ValidationError(
                {"description": ["Merchant or description is required for expenses."]}
            )
        return attrs


class AccountSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    account_type = serializers.ChoiceField(
        choices=[("bank", "Bank"), ("credit_card", "Credit Card"), ("wallet", "Wallet"), ("other", "Other")],
        required=False,
        default="bank",
    )
    order = serializers.IntegerField(required=False, default=0)
    is_active = serializers.BooleanField(required=False, default=True)
    is_default_for_expenses = serializers.BooleanField(required=False, default=False)


IncomeSourceSerializer = AccountSerializer


class BudgetForecastSerializer(serializers.Serializer):
    forecast = serializers.DecimalField(max_digits=12, decimal_places=2)


class SavingsSerializer(serializers.Serializer):
    year = serializers.IntegerField()
    month = serializers.IntegerField(min_value=1, max_value=12)
    target = serializers.DecimalField(max_digits=12, decimal_places=2)
    actual = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True)
    goal_status = serializers.ChoiceField(choices=GoalStatus.choices)


class CommitmentSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    start_date = serializers.DateField()
    term_months = serializers.IntegerField()
    frequency = serializers.ChoiceField(choices=Frequency.choices)
    payment_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    balloon = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default=0)
    currency = serializers.ChoiceField(choices=CURRENCY_CHOICES, required=False, default="USD")
    reminder_enabled = serializers.BooleanField(required=False, default=True)
    reminder_days_before = serializers.IntegerField(required=False, default=3, min_value=0, max_value=90)


class MarkPaymentSerializer(serializers.Serializer):
    paid_date = serializers.DateField(required=False)
    payment_date = serializers.DateField(required=False)

    def validate(self, attrs):
        # Prefer payment_date alias when provided
        if attrs.get("payment_date") and not attrs.get("paid_date"):
            attrs["paid_date"] = attrs["payment_date"]
        return attrs


class ScheduleLineUpdateSerializer(serializers.Serializer):
    due_date = serializers.DateField(required=False)
    payment_date = serializers.DateField(required=False, allow_null=True)
    paid_date = serializers.DateField(required=False, allow_null=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    status = serializers.ChoiceField(choices=["outstanding", "paid"], required=False)

    def validate(self, attrs):
        if "payment_date" in attrs and "paid_date" not in attrs:
            attrs["paid_date"] = attrs.get("payment_date")
        return attrs


class FinancialStandingSerializer(serializers.Serializer):
    snapshot_date = serializers.DateField()
    total_assets = serializers.DecimalField(max_digits=14, decimal_places=2, default=0)
    current_assets = serializers.DecimalField(max_digits=14, decimal_places=2, default=0)
    fixed_assets = serializers.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_liabilities = serializers.DecimalField(max_digits=14, decimal_places=2, default=0)
    short_term_liabilities = serializers.DecimalField(max_digits=14, decimal_places=2, default=0)
    long_term_liabilities = serializers.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class MerchantLinkSerializer(serializers.Serializer):
    keyword = serializers.CharField(max_length=120)
    category_id = serializers.CharField()
    transaction_ids = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        default=list,
    )
    apply_unmatched = serializers.BooleanField(required=False, default=True)


class GroupSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    order = serializers.IntegerField(required=False, default=0)


class CategorySerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    group_id = serializers.CharField()
    include_in_reports = serializers.BooleanField(required=False, default=True)
    order = serializers.IntegerField(required=False, default=0)


class TypeCategoryMapSerializer(serializers.Serializer):
    consumption_type = serializers.ChoiceField(choices=[c[0] for c in TYPE_CHOICES])
    category_id = serializers.CharField()


class BudgetThresholdSerializer(serializers.Serializer):
    category_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    warn_pct = serializers.DecimalField(max_digits=5, decimal_places=1, default=80)
    critical_pct = serializers.DecimalField(max_digits=5, decimal_places=1, default=100)
    email_enabled = serializers.BooleanField(default=True)

    def validate(self, attrs):
        warn = attrs.get("warn_pct")
        critical = attrs.get("critical_pct")
        if warn is not None and critical is not None and warn > critical:
            raise serializers.ValidationError({"warn_pct": "Warn must be <= critical."})
        return attrs
