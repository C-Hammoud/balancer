import logging
from urllib.parse import quote

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.http import HttpResponse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from firebase_admin import auth as fb_auth, firestore
from firebase_client import get_firestore_client
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from api.emails import (
    send_password_reset_email,
    send_verification_email,
    send_welcome_and_verification_email,
)
from api.email_verification import (
    build_password_reset_open_url,
    mobile_deep_link,
    verify_email_with_token,
)
from api.serializers import (
    CustomTokenObtainPairSerializer,
    EmailVerifyConfirmSerializer,
    EmailVerifyResendSerializer,
    FirebaseLoginSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterSerializer,
    UserProfileSerializer,
)
from api.user_preferences import ensure_user_preferences, get_user_preferences, save_user_preferences
from api.user_profile import (
    apply_profile_setup_patch,
    get_user_profile,
    is_email_verified,
    mark_email_unverified,
    mark_email_verified,
)
from api.throttles import AuthEmailThrottle, LoginThrottle, RegisterThrottle
from api.utils import jwt_for_user

User = get_user_model()
logger = logging.getLogger(__name__)

PASSWORD_RESET_SENT_MSG = (
    "If an account exists with that email or username, you will receive password reset instructions shortly."
)
VERIFICATION_RESENT_MSG = (
    "If an unverified account exists for that email, a verification link was sent."
)


def _find_user_by_identifier(identifier: str):
    ident = (identifier or "").strip()
    if not ident:
        return None
    if "@" in ident:
        return User.objects.filter(email__iexact=ident).first()
    user = User.objects.filter(username__iexact=ident).first()
    if user:
        return user
    return User.objects.filter(email__iexact=ident).first()


def _send_password_reset_email(user) -> bool:
    email = (user.email or "").strip()
    if not email:
        logger.info("Password reset skipped: user %s has no email.", user.pk)
        return False
    if not user.has_usable_password():
        logger.info("Password reset skipped: user %s has no local password.", user.pk)
        return False

    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    reset_url = build_password_reset_open_url(uid, token)
    app_url = mobile_deep_link("reset-password", uid=uid, token=token)
    return send_password_reset_email(user, reset_url, app_url=app_url)


def _app_handoff_html(*, title: str, message: str, app_url: str, web_url: str) -> HttpResponse:
    from html import escape

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta http-equiv="refresh" content="0;url={escape(app_url)}" />
  <title>{escape(title)}</title>
  <script>window.location.replace({app_url!r});</script>
</head>
<body style="margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f1f5f4;color:#0f172a;">
  <div style="max-width:420px;margin:64px auto;padding:32px;background:#fff;border-radius:12px;text-align:center;">
    <h1 style="margin:0 0 12px;font-size:22px;color:#0f3d3e;">{escape(title)}</h1>
    <p style="margin:0 0 24px;color:#5b6b6b;line-height:1.5;">{escape(message)}</p>
    <p><a href="{escape(app_url)}" style="display:inline-block;padding:12px 24px;background:#1a7f7a;color:#fff;border-radius:8px;text-decoration:none;font-weight:600;">Open the app</a></p>
    <p style="margin-top:16px;"><a href="{escape(web_url)}" style="color:#1a7f7a;">Continue in the browser</a></p>
  </div>
</body>
</html>"""
    return HttpResponse(html)


class RegisterView(generics.CreateAPIView):
    permission_classes = (permissions.AllowAny,)
    throttle_classes = (RegisterThrottle,)
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        email_sent = send_welcome_and_verification_email(user)
        # Pending shared-budget invites are applied only after the email link is
        # confirmed (api/email_verification.py), never at registration.

        if getattr(settings, "REQUIRE_EMAIL_VERIFICATION", True):
            detail = (
                "Account created. Check your email to verify your address, then sign in."
                if email_sent
                else "Account created, but we could not send the verification email. Contact support or try resending from the sign-in page."
            )
            return Response(
                {
                    "detail": detail,
                    "email": user.email,
                    "email_sent": email_sent,
                    "verification_required": True,
                },
                status=status.HTTP_201_CREATED,
            )

        tokens = jwt_for_user(user)
        mark_email_verified(user)
        return Response(
            {"user": UserProfileSerializer(user).data, **tokens},
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    permission_classes = (permissions.AllowAny,)
    throttle_classes = (LoginThrottle,)
    serializer_class = CustomTokenObtainPairSerializer


class RefreshTokenView(TokenRefreshView):
    permission_classes = (permissions.AllowAny,)


class LogoutView(APIView):
    """Revoke a refresh token so it can no longer mint access tokens."""

    permission_classes = (permissions.AllowAny,)
    authentication_classes = ()

    def post(self, request):
        raw = (request.data.get("refresh") or "").strip()
        if not raw:
            return Response({"refresh": ["This field is required."]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            RefreshToken(raw).blacklist()
        except TokenError:
            # Already expired/blacklisted/invalid: the session is over either way.
            pass
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmailVerifyConfirmView(APIView):
    permission_classes = (permissions.AllowAny,)
    authentication_classes = ()

    def get(self, request):
        uid = request.query_params.get("uid", "")
        token = request.query_params.get("token", "")
        result = verify_email_with_token(uid, token)
        if result["ok"]:
            return _app_handoff_html(
                title="Email verified",
                message="Opening Finance Tracker so you can sign in.",
                app_url=mobile_deep_link("login", verified="1"),
                web_url=f"{settings.FRONTEND_URL}/login?verified=1",
            )
        error = quote(result["detail"], safe="")
        return _app_handoff_html(
            title="Could not verify email",
            message=result["detail"],
            app_url=mobile_deep_link("verify-email", uid=uid, token=token, error=result["detail"]),
            web_url=f"{settings.FRONTEND_URL}/verify-email?uid={uid}&token={token}&error={error}",
        )

    def post(self, request):
        serializer = EmailVerifyConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cd = serializer.validated_data
        result = verify_email_with_token(cd["uid"], cd["token"])
        if not result["ok"]:
            return Response({"detail": result["detail"]}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "detail": result["detail"],
                "email_verified": True,
            }
        )


class EmailVerifyResendView(APIView):
    permission_classes = (permissions.AllowAny,)
    throttle_classes = (AuthEmailThrottle,)

    def post(self, request):
        serializer = EmailVerifyResendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = (serializer.validated_data.get("email") or "").strip()

        user = None
        if request.user and request.user.is_authenticated:
            user = request.user
        elif email:
            user = User.objects.filter(email__iexact=email).first()

        if user and not is_email_verified(user):
            send_verification_email(user)

        return Response({"detail": VERIFICATION_RESENT_MSG})


class PasswordResetRequestView(APIView):
    permission_classes = (permissions.AllowAny,)
    throttle_classes = (AuthEmailThrottle,)

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = _find_user_by_identifier(serializer.validated_data["identifier"])
        if user:
            _send_password_reset_email(user)
        return Response({"detail": PASSWORD_RESET_SENT_MSG})


class PasswordResetOpenView(APIView):
    """HTTPS email landing that hands off to the mobile app or web reset screen."""

    permission_classes = (permissions.AllowAny,)
    authentication_classes = ()

    def get(self, request):
        uid = request.query_params.get("uid", "")
        token = request.query_params.get("token", "")
        return _app_handoff_html(
            title="Reset your password",
            message="Opening Finance Tracker to choose a new password.",
            app_url=mobile_deep_link("reset-password", uid=uid, token=token),
            web_url=f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}",
        )


class PasswordResetConfirmView(APIView):
    permission_classes = (permissions.AllowAny,)
    throttle_classes = (LoginThrottle,)

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cd = serializer.validated_data
        try:
            uid = force_str(urlsafe_base64_decode(cd["uid"]))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({"detail": "Invalid or expired reset link."}, status=status.HTTP_400_BAD_REQUEST)

        if not default_token_generator.check_token(user, cd["token"]):
            return Response({"detail": "Invalid or expired reset link."}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(cd["password"])
        user.save(update_fields=["password"])
        return Response({"detail": "Password updated. You can sign in with your new password."})


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer

    def get_object(self):
        return self.request.user

    def retrieve(self, request, *args, **kwargs):
        user = self.get_object()
        tz = request.query_params.get("tz")
        locale = request.query_params.get("locale")
        country = request.query_params.get("country")
        if tz or locale or country:
            ensure_user_preferences(user, timezone=tz, locale=locale, country=country)
        data = self.get_serializer(user).data
        data.update(get_user_preferences(user))
        return Response(data)

    def update(self, request, *args, **kwargs):
        user = self.get_object()
        old_email = (user.email or "").strip().lower()
        serializer = self.get_serializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        cd = serializer.validated_data
        user_fields = [f for f in ("email", "first_name", "last_name") if f in cd]
        email_changed = False
        if user_fields:
            for field in user_fields:
                if field == "email":
                    new_email = (cd[field] or "").strip().lower()
                    if new_email != old_email:
                        email_changed = True
                setattr(user, field, cd[field])
            user.save(update_fields=user_fields)
        if email_changed:
            mark_email_unverified(user)
            send_verification_email(user)
        pref_patch = {}
        for field in ("timezone", "country", "default_currency"):
            if field in request.data:
                pref_patch[field] = cd.get(field, request.data.get(field))
        if pref_patch:
            save_user_preferences(user, pref_patch)
        apply_profile_setup_patch(user, request.data)
        data = serializer.data
        data.update(get_user_preferences(user))
        return Response(data)


class FirebaseLoginView(APIView):
    permission_classes = (permissions.AllowAny,)
    throttle_classes = (LoginThrottle,)

    def post(self, request):
        serializer = FirebaseLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        token = serializer.validated_data["id_token"]
        if token.startswith("Bearer "):
            token = token.split(" ", 1)[1]

        try:
            decoded = fb_auth.verify_id_token(token)
        except Exception:
            return Response({"detail": "Invalid Firebase token."}, status=status.HTTP_401_UNAUTHORIZED)

        uid = decoded.get("uid")
        email = decoded.get("email", "")
        name = decoded.get("name") or decoded.get("displayName") or ""
        photo = decoded.get("picture")
        email_verified_fb = decoded.get("email_verified", False)

        try:
            db = get_firestore_client()
            user_ref = db.collection("users").document(uid)
            snapshot = user_ref.get()
            user_payload = {
                "uid": uid,
                "email": email,
                "name": name,
                "photo": photo,
                "email_verified": email_verified_fb,
            }
            if not snapshot.exists:
                user_ref.set({
                    **user_payload,
                    "created_at": firestore.SERVER_TIMESTAMP,
                    "last_login": firestore.SERVER_TIMESTAMP,
                })
            else:
                user_ref.update({
                    **user_payload,
                    "last_login": firestore.SERVER_TIMESTAMP,
                })
        except Exception:
            logger.warning("Firestore user sync failed for uid %s", uid, exc_info=True)

        user, created = User.objects.get_or_create(
            username=uid,
            defaults={"email": email, "first_name": name or ""},
        )
        if not created and email and user.email != email:
            user.email = email
            user.save(update_fields=["email"])

        profile = get_user_profile(user)
        if email_verified_fb:
            mark_email_verified(user)
        elif created:
            profile.email_verified = False
            profile.save(update_fields=["email_verified"])

        tokens = jwt_for_user(user)
        return Response({
            "user": UserProfileSerializer(user).data,
            **tokens,
        })
