"""
Admin notification center: templates, messages to one user, and campaigns to an audience.
Staff only; every send is written to the audit log.
"""
import logging

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify
from rest_framework import status
from rest_framework.response import Response

from api import support
from api.messaging.audience import AUDIENCE_FLAGS, audience_users, clean_audience
from api.messaging.campaigns import INLINE_BATCH, campaign_to_dict, process_campaigns
from api.messaging.channels import CHANNELS, channel_list
from api.messaging.missing import missing_items
from api.messaging.sending import channel_summary, compose, delivery_to_dict, send_message, skip_reason
from api.messaging.templates import PLACEHOLDERS, ensure_builtin_templates, get_template, template_to_dict
from api.models import MESSAGE_CATEGORIES, Campaign, MessageDelivery, MessageTemplate
from api.views.admin import PAGE_SIZE, StaffView, _get_user, _not_found, _page

logger = logging.getLogger(__name__)

CATEGORY_CODES = tuple(c for c, _ in MESSAGE_CATEGORIES)
CONTENT_FIELDS = ("subject", "body", "link", "link_label", "channels")


def _bad(errors, code=status.HTTP_400_BAD_REQUEST):
    return Response(errors, status=code)


def clean_content(data: dict, base: dict, *, require_complete: bool = True):
    """
    Message fields from the request over `base` (a template or campaign).
    Returns (content, errors); content has subject, body, link, link_label, channels.
    """
    errors = {}
    out = {}
    for field in CONTENT_FIELDS:
        out[field] = data[field] if field in data else base.get(field)
    for field, limit in (("subject", 200), ("body", 5000), ("link", 300), ("link_label", 60)):
        value = out.get(field)
        value = "" if value is None else str(value)
        if field != "body":
            value = value.strip()
        if len(value) > limit:
            errors[field] = [f"At most {limit} characters."]
        out[field] = value
    if out["link"] and not out["link"].startswith("/"):
        errors["link"] = ["Use a page of the app, starting with / (e.g. /budgeting/transactions)."]
    channels = out.get("channels") or []
    if not isinstance(channels, list) or any(c not in CHANNELS for c in channels):
        errors["channels"] = [f"Use any of: {', '.join(CHANNELS)}."]
        channels = []
    out["channels"] = list(dict.fromkeys(channels))
    if require_complete:
        if not out["subject"]:
            errors["subject"] = ["Enter a subject (the notification title)."]
        if not out["body"].strip():
            errors["body"] = ["Enter the message."]
        if not out["channels"]:
            errors.setdefault("channels", ["Choose at least one channel."])
        elif not any(CHANNELS[c].enabled for c in out["channels"]):
            errors["channels"] = ["Choose a channel that is set up (in-app or email)."]
    return out, errors


def _availability(user, category: str, channels) -> list:
    blocked = skip_reason(user, category)
    return [
        {"code": c.code, "label": c.label, "enabled": c.enabled, "chosen": c.code in channels,
         "reason": blocked or c.unavailable(user)}
        for c in CHANNELS.values()
    ]


# ---- Templates -----------------------------------------------------------------------


class AdminMessagingMetaView(StaffView):
    """Everything the message editors need: templates, channels, placeholders, flags."""

    def get(self, request):
        ensure_builtin_templates()
        return Response({
            "templates": [template_to_dict(t) for t in MessageTemplate.objects.all()],
            "channels": channel_list(),
            "placeholders": PLACEHOLDERS,
            "categories": [{"code": c, "label": label} for c, label in MESSAGE_CATEGORIES],
            "audience_flags": [{"code": f, "label": support.FLAGS[f][1]} for f in AUDIENCE_FLAGS],
        })


def _template_fields(data: dict, base: dict):
    content, errors = clean_content(data, base, require_complete=False)
    name = str(data.get("name", base.get("name", "")) or "").strip()
    if not name:
        errors["name"] = ["Enter a name."]
    category = data.get("category", base.get("category", "reminder"))
    if category not in CATEGORY_CODES:
        errors["category"] = [f"Use {', '.join(CATEGORY_CODES)}."]
    return {**content, "name": name[:80], "category": category}, errors


class AdminMessageTemplateListView(StaffView):
    """POST: a new template (superusers)."""

    def post(self, request):
        if not request.user.is_superuser:
            return _bad({"detail": "Only a superuser can add templates."}, status.HTTP_403_FORBIDDEN)
        fields, errors = _template_fields(request.data, {})
        if errors:
            return _bad(errors)
        base_key = slugify(request.data.get("key") or fields["name"])[:36] or "template"
        key, n = base_key, 2
        while MessageTemplate.objects.filter(key=key).exists():
            key, n = f"{base_key[:34]}-{n}", n + 1
        t = MessageTemplate.objects.create(key=key, updated_by=request.user, **fields)
        support.audit(request.user, "template_create", None, key=key)
        return Response(template_to_dict(t), status=status.HTTP_201_CREATED)


class AdminMessageTemplateDetailView(StaffView):
    """PATCH: edit (superusers). DELETE: remove a template that is not built in (superusers)."""

    def _get(self, request, key):
        ensure_builtin_templates()
        return MessageTemplate.objects.filter(key=key).first()

    def patch(self, request, key):
        if not request.user.is_superuser:
            return _bad({"detail": "Only a superuser can edit templates."}, status.HTTP_403_FORBIDDEN)
        t = self._get(request, key)
        if not t:
            return _not_found()
        fields, errors = _template_fields(request.data, template_to_dict(t))
        if errors:
            return _bad(errors)
        for k, v in fields.items():
            setattr(t, k, v)
        t.updated_by = request.user
        t.save()
        support.audit(request.user, "template_edit", None, key=key)
        return Response(template_to_dict(t))

    def delete(self, request, key):
        if not request.user.is_superuser:
            return _bad({"detail": "Only a superuser can delete templates."}, status.HTTP_403_FORBIDDEN)
        t = self._get(request, key)
        if not t:
            return _not_found()
        if t.is_builtin:
            return _bad({"detail": "Built-in templates cannot be deleted; edit them instead."})
        t.delete()
        support.audit(request.user, "template_delete", None, key=key)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---- One user ------------------------------------------------------------------------


def notify_user(user, template_key: str, *, sent_by, reason: str = "", channels=None) -> list:
    """Send a template to a user (used by deactivate / reactivate). Returns the deliveries."""
    t = get_template(template_key)
    if not t:
        return []
    msg = compose(user, subject=t.subject, body=t.body, link=t.link, link_label=t.link_label,
                  category=t.category, reason=reason)
    return send_message(user, msg, channels or t.channels or ["email"], template_key=t.key, sent_by=sent_by)


class AdminUserMessagesView(StaffView):
    """
    GET: messages sent to this user and what they have not filled in yet.
    POST {template_key, channels?, subject?, body?, link?, link_label?, reason?, preview?}:
      preview=true renders the message for this user without sending.
    """

    def get(self, request, pk):
        user = _get_user(pk)
        if not user:
            return _not_found()
        rows = MessageDelivery.objects.filter(user=user).select_related("campaign", "sent_by", "user")[:50]
        return Response({
            "missing": missing_items(user),
            "deliveries": [delivery_to_dict(d) for d in rows],
        })

    def post(self, request, pk):
        user = _get_user(pk)
        if not user:
            return _not_found()
        data = request.data if isinstance(request.data, dict) else {}
        key = str(data.get("template_key") or "custom")
        t = get_template(key)
        if not t:
            return _bad({"template_key": ["Template not found."]})
        content, errors = clean_content(data, template_to_dict(t))
        if errors:
            return _bad(errors)
        msg = compose(user, subject=content["subject"], body=content["body"], link=content["link"],
                      link_label=content["link_label"], category=t.category, reason=str(data.get("reason") or ""))
        if data.get("preview"):
            return Response({
                "subject": msg.subject, "body": msg.body, "link": msg.link, "link_label": msg.link_label,
                "category": msg.category, "channels": _availability(user, msg.category, content["channels"]),
            })
        deliveries = send_message(user, msg, content["channels"], template_key=t.key, sent_by=request.user)
        support.audit(request.user, "send_message", user, template=t.key, subject=msg.subject,
                      results={d.channel: d.status for d in deliveries})
        return Response(
            {"deliveries": [delivery_to_dict(d) for d in deliveries], "summary": channel_summary(deliveries)},
            status=status.HTTP_201_CREATED,
        )


# ---- Campaigns -----------------------------------------------------------------------


def _campaign_fields(data: dict, base: dict):
    content, errors = clean_content(data, base, require_complete=False)
    name = str(data.get("name", base.get("name", "")) or "").strip()
    if not name:
        errors["name"] = ["Enter a name for the campaign."]
    category = data.get("category", base.get("category", "marketing"))
    if category not in ("marketing", "reminder"):
        errors["category"] = ["Use marketing or reminder."]
    audience, aud_errors = clean_audience(data.get("audience", base.get("audience") or {"type": "filter"}))
    if aud_errors:
        errors["audience"] = aud_errors
    return {**content, "name": name[:120], "category": category, "audience": audience}, errors


def _get_campaign(pk):
    try:
        return Campaign.objects.select_related("created_by", "sent_by").get(pk=int(pk))
    except (Campaign.DoesNotExist, TypeError, ValueError):
        return None


EDITABLE = (Campaign.DRAFT, Campaign.SCHEDULED)


class AdminCampaignListView(StaffView):
    """GET ?status=&page=: campaigns, newest first. POST: a new draft."""

    def get(self, request):
        qs = Campaign.objects.select_related("created_by", "sent_by")
        wanted = request.query_params.get("status")
        if wanted:
            qs = qs.filter(status=wanted)
        total = qs.count()
        page, start, end = _page(request)
        return Response({
            "count": total, "page": page, "page_size": PAGE_SIZE,
            "results": [campaign_to_dict(c) for c in qs[start:end]],
        })

    def post(self, request):
        fields, errors = _campaign_fields(request.data, {})
        if errors:
            return _bad(errors)
        c = Campaign.objects.create(created_by=request.user, **fields)
        support.audit(request.user, "campaign_create", None, campaign=c.pk, name=c.name)
        return Response(campaign_to_dict(c), status=status.HTTP_201_CREATED)


class AdminCampaignDetailView(StaffView):
    def get(self, request, pk):
        c = _get_campaign(pk)
        return Response(campaign_to_dict(c)) if c else _not_found()

    def patch(self, request, pk):
        c = _get_campaign(pk)
        if not c:
            return _not_found()
        if c.status not in EDITABLE:
            return _bad({"detail": "Only a draft or scheduled campaign can be edited."})
        fields, errors = _campaign_fields(request.data, campaign_to_dict(c, stats=False))
        if errors:
            return _bad(errors)
        for k, v in fields.items():
            setattr(c, k, v)
        c.save()
        return Response(campaign_to_dict(c))

    def delete(self, request, pk):
        c = _get_campaign(pk)
        if not c:
            return _not_found()
        if c.status not in (Campaign.DRAFT, Campaign.CANCELLED) or c.deliveries.exists():
            return _bad({"detail": "Only a draft (or a cancelled campaign that sent nothing) can be deleted."})
        support.audit(request.user, "campaign_delete", None, campaign=c.pk, name=c.name)
        c.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminCampaignAudienceView(StaffView):
    """POST {audience}: how many active users it reaches, and a few of them."""

    def post(self, request):
        audience, errors = clean_audience(request.data.get("audience"))
        if errors:
            return _bad({"audience": errors})
        users = audience_users(audience)
        return Response({"count": len(users), "sample": [support.user_ref(u) for u in users[:8]]})


class AdminCampaignTestView(StaffView):
    """POST: send the campaign to yourself only (marked [Test]); not counted in its stats."""

    def post(self, request, pk):
        c = _get_campaign(pk)
        if not c:
            return _not_found()
        content, errors = clean_content({}, campaign_to_dict(c, stats=False))
        if errors:
            return _bad(errors)
        msg = compose(request.user, subject=content["subject"], body=content["body"], link=content["link"],
                      link_label=content["link_label"], category=c.category)
        msg.subject = f"[Test] {msg.subject}"[:200]
        deliveries = send_message(request.user, msg, content["channels"], template_key="campaign_test",
                                  sent_by=request.user, force=True)
        return Response({"deliveries": [delivery_to_dict(d) for d in deliveries],
                         "summary": channel_summary(deliveries)})


class AdminCampaignSendView(StaffView):
    """
    POST {confirm_count, scheduled_at?}: send now, or at scheduled_at (ISO date-time).
    confirm_count must equal the current audience size (what the admin confirmed).
    """

    def post(self, request, pk):
        c = _get_campaign(pk)
        if not c:
            return _not_found()
        if c.status not in EDITABLE:
            return _bad({"detail": "This campaign was already sent or cancelled."})
        content, errors = clean_content({}, campaign_to_dict(c, stats=False))
        if errors:
            return _bad(errors)
        audience, aud_errors = clean_audience(c.audience)
        if aud_errors:
            return _bad({"audience": aud_errors})
        if audience.get("type") == "all" and not request.user.is_superuser:
            return _bad({"detail": "Only a superuser can send to all users."}, status.HTTP_403_FORBIDDEN)
        count = len(audience_users(audience))
        if not count:
            return _bad({"detail": "Nobody matches this audience."})
        try:
            confirmed = int(request.data.get("confirm_count"))
        except (TypeError, ValueError):
            confirmed = -1
        if confirmed != count:
            return Response(
                {"detail": f"The audience is now {count} user(s). Check it and confirm again.", "count": count},
                status=status.HTTP_409_CONFLICT,
            )
        now = timezone.now()
        when = None
        raw_when = request.data.get("scheduled_at")
        if raw_when:
            when = parse_datetime(str(raw_when))
            if not when:
                return _bad({"scheduled_at": ["Use a date and time like 2026-12-01T09:00."]})
            if timezone.is_naive(when):
                when = timezone.make_aware(when)
        c.status = Campaign.SCHEDULED
        c.scheduled_at = when if when and when > now else now
        c.sent_by = request.user
        c.save(update_fields=["status", "scheduled_at", "sent_by", "updated_at"])
        later = c.scheduled_at > now
        support.audit(request.user, "campaign_schedule" if later else "campaign_send", None,
                      campaign=c.pk, name=c.name, recipients=count,
                      scheduled_at=c.scheduled_at.isoformat())
        if not later:
            # Start right away; the scheduler sends the rest in batches.
            process_campaigns(only=c.pk, max_per_run=INLINE_BATCH)
        c.refresh_from_db()
        return Response(campaign_to_dict(c))


class AdminCampaignCancelView(StaffView):
    """POST: stop a scheduled or sending campaign (what was sent stays sent)."""

    def post(self, request, pk):
        c = _get_campaign(pk)
        if not c:
            return _not_found()
        if c.status not in (Campaign.SCHEDULED, Campaign.SENDING):
            return _bad({"detail": "Only a scheduled or sending campaign can be cancelled."})
        c.status = Campaign.CANCELLED
        c.finished_at = timezone.now()
        c.save(update_fields=["status", "finished_at", "updated_at"])
        support.audit(request.user, "campaign_cancel", None, campaign=c.pk, name=c.name)
        return Response(campaign_to_dict(c))


class AdminCampaignDeliveriesView(StaffView):
    """GET ?status=&channel=&page=: who the campaign reached and how."""

    def get(self, request, pk):
        c = _get_campaign(pk)
        if not c:
            return _not_found()
        qs = c.deliveries.select_related("user", "sent_by", "campaign")
        for param in ("status", "channel"):
            value = request.query_params.get(param)
            if value:
                qs = qs.filter(**{param: value})
        total = qs.count()
        page, start, end = _page(request)
        return Response({
            "count": total, "page": page, "page_size": PAGE_SIZE,
            "results": [delivery_to_dict(d) for d in qs[start:end]],
        })
