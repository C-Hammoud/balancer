package com.financetracker.access.application;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;

import com.financetracker.access.domain.UserAccount;
import com.financetracker.access.security.DjangoTokenGenerator;
import com.financetracker.shared.config.AppProperties;
import com.financetracker.shared.web.Py;

/** Port of the link helpers in api/email_verification.py and the app hand-off page. */
@Component
public class AuthLinks {

    private final AppProperties props;
    private final DjangoTokenGenerator emailVerificationTokens;

    public AuthLinks(AppProperties props, @Qualifier("emailVerificationTokens") DjangoTokenGenerator emailVerificationTokens) {
        this.props = props;
        this.emailVerificationTokens = emailVerificationTokens;
    }

    /** financetracker://path?query (empty values dropped). */
    public String mobileDeepLink(String path, Map<String, String> params) {
        Map<String, String> kept = new LinkedHashMap<>();
        params.forEach((k, v) -> {
            if (v != null && !v.isEmpty()) {
                kept.put(k, v);
            }
        });
        String query = Py.urlencode(kept);
        String p = path.replaceFirst("^/+", "");
        return props.getMobileAppScheme() + "://" + p + (query.isEmpty() ? "" : "?" + query);
    }

    public String mobileDeepLink(String path, String... keyValues) {
        Map<String, String> params = new LinkedHashMap<>();
        for (int i = 0; i + 1 < keyValues.length; i += 2) {
            params.put(keyValues[i], keyValues[i + 1]);
        }
        return mobileDeepLink(path, params);
    }

    public static String uidFor(UserAccount user) {
        return Py.urlsafeB64Encode(String.valueOf(user.getId()));
    }

    /** API GET link so verification works from mail apps before the SPA loads. */
    public String emailVerificationUrl(UserAccount user) {
        String token = Py.quote(emailVerificationTokens.makeToken(user), "");
        return props.getApiPublicUrl() + "/auth/email-verify/confirm/?uid=" + uidFor(user) + "&token=" + token;
    }

    public String mobileVerifyUrl(UserAccount user) {
        return mobileDeepLink("verify-email", "uid", uidFor(user), "token", emailVerificationTokens.makeToken(user));
    }

    public String passwordResetOpenUrl(String uid, String token) {
        return props.getApiPublicUrl() + "/auth/password-reset/open/?uid=" + uid + "&token=" + Py.quote(token, "");
    }

    /** views/auth._app_handoff_html. */
    public static String handoffHtml(String title, String message, String appUrl, String webUrl) {
        return "<!DOCTYPE html>\n"
                + "<html lang=\"en\">\n"
                + "<head>\n"
                + "  <meta charset=\"utf-8\" />\n"
                + "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />\n"
                + "  <meta http-equiv=\"refresh\" content=\"0;url=" + Py.escape(appUrl) + "\" />\n"
                + "  <title>" + Py.escape(title) + "</title>\n"
                + "  <script>window.location.replace(" + Py.repr(appUrl) + ");</script>\n"
                + "</head>\n"
                + "<body style=\"margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f1f5f4;color:#0f172a;\">\n"
                + "  <div style=\"max-width:420px;margin:64px auto;padding:32px;background:#fff;border-radius:12px;text-align:center;\">\n"
                + "    <h1 style=\"margin:0 0 12px;font-size:22px;color:#0f3d3e;\">" + Py.escape(title) + "</h1>\n"
                + "    <p style=\"margin:0 0 24px;color:#5b6b6b;line-height:1.5;\">" + Py.escape(message) + "</p>\n"
                + "    <p><a href=\"" + Py.escape(appUrl) + "\" style=\"display:inline-block;padding:12px 24px;background:#1a7f7a;color:#fff;border-radius:8px;text-decoration:none;font-weight:600;\">Open the app</a></p>\n"
                + "    <p style=\"margin-top:16px;\"><a href=\"" + Py.escape(webUrl) + "\" style=\"color:#1a7f7a;\">Continue in the browser</a></p>\n"
                + "  </div>\n"
                + "</body>\n"
                + "</html>";
    }
}
