"""Support staff API: user search and support view, support actions, ticket queue, audit log."""
from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from api import support
from api.currency import resolve_report_currency
from api.emails import send_verification_email
from api.models import AdminAuditLog, EmailLog, SupportTicket
from api.user_profile import get_user_profile, is_email_verified, mark_email_verified
from api.utils import decimal_to_json, transaction_to_dict
from api.views.auth import _send_password_reset_email

User = get_user_model()
PAGE_SIZE = 25


def _page(request) -> tuple:
    try:
        page = max(1, int(request.query_params.get("page", 1)))
    except ValueError:
        page = 1
    start = (page - 1) * PAGE_SIZE
    return page, start, start + PAGE_SIZE


def _get_user(pk):
    try:
        return User.objects.get(pk=int(pk))
    except (User.DoesNotExist, TypeError, ValueError):
        return None


def _not_found():
    return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)


class StaffView(APIView):
    permission_classes = (support.IsStaff,)


class AdminOverviewView(StaffView):
    def get(self, request):
        return Response(support.overview(for_user=request.user))


class AdminUserListView(StaffView):
    """GET ?q=&status=active|inactive|staff&flag=<code>&page="""

    def get(self, request):
        qs = support.search_users(request.query_params.get("q", ""), request.query_params.get("status", ""))
        flag = request.query_params.get("flag", "")
        if flag and flag not in support.FLAGS:
            return Response({"flag": ["Unknown flag."]}, status=status.HTTP_400_BAD_REQUEST)
        if flag in support.DB_FLAGS:
            qs = support.filter_by_db_flag(qs, flag)
        elif flag:
            # Store-based flags (risk, activity) are computed per user.
            qs = [u for u in qs[:2000] if any(f["code"] == flag for f in support.user_flags(u))]
        total = len(qs) if isinstance(qs, list) else qs.count()
        page, start, end = _page(request)
        rows = [support.user_row(u) for u in qs[start:end]]
        return Response({"count": total, "page": page, "page_size": PAGE_SIZE, "results": rows})


class AdminUserDetailView(StaffView):
    """The support view of one user. Every look is written to the audit log."""

    def get(self, request, pk):
        user = _get_user(pk)
        if not user:
            return _not_found()
        support.audit(request.user, "view_user", user)
        profile = get_user_profile(user)
        uid = str(user.pk)
        data = {
            "user": {
                **support.user_ref(user),
                "name": f"{user.first_name} {user.last_name}".strip(),
                "is_active": user.is_active,
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
                "date_joined": user.date_joined.isoformat() if user.date_joined else None,
                "last_login": user.last_login.isoformat() if user.last_login else None,
                "email_verified": bool(profile.email_verified),
                "email_verified_at": profile.email_verified_at.isoformat() if profile.email_verified_at else None,
                "setup_status": profile.setup_status,
                "setup_completed_at": profile.setup_completed_at.isoformat() if profile.setup_completed_at else None,
                "notify_low_balance": profile.notify_low_balance,
                "has_password": user.has_usable_password(),
            },
            "flags": support.user_flags(user),
            "emails": [
                {"to": e.to, "subject": e.subject, "kind": e.kind, "status": e.status, "error": e.error,
                 "created_at": e.created_at.isoformat()}
                for e in EmailLog.objects.filter(Q(user=user) | Q(to__iexact=user.email or "-"))[:20]
            ],
            "tickets": [support.ticket_to_dict(t, for_staff=True) for t in user.support_tickets.all()[:20]],
        }
        data.update(self._finance(user, uid))
        return Response(decimal_to_json(data))

    @staticmethod
    def _finance(user, uid: str) -> dict:
        """Summary of the user's money data, read through the store adapters (SQLite or Firestore)."""
        try:
            from api.views.budgeting import _alert_dict
            from budgeting.balances import account_balances
            from budgeting.store import BudgetAlertFS, CommitmentFS, TransactionFS

            currency = resolve_report_currency(user, None)
            recent = TransactionFS.list_by_user(uid, limit=20)
            snap = support.latest_risk(uid)
            return {
                "currency": currency,
                "accounts": account_balances(user, currency),
                "recent_transactions": [transaction_to_dict(t) for t in recent],
                "transactions_count": len(TransactionFS.list_all_for_user(uid)),
                "commitments_count": len(CommitmentFS.list_by_user(uid)),
                "open_alerts": [_alert_dict(a) for a in BudgetAlertFS.list_by_user(uid, open_only=True, limit=20)],
                "risk": {"as_of": snap.as_of.isoformat(), "score": snap.score, "level": snap.level} if snap else None,
            }
        except Exception as exc:
            return {"finance_error": f"Could not load financial data: {exc}"}


class _UserAction(StaffView):
    action = ""

    def post(self, request, pk):
        user = _get_user(pk)
        if not user:
            return _not_found()
        error = self.check(request, user)
        if error:
            return Response({"detail": error}, status=status.HTTP_400_BAD_REQUEST)
        detail = self.run(request, user) or {}
        support.audit(request.user, self.action, user, **detail)
        return Response({"ok": True, "action": self.action, **detail, "user": support.user_row(user)})

    def check(self, request, user):
        return None

    def run(self, request, user):
        return None


class AdminResendVerificationView(_UserAction):
    action = "resend_verification"

    def check(self, request, user):
        if not (user.email or "").strip():
            return "This user has no email address."
        if is_email_verified(user):
            return "This email is already verified."
        return None

    def run(self, request, user):
        return {"email_sent": bool(send_verification_email(user))}


class AdminMarkVerifiedView(_UserAction):
    action = "mark_verified"

    def run(self, request, user):
        mark_email_verified(user)


class AdminSendPasswordResetView(_UserAction):
    action = "send_reset"

    def check(self, request, user):
        if not (user.email or "").strip():
            return "This user has no email address."
        if not user.has_usable_password():
            return "This user signs in with Google/Firebase and has no password to reset."
        return None

    def run(self, request, user):
        return {"email_sent": bool(_send_password_reset_email(user))}


def _last_active_superuser(user) -> bool:
    return user.is_superuser and not User.objects.filter(is_superuser=True, is_active=True).exclude(pk=user.pk).exists()


class AdminDeactivateView(_UserAction):
    action = "deactivate"

    def check(self, request, user):
        if user.pk == request.user.pk:
            return "You cannot deactivate your own account."
        if user.is_superuser and not request.user.is_superuser:
            return "Only a superuser can deactivate a superuser."
        if _last_active_superuser(user):
            return "This is the last active superuser."
        if not user.is_active:
            return "This account is already deactivated."
        return None

    def run(self, request, user):
        user.is_active = False
        user.save(update_fields=["is_active"])
        # Sign the user out everywhere: refresh tokens stop working; access tokens of inactive
        # users are already refused by the JWT authentication.
        revoked = 0
        for token in OutstandingToken.objects.filter(user=user):
            _, created = BlacklistedToken.objects.get_or_create(token=token)
            revoked += int(created)
        # A deactivated admin's unfinished tickets go to the other admins.
        moved = support.reassign_open_tickets_of(user, by=request.user)
        return {"sessions_revoked": revoked, "tickets_reassigned": moved}


class AdminReactivateView(_UserAction):
    action = "reactivate"

    def check(self, request, user):
        return "This account is already active." if user.is_active else None

    def run(self, request, user):
        user.is_active = True
        user.save(update_fields=["is_active"])


class AdminUserRoleView(APIView):
    """POST {"is_staff": true|false}: grant or remove the support admin role (superusers only)."""

    permission_classes = (support.IsSuperuser,)

    def post(self, request, pk):
        user = _get_user(pk)
        if not user:
            return _not_found()
        value = request.data.get("is_staff")
        if not isinstance(value, bool):
            return Response({"is_staff": ["Send true or false."]}, status=status.HTTP_400_BAD_REQUEST)
        if user.pk == request.user.pk:
            return Response({"detail": "You cannot change your own role."}, status=status.HTTP_400_BAD_REQUEST)
        if user.is_superuser and not value:
            return Response(
                {"detail": "This user is a superuser; remove that with: python manage.py set_admin <username> --remove"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.is_staff = value
        user.save(update_fields=["is_staff"])
        support.audit(request.user, "grant_staff" if value else "revoke_staff", user)
        moved = 0 if value else support.reassign_open_tickets_of(user, by=request.user)
        if value:
            support.assign_pool()  # a new admin can take tickets waiting in the pool
        return Response({"ok": True, "tickets_reassigned": moved, "user": support.user_row(user)})


# ---- Tickets ----------------------------------------------------------------------

class AdminTicketListView(StaffView):
    """GET ?view=mine|pool|all&status=open|waiting_user|resolved|closed&q=&page="""

    def get(self, request):
        qs = SupportTicket.objects.select_related("user", "assigned_to")
        view = request.query_params.get("view", "mine")
        if view == "pool":
            qs = qs.filter(status=SupportTicket.STATUS_OPEN, assigned_to__isnull=True)
        elif view == "mine":
            qs = qs.filter(assigned_to=request.user)
        elif view != "all":
            return Response({"view": ["Use mine, pool or all."]}, status=status.HTTP_400_BAD_REQUEST)
        st = request.query_params.get("status", "")
        if st:
            qs = qs.filter(status=st)
        q = (request.query_params.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(subject__icontains=q) | Q(user__username__icontains=q) | Q(user__email__icontains=q))
        total = qs.count()
        page, start, end = _page(request)
        return Response({
            "count": total, "page": page, "page_size": PAGE_SIZE,
            "results": [support.ticket_to_dict(t, for_staff=True) for t in qs[start:end]],
        })


def _staff_ticket(pk):
    try:
        return SupportTicket.objects.select_related("user", "assigned_to").get(pk=int(pk))
    except (SupportTicket.DoesNotExist, TypeError, ValueError):
        return None


class AdminTicketDetailView(StaffView):
    def get(self, request, pk):
        ticket = _staff_ticket(pk)
        if not ticket:
            return _not_found()
        return Response(support.ticket_to_dict(ticket, messages=True, for_staff=True))

    def patch(self, request, pk):
        """
        {priority} by the assigned admin or a superuser; {assigned_to: id|null} by a superuser.
        Status changes go through the workflow actions (reply, resolve, user confirmation).
        """
        ticket = _staff_ticket(pk)
        if not ticket:
            return _not_found()
        if "status" in request.data:
            return Response(
                {"status": ["Use Reply or Mark resolved; the user confirms to close the ticket."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if "assigned_to" in request.data:
            if not request.user.is_superuser:
                return Response({"detail": "Only a superuser can reassign tickets."}, status=status.HTTP_403_FORBIDDEN)
            raw = request.data["assigned_to"]
            member = _get_user(raw) if raw not in (None, "") else None
            if raw not in (None, "") and not (support.is_staff(member) and member.is_active):
                return Response({"assigned_to": ["Choose an active admin."]}, status=status.HTTP_400_BAD_REQUEST)
            if member != ticket.assigned_to:
                support.assign(ticket, member, by=request.user)
        if "priority" in request.data:
            if not support.can_act(request.user, ticket):
                return _not_yours(ticket)
            if request.data["priority"] not in dict(SupportTicket.PRIORITIES):
                return Response({"priority": ["Unknown priority."]}, status=status.HTTP_400_BAD_REQUEST)
            ticket.priority = request.data["priority"]
            ticket.save(update_fields=["priority", "updated_at"])
            support.audit(request.user, "ticket_status", ticket.user, ticket, priority=ticket.priority)
        return Response(support.ticket_to_dict(ticket, messages=True, for_staff=True))


def _not_yours(ticket):
    owner = ticket.assigned_to.username if ticket.assigned_to else "nobody (take it from the pool first)"
    return Response(
        {"detail": f"This ticket is assigned to {owner}. Only the assigned admin or a superuser can act on it."},
        status=status.HTTP_403_FORBIDDEN,
    )


def _actionable(request, pk):
    """(ticket, error response) for reply/resolve: assignee or superuser, ticket not closed."""
    ticket = _staff_ticket(pk)
    if not ticket:
        return None, _not_found()
    if not support.can_act(request.user, ticket):
        return None, _not_yours(ticket)
    if ticket.status == SupportTicket.STATUS_CLOSED:
        return None, Response(
            {"detail": "This ticket is closed. The user can reply to reopen it."}, status=status.HTTP_400_BAD_REQUEST
        )
    return ticket, None


class AdminTicketReplyView(StaffView):
    """Answer or ask the user something: the ticket waits for the user."""

    def post(self, request, pk):
        ticket, error = _actionable(request, pk)
        if error:
            return error
        body = (request.data.get("body") or "").strip()
        if not body:
            return Response({"body": ["Write a reply."]}, status=status.HTTP_400_BAD_REQUEST)
        support.add_message(ticket, request.user, body[:5000], from_staff=True)
        support.notify_user_of_reply(ticket, body)
        support.audit(request.user, "ticket_reply", ticket.user, ticket)
        return Response(support.ticket_to_dict(ticket, messages=True, for_staff=True), status=status.HTTP_201_CREATED)


class AdminTicketResolveView(StaffView):
    """{message}: tell the user it is fixed; they confirm (closes) or say it is not fixed (reopens)."""

    def post(self, request, pk):
        ticket, error = _actionable(request, pk)
        if error:
            return error
        message = (request.data.get("message") or "").strip()
        if not message:
            return Response({"message": ["Tell the user what was fixed."]}, status=status.HTTP_400_BAD_REQUEST)
        support.resolve(ticket, request.user, message[:5000])
        return Response(support.ticket_to_dict(ticket, messages=True, for_staff=True))


class AdminTicketClaimView(StaffView):
    """Take an unassigned ticket from the pool."""

    def post(self, request, pk):
        ticket = _staff_ticket(pk)
        if not ticket:
            return _not_found()
        if ticket.assigned_to_id:
            return Response(
                {"detail": f"Already assigned to {ticket.assigned_to.username}."}, status=status.HTTP_409_CONFLICT
            )
        if ticket.status == SupportTicket.STATUS_CLOSED:
            return Response({"detail": "This ticket is closed."}, status=status.HTTP_400_BAD_REQUEST)
        support.assign(ticket, request.user, by=request.user)
        return Response(support.ticket_to_dict(ticket, messages=True, for_staff=True))


class AdminSupportSettingsView(StaffView):
    """GET (any admin) / PATCH (superusers): assignment mode, reminder and auto-close days, admin emails."""

    def get(self, request):
        return Response(support.settings_to_dict(support.get_support_settings()))

    def patch(self, request):
        from api.models import SupportSettings

        if not request.user.is_superuser:
            return Response({"detail": "Only a superuser can change support settings."}, status=status.HTTP_403_FORBIDDEN)
        row = support.get_support_settings()
        errors = {}
        data = request.data
        if "assignment_mode" in data:
            if data["assignment_mode"] not in dict(SupportSettings.ASSIGNMENT_MODES):
                errors["assignment_mode"] = ["Use least_busy, round_robin or pool."]
            else:
                row.assignment_mode = data["assignment_mode"]
        for key in ("reminder_days", "auto_close_days"):
            if key in data:
                try:
                    value = int(data[key])
                    if not 0 <= value <= 90:
                        raise ValueError
                    setattr(row, key, value)
                except (TypeError, ValueError):
                    errors[key] = ["Enter a number of days between 0 (off) and 90."]
        if "email_admins" in data:
            row.email_admins = bool(data["email_admins"])
        if not errors and row.reminder_days and row.auto_close_days and row.reminder_days >= row.auto_close_days:
            errors["reminder_days"] = ["The reminder must come before the automatic close."]
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        row.updated_by = request.user
        row.save()
        support.audit(
            request.user, "support_settings", None, None,
            assignment_mode=row.assignment_mode, reminder_days=row.reminder_days,
            auto_close_days=row.auto_close_days, email_admins=row.email_admins,
        )
        support.assign_pool()  # switching away from pool mode hands out waiting tickets
        return Response(support.settings_to_dict(row))


class AdminStaffListView(StaffView):
    """Staff members, for the ticket assignee picker."""

    def get(self, request):
        staff = User.objects.filter(Q(is_staff=True) | Q(is_superuser=True), is_active=True).order_by("username")
        return Response([support.user_ref(u) for u in staff])


class AdminAuditLogView(StaffView):
    """GET ?user=<target id>&actor=<id>&action=&page="""

    def get(self, request):
        qs = AdminAuditLog.objects.select_related("actor", "target_user")
        for param, field in (("user", "target_user_id"), ("actor", "actor_id")):
            value = request.query_params.get(param)
            if value:
                try:
                    qs = qs.filter(**{field: int(value)})
                except ValueError:
                    return Response({param: ["Enter a user id."]}, status=status.HTTP_400_BAD_REQUEST)
        action = request.query_params.get("action")
        if action:
            qs = qs.filter(action=action)
        total = qs.count()
        page, start, end = _page(request)
        return Response({
            "count": total, "page": page, "page_size": PAGE_SIZE,
            "results": [support.audit_to_dict(r) for r in qs[start:end]],
        })
