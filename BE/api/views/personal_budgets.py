"""API views for personal (multi) budgets."""
from datetime import date
from decimal import Decimal, InvalidOperation

from rest_framework import status
from rest_framework.exceptions import ParseError
from rest_framework.response import Response
from rest_framework.views import APIView

from budgeting.personal_budget_access import OWNER, require_edit, require_owner, require_view
from budgeting.personal_budget_constants import MEMBER_ROLES, PERSONAL_BUDGET_STATUSES
from budgeting.personal_budget_service import (
    clone_personal_budget,
    create_personal_budget,
    create_personal_budget_category,
    dashboard_summary,
    get_budget_detail,
    list_personal_budgets,
    serialize_budget_summary,
    update_personal_budget,
)
from budgeting.personal_budget_sharing_service import (
    accept_pending_budget_invites,
    cancel_pending_invite,
    list_budget_members,
    list_notifications,
    list_shared_with_me,
    lookup_user_by_email,
    mark_notification_read,
    remove_member,
    share_or_invite_by_email,
    update_member_role,
)
from budgeting.store import PersonalBudgetCategoryFS, PersonalBudgetFS
from api.throttles import UserLookupThrottle


def _parse_date(val):
    if not val:
        return None
    if isinstance(val, date):
        return val
    try:
        return date.fromisoformat(str(val)[:10])
    except ValueError:
        # A malformed date is the client's mistake: 400, not a server error.
        raise ParseError(f"Invalid isoformat string: '{val}'")


class PersonalBudgetDashboardView(APIView):
    def get(self, request):
        return Response(dashboard_summary(request.user))


class PersonalBudgetSharedListView(APIView):
    def get(self, request):
        return Response({"budgets": list_shared_with_me(request.user)})


class PersonalBudgetUserLookupView(APIView):
    """
    Tells the sharer whether the email already has an account (share vs. invite).
    Deliberately returns no name, username or id for that account.
    """

    throttle_classes = (UserLookupThrottle,)

    def get(self, request):
        email = request.query_params.get("email", "")
        user = lookup_user_by_email(email)
        if not user:
            return Response(
                {
                    "found": False,
                    "can_invite": True,
                    "detail": "No account with this email. You can send an invitation to join Finance Tracker.",
                }
            )
        return Response(
            {
                "found": True,
                "can_invite": False,
                "detail": "This email has an account. They will be notified in the app and by email.",
            }
        )


class PersonalBudgetNotificationListView(APIView):
    def get(self, request):
        return Response({"notifications": list_notifications(request.user)})


class PersonalBudgetNotificationReadView(APIView):
    def post(self, request, pk):
        try:
            mark_notification_read(request.user, pk)
        except PermissionError:
            return Response({"detail": "Notification not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"ok": True})


class PersonalBudgetListCreateView(APIView):
    def get(self, request):
        search = request.query_params.get("search", "")
        status_filter = request.query_params.get("status", "")
        sort = request.query_params.get("sort", "created_desc")
        period_start = _parse_date(request.query_params.get("period_start"))
        period_end = _parse_date(request.query_params.get("period_end"))
        in_plan_raw = request.query_params.get("in_plan")
        in_plan = None if in_plan_raw in (None, "") else in_plan_raw.lower() in ("1", "true", "yes")
        return Response({
            "budgets": list_personal_budgets(
                request.user,
                search=search,
                status=status_filter,
                sort=sort,
                period_start=period_start,
                period_end=period_end,
                in_plan=in_plan,
            ),
            "shared_with_me": list_shared_with_me(request.user),
            "statuses": list(PERSONAL_BUDGET_STATUSES),
        })

    def post(self, request):
        data = dict(request.data)
        data["start_date"] = _parse_date(data.get("start_date"))
        data["end_date"] = _parse_date(data.get("end_date"))
        if not data.get("name"):
            return Response({"detail": "Budget name is required."}, status=status.HTTP_400_BAD_REQUEST)
        if data.get("funding_start"):
            data["funding_start"] = _parse_date(data.get("funding_start"))
        try:
            created = create_personal_budget(request.user, data)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(created, status=status.HTTP_201_CREATED)


class PersonalBudgetDetailView(APIView):
    def get(self, request, pk):
        try:
            return Response(get_budget_detail(request.user, pk))
        except PermissionError:
            return Response({"detail": "Budget not found."}, status=status.HTTP_404_NOT_FOUND)

    def patch(self, request, pk):
        data = dict(request.data)
        if "start_date" in data:
            data["start_date"] = _parse_date(data.get("start_date"))
        if "end_date" in data:
            data["end_date"] = _parse_date(data.get("end_date"))
        if data.get("funding_start"):
            data["funding_start"] = _parse_date(data.get("funding_start"))
        try:
            updated = update_personal_budget(request.user, pk, data)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionError as e:
            msg = str(e) or "Budget not found."
            code = status.HTTP_403_FORBIDDEN if "permission" in msg.lower() else status.HTTP_404_NOT_FOUND
            return Response({"detail": msg}, status=code)
        return Response(updated)

    def delete(self, request, pk):
        try:
            budget = require_owner(request.user, pk)
        except PermissionError:
            return Response({"detail": "Budget not found."}, status=status.HTTP_404_NOT_FOUND)
        if budget.is_default:
            return Response({"detail": "Cannot delete the default budget."}, status=status.HTTP_400_BAD_REQUEST)
        for cat in PersonalBudgetCategoryFS.list_by_budget(pk):
            cat.delete()
        budget.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PersonalBudgetCloneView(APIView):
    def post(self, request, pk):
        data = dict(request.data)
        # Only override dates the request sends; absent keys keep the source budget's dates.
        for key in ("start_date", "end_date"):
            if key in data:
                data[key] = _parse_date(data.get(key))
        try:
            cloned = clone_personal_budget(request.user, pk, data)
        except PermissionError:
            return Response({"detail": "Budget not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(cloned, status=status.HTTP_201_CREATED)


class PersonalBudgetMemberListView(APIView):
    def get(self, request, pk):
        try:
            return Response(list_budget_members(request.user, pk))
        except PermissionError:
            return Response({"detail": "Budget not found."}, status=status.HTTP_404_NOT_FOUND)

    def post(self, request, pk):
        email = (request.data.get("email") or "").strip()
        role = (request.data.get("role") or "viewer").strip().lower()
        if role not in MEMBER_ROLES:
            return Response({"detail": "Invalid permission. Choose Viewer or Editor."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            result = share_or_invite_by_email(request.user, pk, email, role)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionError:
            return Response({"detail": "Budget not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(result, status=status.HTTP_201_CREATED)


class PersonalBudgetInviteDetailView(APIView):
    def delete(self, request, pk, invite_pk):
        try:
            return Response(cancel_pending_invite(request.user, pk, invite_pk))
        except PermissionError as e:
            return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)


class PersonalBudgetMemberDetailView(APIView):
    def patch(self, request, pk, member_pk):
        role = (request.data.get("role") or "").strip().lower()
        if role not in MEMBER_ROLES:
            return Response({"detail": "Invalid permission."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            return Response(update_member_role(request.user, pk, member_pk, role))
        except (PermissionError, ValueError) as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk, member_pk):
        try:
            return Response(remove_member(request.user, pk, member_pk))
        except PermissionError as e:
            return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)


class PersonalBudgetCategoryCreateView(APIView):
    def post(self, request, pk):
        try:
            budget, _role = require_edit(request.user, pk)
        except PermissionError as e:
            msg = str(e) or "Budget not found."
            code = status.HTTP_403_FORBIDDEN if "permission" in msg.lower() else status.HTTP_404_NOT_FOUND
            return Response({"detail": msg}, status=code)
        try:
            return Response(create_personal_budget_category(pk, request.user, request.data))
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class PersonalBudgetCategoryDetailView(APIView):
    def _get_budget_and_cat(self, request, budget_pk, cat_pk):
        try:
            budget, role = require_edit(request.user, budget_pk)
        except PermissionError:
            return None, None, None
        cat = PersonalBudgetCategoryFS.get(cat_pk)
        if not cat or cat.budget_id != budget_pk:
            return budget, role, None
        return budget, role, cat

    def patch(self, request, budget_pk, cat_pk):
        budget, _role, cat = self._get_budget_and_cat(request, budget_pk, cat_pk)
        if not budget:
            return Response({"detail": "Budget not found."}, status=status.HTTP_404_NOT_FOUND)
        if not cat:
            return Response({"detail": "Category not found."}, status=status.HTTP_404_NOT_FOUND)
        if "name" in request.data:
            cat.name = (request.data.get("name") or "").strip() or cat.name
        if "allocated_amount" in request.data:
            try:
                cat.allocated_amount = Decimal(str(request.data.get("allocated_amount", "0") or "0").strip())
            except InvalidOperation:
                return Response({"detail": "A valid number is required."}, status=status.HTTP_400_BAD_REQUEST)
        if "order" in request.data:
            try:
                cat.order = int(request.data.get("order", 0) or 0)
            except (TypeError, ValueError):
                cat.order = 0
        if "notes" in request.data:
            cat.notes = request.data.get("notes", "") or ""
        if "group_id" in request.data:
            cat.group_id = (request.data.get("group_id") or "").strip()
        if "category_id" in request.data:
            cat.category_id = (request.data.get("category_id") or "").strip()
        if "parent_id" in request.data:
            cat.parent_id = (request.data.get("parent_id") or "").strip()
        cat.save()
        return Response(serialize_budget_summary(budget, request.user, include_categories=True))

    def delete(self, request, budget_pk, cat_pk):
        budget, _role, cat = self._get_budget_and_cat(request, budget_pk, cat_pk)
        if not budget:
            return Response({"detail": "Budget not found."}, status=status.HTTP_404_NOT_FOUND)
        if not cat:
            return Response({"detail": "Category not found."}, status=status.HTTP_404_NOT_FOUND)
        cat.delete()
        for child in PersonalBudgetCategoryFS.list_by_budget(budget_pk):
            if getattr(child, "parent_id", "") == cat_pk:
                child.delete()
        return Response(serialize_budget_summary(budget, request.user, include_categories=True))
