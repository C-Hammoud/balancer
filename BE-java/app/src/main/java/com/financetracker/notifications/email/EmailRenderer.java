package com.financetracker.notifications.email;

import static com.financetracker.shared.web.Py.escape;

import java.time.Clock;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.List;

import org.springframework.stereotype.Component;

import com.financetracker.shared.config.AppProperties;

/** Port of api/email_template.render_html / render_plain_text (same markup and inline styles). */
@Component
public class EmailRenderer {

    private final AppProperties props;
    private final Clock clock;

    public EmailRenderer(AppProperties props, Clock clock) {
        this.props = props;
        this.clock = clock;
    }

    private String brand() {
        return props.getEmail().getAppName();
    }

    private String support() {
        String s = props.getEmail().getSupportEmail();
        return s != null && !s.isEmpty() ? s : props.getEmail().getFrom();
    }

    private int year() {
        return clock.instant().atOffset(ZoneOffset.UTC).getYear();
    }

    private static String nl2br(String text) {
        return escape(text).replace("\n", "<br />");
    }

    public String plainText(BrandedEmail c) {
        List<String> lines = new ArrayList<>();
        lines.add(c.headline);
        lines.add("");
        lines.addAll(c.paragraphs);
        if (!c.detailRows.isEmpty()) {
            lines.add("");
            for (BrandedEmail.Row r : c.detailRows) {
                lines.add(r.label() + ": " + r.value());
            }
        }
        if (!c.bullets.isEmpty()) {
            lines.add("");
            for (String b : c.bullets) {
                lines.add("  • " + b);
            }
        }
        if (c.cta != null) {
            lines.add("");
            lines.add(c.cta.label() + ": " + c.cta.url());
        }
        if (c.secondaryCta != null) {
            lines.add("");
            lines.add(c.secondaryCta.label() + ": " + c.secondaryCta.url());
        }
        if (!c.secondaryNote.isEmpty()) {
            lines.add("");
            lines.add(c.secondaryNote);
        }
        lines.add("");
        lines.add("—");
        lines.add(brand());
        if (!c.footerReason.isEmpty()) {
            lines.add("");
            lines.add(c.footerReason);
        }
        String support = support();
        if (support != null && !support.isEmpty()) {
            lines.add("Questions? Contact us at " + support);
        }
        lines.add("© " + year() + " " + brand());
        return String.join("\n", lines);
    }

    public String html(BrandedEmail c) {
        String brand = escape(brand());
        String preheader = escape(c.preheader);
        String headline = escape(c.headline);
        String primary = props.getEmail().getBrandPrimary();
        String accent = props.getEmail().getBrandAccent();
        String frontend = escape(props.getFrontendUrl());
        int year = year();

        StringBuilder body = new StringBuilder();
        for (String p : c.paragraphs) {
            body.append("<p style=\"margin:0 0 16px;font-size:16px;line-height:1.6;color:#334155;\">")
                    .append(nl2br(p)).append("</p>");
        }
        if (!c.detailRows.isEmpty()) {
            StringBuilder rows = new StringBuilder();
            for (BrandedEmail.Row r : c.detailRows) {
                rows.append("<tr>")
                        .append("<td style=\"padding:10px 12px;border-bottom:1px solid #e2e8f0;color:#64748b;font-size:14px;width:38%;\">")
                        .append(escape(r.label())).append("</td>")
                        .append("<td style=\"padding:10px 12px;border-bottom:1px solid #e2e8f0;color:#0f172a;font-size:14px;font-weight:600;\">")
                        .append(escape(r.value())).append("</td>")
                        .append("</tr>");
            }
            body.append("<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" width=\"100%\" ")
                    .append("style=\"margin:0 0 20px;border:1px solid #e2e8f0;border-radius:8px;border-collapse:collapse;overflow:hidden;\">")
                    .append(rows).append("</table>");
        }
        if (!c.bullets.isEmpty()) {
            StringBuilder items = new StringBuilder();
            for (String b : c.bullets) {
                items.append("<li style=\"margin-bottom:8px;color:#334155;font-size:15px;line-height:1.5;\">")
                        .append(escape(b)).append("</li>");
            }
            body.append("<ul style=\"margin:0 0 20px;padding-left:22px;\">").append(items).append("</ul>");
        }

        StringBuilder ctaHtml = new StringBuilder();
        if (c.cta != null) {
            ctaHtml.append("<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" style=\"margin:28px 0 8px;\">")
                    .append("<tr><td style=\"border-radius:8px;background:").append(accent).append(";\">")
                    .append("<a href=\"").append(escape(c.cta.url())).append("\" target=\"_blank\" rel=\"noopener\" ")
                    .append("style=\"display:inline-block;padding:14px 28px;font-size:16px;font-weight:600;")
                    .append("color:#ffffff;text-decoration:none;border-radius:8px;\">").append(escape(c.cta.label())).append("</a>")
                    .append("</td></tr></table>");
        }
        if (c.secondaryCta != null) {
            ctaHtml.append("<p style=\"margin:12px 0 0;font-size:14px;line-height:1.5;\">")
                    .append("<a href=\"").append(escape(c.secondaryCta.url())).append("\" target=\"_blank\" rel=\"noopener\" ")
                    .append("style=\"color:").append(accent).append(";font-weight:600;text-decoration:none;\">")
                    .append(escape(c.secondaryCta.label())).append("</a></p>");
        }
        String secondaryHtml = c.secondaryNote.isEmpty() ? ""
                : "<p style=\"margin:16px 0 0;font-size:13px;line-height:1.5;color:#64748b;\">" + nl2br(c.secondaryNote) + "</p>";
        String footerReasonHtml = c.footerReason.isEmpty() ? ""
                : "<p style=\"margin:0 0 12px;font-size:12px;line-height:1.5;color:#94a3b8;\">" + escape(c.footerReason) + "</p>";
        String support = support();
        String supportHtml = support == null || support.isEmpty() ? ""
                : "<p style=\"margin:0 0 8px;font-size:12px;color:#94a3b8;\">Questions? <a href=\"mailto:" + escape(support)
                        + "\" style=\"color:" + accent + ";text-decoration:none;\">" + escape(support) + "</a></p>";

        return """
                <!DOCTYPE html>
                <html lang="en">
                <head>
                  <meta charset="utf-8" />
                  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
                  <meta name="color-scheme" content="light" />
                  <meta name="supported-color-schemes" content="light" />
                  <title>%s</title>
                </head>
                <body style="margin:0;padding:0;background-color:#f1f5f4;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;">
                  <div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">%s</div>
                  <table role="presentation" cellpadding="0" cellspacing="0" width="100%%" style="background-color:#f1f5f4;padding:32px 16px;">
                    <tr>
                      <td align="center">
                        <table role="presentation" cellpadding="0" cellspacing="0" width="100%%" style="max-width:560px;">
                          <!-- Header -->
                          <tr>
                            <td style="background:linear-gradient(135deg,%s 0%%,%s 100%%);border-radius:12px 12px 0 0;padding:28px 32px;text-align:center;">
                              <p style="margin:0;font-size:22px;font-weight:700;color:#ffffff;letter-spacing:-0.02em;">%s</p>
                              <p style="margin:8px 0 0;font-size:13px;color:rgba(255,255,255,0.85);">Personal finance &amp; budgeting</p>
                            </td>
                          </tr>
                          <!-- Body -->
                          <tr>
                            <td style="background-color:#ffffff;padding:32px;border-left:1px solid #e2e8f0;border-right:1px solid #e2e8f0;">
                              <h1 style="margin:0 0 20px;font-size:22px;line-height:1.3;color:%s;font-weight:700;">%s</h1>
                              %s
                              %s
                              %s
                            </td>
                          </tr>
                          <!-- Footer -->
                          <tr>
                            <td style="background-color:#f8faf9;border-radius:0 0 12px 12px;padding:24px 32px;border:1px solid #e2e8f0;border-top:none;text-align:center;">
                              %s
                              %s
                              <p style="margin:0;font-size:12px;color:#94a3b8;">
                                © %d %s · <a href="%s" style="color:%s;text-decoration:none;">Open app</a>
                              </p>
                            </td>
                          </tr>
                        </table>
                      </td>
                    </tr>
                  </table>
                </body>
                </html>""".formatted(escape(c.subject), preheader, primary, accent, brand, primary, headline,
                body, ctaHtml, secondaryHtml, footerReasonHtml, supportHtml, year, brand, frontend, accent);
    }
}
