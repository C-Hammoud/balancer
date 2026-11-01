"""Health and locale meta endpoints."""
from rest_framework.response import Response
from rest_framework.views import APIView

from api.constants import COUNTRIES, CURRENCY_CHOICES, TYPE_CHOICES
from api.locale_defaults import detect_locale_defaults


class HealthView(APIView):
    permission_classes = []
    authentication_classes = []

    def get(self, request):
        # No side effects: uptime monitors and anonymous callers hit this endpoint.
        return Response({"status": "ok"})


class MetaView(APIView):
    def get(self, request):
        from django.conf import settings

        from api.currency import get_exchange_rates
        from api.user_preferences import get_user_preferences

        tz = request.query_params.get("tz")
        locale = request.query_params.get("locale")
        country = request.query_params.get("country")
        suggested = detect_locale_defaults(timezone=tz, locale=locale, country=country)
        payload = {
            "currencies": [{"code": c[0], "label": c[1]} for c in CURRENCY_CHOICES],
            "consumption_types": [{"code": c[0], "label": c[1]} for c in TYPE_CHOICES],
            "countries": [{"code": c[0], "label": c[1]} for c in sorted(COUNTRIES.choices, key=lambda x: x[1])],
            "suggested": suggested,
            "exchange_rates": get_exchange_rates(),
            "exchange_rates_as_of": getattr(settings, "EXCHANGE_RATES_AS_OF", None),
        }
        if request.user and request.user.is_authenticated:
            saved = get_user_preferences(request.user)
            if saved.get("default_currency"):
                suggested = detect_locale_defaults(
                    timezone=saved.get("timezone") or tz,
                    locale=locale,
                    country=saved.get("country") or country,
                    default_currency=saved.get("default_currency"),
                )
                payload["suggested"] = suggested
                payload["saved_preferences"] = saved
        return Response(payload)
