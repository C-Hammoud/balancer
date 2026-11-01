"""Template context: open budget alert count for navbar badge."""


def budget_alert_count(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"budget_open_alert_count": 0}
    try:
        from .alerts import open_alert_count
        return {"budget_open_alert_count": open_alert_count(request.user)}
    except Exception:
        return {"budget_open_alert_count": 0}
