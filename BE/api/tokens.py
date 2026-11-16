"""
Token generators. Email verification must not share tokens with password reset:
a forwarded or logged verification link would otherwise let anyone set a new password.
"""
from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    key_salt = "api.tokens.EmailVerificationTokenGenerator"

    def _make_hash_value(self, user, timestamp):
        # Unlike password reset, last_login is left out: an unverified user trying to sign in
        # must not break the verification links already in their inbox. A new password or a
        # new email address still invalidates them. Keep in sync with BE-java DjangoTokenGenerator.
        email = getattr(user, user.get_email_field_name(), "") or ""
        return f"{user.pk}{user.password}{timestamp}{email}"


email_verification_token = EmailVerificationTokenGenerator()
