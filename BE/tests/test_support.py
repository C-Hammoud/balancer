"""Help & support tickets: users see only their own; staff replies notify and email the user."""
import pytest
from django.core import mail

from api.models import SupportTicket
from budgeting.store import NotificationFS

pytestmark = pytest.mark.django_db

S = "/api/v1/support/tickets/"
A = "/api/v1/admin/tickets/"


@pytest.fixture
def staff(make_user):
    return make_user("helper", is_staff=True)


@pytest.fixture
def staff_api(staff, client_for):
    return client_for(staff)


def _open(api, subject="Cannot import CSV"):
    r = api.post(S, {"subject": subject, "category": "bug", "message": "It fails at row 3."}, format="json")
    assert r.status_code == 201, r.content
    return r.json()


def test_validation(api):
    assert api.post(S, {"subject": "", "message": "x"}, format="json").status_code == 400
    assert api.post(S, {"subject": "x", "message": ""}, format="json").status_code == 400
    assert api.post(S, {"subject": "x", "message": "y", "category": "money"}, format="json").status_code == 400


def test_user_sees_only_own_tickets(api, make_user, client_for):
    mine = _open(api)
    other = client_for(make_user())
    assert other.get(S).json() == []
    assert other.get(f"{S}{mine['id']}/").status_code == 404
    assert other.post(f"{S}{mine['id']}/reply/", {"body": "hi"}, format="json").status_code == 404


def test_new_ticket_is_assigned_and_the_admin_notified(api, staff):
    ticket = _open(api)
    assert SupportTicket.objects.get(pk=ticket["id"]).assigned_to == staff
    notes = NotificationFS.list_by_user(str(staff.pk))
    assert any(n.kind == "support_assigned" and n.related_id == str(ticket["id"]) for n in notes)


def test_staff_reply_notifies_and_emails_user(api, user, staff_api, settings):
    settings.NOTIFICATION_EMAILS_ENABLED = False  # support replies are account emails: still sent
    ticket = _open(api)
    mail.outbox.clear()
    r = staff_api.post(f"{A}{ticket['id']}/reply/", {"body": "Please try the Excel template."}, format="json")
    assert r.status_code == 201
    assert r.json()["status"] == "waiting_user"
    assert len(mail.outbox) == 1 and user.email in mail.outbox[0].to
    assert any(n.kind == "support_reply" for n in NotificationFS.list_by_user(str(user.pk)))

    thread = api.get(f"{S}{ticket['id']}/").json()
    assert [m["author"] for m in thread["messages"]] == [user.username, "Support"]


def test_user_reply_reopens(api, staff_api):
    ticket = _open(api)
    staff_api.post(f"{A}{ticket['id']}/reply/", {"body": "Which bank?"}, format="json")
    r = api.post(f"{S}{ticket['id']}/reply/", {"body": "Still broken."}, format="json")
    assert r.status_code == 201 and r.json()["status"] == "open"


def test_staff_queue_filters_and_updates(api, staff_api, staff):
    _open(api, "First")
    second = _open(api, "Second")
    assert staff_api.get(A, {"q": "Second", "view": "mine"}).json()["count"] == 1
    r = staff_api.patch(f"{A}{second['id']}/", {"priority": "high"}, format="json")
    assert r.status_code == 200 and r.json()["priority"] == "high"
    # Status changes go through the workflow; reassigning is for superusers.
    assert staff_api.patch(f"{A}{second['id']}/", {"status": "closed"}, format="json").status_code == 400
    assert staff_api.patch(f"{A}{second['id']}/", {"assigned_to": None}, format="json").status_code == 403
    assert SupportTicket.objects.get(pk=second["id"]).priority == "high"


def test_open_ticket_flag(api, user, staff_api):
    _open(api)
    rows = staff_api.get("/api/v1/admin/users/", {"flag": "open_ticket"}).json()["results"]
    assert [r["id"] for r in rows] == [user.pk]
