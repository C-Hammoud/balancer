"""Links inside sent messages: tracked email button clicks and marketing unsubscribe (no sign-in)."""
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from api.messaging.tokens import read_click_token, read_unsubscribe_token
from api.models import MessageDelivery, UserProfile


class MessageOpenView(APIView):
    """GET: record the click on an email button and return the app page to open."""

    permission_classes = (permissions.AllowAny,)
    authentication_classes = ()

    def get(self, request, token):
        delivery_id = read_click_token(token)
        d = MessageDelivery.objects.filter(pk=delivery_id).first() if delivery_id else None
        if not d:
            return Response({"detail": "This link is not valid."}, status=status.HTTP_404_NOT_FOUND)
        if not d.clicked_at:
            d.clicked_at = timezone.now()
            d.save(update_fields=["clicked_at"])
        return Response({"link": d.link or "/dashboard"})


class UnsubscribeView(APIView):
    """POST {token}: stop marketing messages for the user in the token (from the email link)."""

    permission_classes = (permissions.AllowAny,)
    authentication_classes = ()

    def post(self, request):
        user_id = read_unsubscribe_token(str(request.data.get("token") or ""))
        profile = UserProfile.objects.filter(user_id=user_id).first() if user_id else None
        if not profile:
            return Response({"detail": "This unsubscribe link is not valid."}, status=status.HTTP_400_BAD_REQUEST)
        if profile.notify_marketing:
            profile.notify_marketing = False
            profile.save(update_fields=["notify_marketing"])
        return Response({"ok": True, "detail": "You will no longer receive marketing messages."})
