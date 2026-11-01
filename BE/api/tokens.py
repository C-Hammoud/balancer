"""
Token generators. Email verification must not share tokens with password reset:
a forwarded or logged verification link would otherwise let anyone set a new password.
"""
from django.contrib.auth.tokens import PasswordResetTokenGenerator


class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    key_salt = "api.tokens.EmailVerificationTokenGenerator"


email_verification_token = EmailVerificationTokenGenerator()
