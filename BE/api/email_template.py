"""Branded HTML + plain-text email layout (header, body, footer)."""
from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from typing import List, Optional, Tuple

from django.conf import settings
from django.utils import timezone


@dataclass
class EmailCTA:
    label: str
    url: str


@dataclass
class BrandedEmail:
    subject: str
    preheader: str
    headline: str
    paragraphs: List[str] = field(default_factory=list)
    bullets: List[str] = field(default_factory=list)
    detail_rows: List[Tuple[str, str]] = field(default_factory=list)
    cta: Optional[EmailCTA] = None
    secondary_cta: Optional[EmailCTA] = None
    secondary_note: str = ""
    footer_reason: str = ""


def _brand_name() -> str:
    return getattr(settings, "EMAIL_APP_NAME", "Finance Tracker")


def _frontend_url() -> str:
    return getattr(settings, "FRONTEND_URL", "http://localhost:4200").rstrip("/")


def _support_email() -> str:
    return getattr(settings, "SUPPORT_EMAIL", "") or getattr(settings, "DEFAULT_FROM_EMAIL", "")


def _brand_primary() -> str:
    return getattr(settings, "EMAIL_BRAND_PRIMARY", "#0f3d3e")


def _brand_accent() -> str:
    return getattr(settings, "EMAIL_BRAND_ACCENT", "#1a7f7a")


def _nl2br(text: str) -> str:
    return escape(text).replace("\n", "<br />")


def render_plain_text(content: BrandedEmail) -> str:
    lines = [content.headline, ""]
    lines.extend(content.paragraphs)
    if content.detail_rows:
        lines.append("")
        for label, value in content.detail_rows:
            lines.append(f"{label}: {value}")
    if content.bullets:
        lines.append("")
        for item in content.bullets:
            lines.append(f"  • {item}")
    if content.cta:
        lines.extend(["", f"{content.cta.label}: {content.cta.url}"])
    if content.secondary_cta:
        lines.extend(["", f"{content.secondary_cta.label}: {content.secondary_cta.url}"])
    if content.secondary_note:
        lines.extend(["", content.secondary_note])
    lines.extend(["", "—", _brand_name()])
    if content.footer_reason:
        lines.extend(["", content.footer_reason])
    support = _support_email()
    if support:
        lines.append(f"Questions? Contact us at {support}")
    lines.append(f"© {timezone.now().year} {_brand_name()}")
    return "\n".join(lines)


def render_html(content: BrandedEmail) -> str:
    brand = escape(_brand_name())
    preheader = escape(content.preheader)
    headline = escape(content.headline)
    primary = _brand_primary()
    accent = _brand_accent()
    frontend = escape(_frontend_url())
    year = timezone.now().year

    body_parts: List[str] = []
    for p in content.paragraphs:
        body_parts.append(
            f'<p style="margin:0 0 16px;font-size:16px;line-height:1.6;color:#334155;">{_nl2br(p)}</p>'
        )

    if content.detail_rows:
        rows_html = []
        for label, value in content.detail_rows:
            rows_html.append(
                f'<tr>'
                f'<td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;color:#64748b;font-size:14px;width:38%;">'
                f"{escape(label)}</td>"
                f'<td style="padding:10px 12px;border-bottom:1px solid #e2e8f0;color:#0f172a;font-size:14px;font-weight:600;">'
                f"{escape(value)}</td>"
                f"</tr>"
            )
        body_parts.append(
            '<table role="presentation" cellpadding="0" cellspacing="0" width="100%" '
            'style="margin:0 0 20px;border:1px solid #e2e8f0;border-radius:8px;border-collapse:collapse;overflow:hidden;">'
            + "".join(rows_html)
            + "</table>"
        )

    if content.bullets:
        items = "".join(
            f'<li style="margin-bottom:8px;color:#334155;font-size:15px;line-height:1.5;">{escape(b)}</li>'
            for b in content.bullets
        )
        body_parts.append(
            f'<ul style="margin:0 0 20px;padding-left:22px;">{items}</ul>'
        )

    cta_html = ""
    if content.cta:
        cta_html = (
            f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:28px 0 8px;">'
            f'<tr><td style="border-radius:8px;background:{accent};">'
            f'<a href="{escape(content.cta.url)}" target="_blank" rel="noopener" '
            f'style="display:inline-block;padding:14px 28px;font-size:16px;font-weight:600;'
            f'color:#ffffff;text-decoration:none;border-radius:8px;">{escape(content.cta.label)}</a>'
            f"</td></tr></table>"
        )

    if content.secondary_cta:
        cta_html += (
            f'<p style="margin:12px 0 0;font-size:14px;line-height:1.5;">'
            f'<a href="{escape(content.secondary_cta.url)}" target="_blank" rel="noopener" '
            f'style="color:{accent};font-weight:600;text-decoration:none;">'
            f"{escape(content.secondary_cta.label)}</a></p>"
        )

    secondary_html = ""
    if content.secondary_note:
        secondary_html = (
            f'<p style="margin:16px 0 0;font-size:13px;line-height:1.5;color:#64748b;">'
            f"{_nl2br(content.secondary_note)}</p>"
        )

    footer_reason_html = ""
    if content.footer_reason:
        footer_reason_html = (
            f'<p style="margin:0 0 12px;font-size:12px;line-height:1.5;color:#94a3b8;">'
            f"{escape(content.footer_reason)}</p>"
        )

    support = _support_email()
    support_html = ""
    if support:
        support_html = (
            f'<p style="margin:0 0 8px;font-size:12px;color:#94a3b8;">'
            f'Questions? <a href="mailto:{escape(support)}" style="color:{accent};text-decoration:none;">'
            f"{escape(support)}</a></p>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="color-scheme" content="light" />
  <meta name="supported-color-schemes" content="light" />
  <title>{escape(content.subject)}</title>
</head>
<body style="margin:0;padding:0;background-color:#f1f5f4;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;">
  <div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">{preheader}</div>
  <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background-color:#f1f5f4;padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="max-width:560px;">
          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,{primary} 0%,{accent} 100%);border-radius:12px 12px 0 0;padding:28px 32px;text-align:center;">
              <p style="margin:0;font-size:22px;font-weight:700;color:#ffffff;letter-spacing:-0.02em;">{brand}</p>
              <p style="margin:8px 0 0;font-size:13px;color:rgba(255,255,255,0.85);">Personal finance &amp; budgeting</p>
            </td>
          </tr>
          <!-- Body -->
          <tr>
            <td style="background-color:#ffffff;padding:32px;border-left:1px solid #e2e8f0;border-right:1px solid #e2e8f0;">
              <h1 style="margin:0 0 20px;font-size:22px;line-height:1.3;color:{primary};font-weight:700;">{headline}</h1>
              {"".join(body_parts)}
              {cta_html}
              {secondary_html}
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="background-color:#f8faf9;border-radius:0 0 12px 12px;padding:24px 32px;border:1px solid #e2e8f0;border-top:none;text-align:center;">
              {footer_reason_html}
              {support_html}
              <p style="margin:0;font-size:12px;color:#94a3b8;">
                © {year} {brand} · <a href="{frontend}" style="color:{accent};text-decoration:none;">Open app</a>
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
