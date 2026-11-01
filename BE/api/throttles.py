"""Rate limits for auth and email-sending endpoints (rates: settings DEFAULT_THROTTLE_RATES)."""
from rest_framework.throttling import SimpleRateThrottle


class _IPThrottle(SimpleRateThrottle):
    """Keyed by client IP, so it also applies to anonymous requests."""

    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class LoginThrottle(_IPThrottle):
    scope = "auth_login"


class RegisterThrottle(_IPThrottle):
    scope = "auth_register"


class AuthEmailThrottle(_IPThrottle):
    """Password reset and verification resend: limits email-bombing a victim."""

    scope = "auth_email"


class UserLookupThrottle(SimpleRateThrottle):
    """Per signed-in user: limits probing which emails have accounts."""

    scope = "user_lookup"

    def get_cache_key(self, request, view):
        ident = request.user.pk if request.user and request.user.is_authenticated else self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}
