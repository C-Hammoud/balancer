"""Help & support for signed-in users: report a problem and follow the conversation."""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api import support
from api.models import SupportTicket

CATEGORIES = dict(SupportTicket.CATEGORIES)


def _own_ticket(request, pk):
    try:
        return SupportTicket.objects.get(pk=int(pk), user=request.user)
    except (SupportTicket.DoesNotExist, TypeError, ValueError):
        return None


class SupportTicketListCreateView(APIView):
    def get(self, request):
        rows = SupportTicket.objects.filter(user=request.user)[:100]
        return Response([support.ticket_to_dict(t) for t in rows])

    def post(self, request):
        """{subject, category, message}"""
        subject = (request.data.get("subject") or "").strip()
        message = (request.data.get("message") or "").strip()
        category = request.data.get("category") or "other"
        errors = {}
        if not subject:
            errors["subject"] = ["Give your request a short title."]
        if not message:
            errors["message"] = ["Describe the problem."]
        if category not in CATEGORIES:
            errors["category"] = ["Choose account, bug, data or other."]
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        ticket = SupportTicket.objects.create(user=request.user, subject=subject[:200], category=category)
        support.add_message(ticket, request.user, message[:5000], from_staff=False)
        # Assigned by the configured mode; without an admin (or in pool mode) every admin is told.
        support.auto_assign(ticket)
        if not ticket.assigned_to_id:
            support.notify_pool_ticket(ticket, message)
        return Response(support.ticket_to_dict(ticket, messages=True), status=status.HTTP_201_CREATED)


class SupportTicketDetailView(APIView):
    def get(self, request, pk):
        ticket = _own_ticket(request, pk)
        if not ticket:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(support.ticket_to_dict(ticket, messages=True))


class SupportTicketReplyView(APIView):
    def post(self, request, pk):
        ticket = _own_ticket(request, pk)
        if not ticket:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        body = (request.data.get("body") or "").strip()
        if not body:
            return Response({"body": ["Write a message."]}, status=status.HTTP_400_BAD_REQUEST)
        # A user reply (also on a resolved or closed ticket) sends it back to the assigned admin.
        support.add_message(ticket, request.user, body[:5000], from_staff=False)
        if ticket.assigned_to_id and not (ticket.assigned_to.is_active and support.is_staff(ticket.assigned_to)):
            support.auto_assign(ticket, exclude=ticket.assigned_to)
        support.notify_assignee_of_user_reply(ticket, body)
        return Response(support.ticket_to_dict(ticket, messages=True), status=status.HTTP_201_CREATED)


class SupportTicketConfirmView(APIView):
    """{fixed: true|false, comment?}: answer "is it fixed?" on a resolved ticket."""

    def post(self, request, pk):
        ticket = _own_ticket(request, pk)
        if not ticket:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if ticket.status != SupportTicket.STATUS_RESOLVED:
            return Response(
                {"detail": "Support has not marked this request as fixed yet."}, status=status.HTTP_400_BAD_REQUEST
            )
        fixed = request.data.get("fixed")
        if not isinstance(fixed, bool):
            return Response({"fixed": ["Send true (fixed) or false (not fixed)."]}, status=status.HTTP_400_BAD_REQUEST)
        if fixed:
            support.close(ticket, "user_confirmed", by=request.user)
        else:
            support.reopen(ticket, request.user, (request.data.get("comment") or "")[:5000])
        return Response(support.ticket_to_dict(ticket, messages=True))
