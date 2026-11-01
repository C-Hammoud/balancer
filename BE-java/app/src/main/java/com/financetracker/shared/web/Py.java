package com.financetracker.shared.web;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.Base64;
import java.util.Map;

/**
 * Python-compatible formatting so JSON, links and emails come out byte-for-byte like Django's:
 * datetime.isoformat(), str(Decimal), urllib quote/urlencode, html.escape and repr().
 */
public final class Py {

    private static final DateTimeFormatter SECONDS = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss");

    private Py() {
    }

    /** Aware UTC datetime.isoformat(): 2026-10-18T09:30:00.123456+00:00 (no fraction when 0). */
    public static String isoformat(Instant instant) {
        if (instant == null) {
            return null;
        }
        OffsetDateTime t = instant.atOffset(ZoneOffset.UTC);
        StringBuilder sb = new StringBuilder(SECONDS.format(t));
        int micros = t.getNano() / 1000;
        if (micros != 0) {
            sb.append('.').append(String.format("%06d", micros));
        }
        return sb.append("+00:00").toString();
    }

    /** Naive datetime.isoformat() (no offset). */
    public static String isoformat(LocalDateTime t) {
        if (t == null) {
            return null;
        }
        StringBuilder sb = new StringBuilder(SECONDS.format(t));
        int micros = t.getNano() / 1000;
        if (micros != 0) {
            sb.append('.').append(String.format("%06d", micros));
        }
        return sb.toString();
    }

    public static String isoformat(LocalDate d) {
        return d == null ? null : d.toString();
    }

    /**
     * str(Decimal); "0" for None like api.utils._dec. BigDecimal.toString follows the same
     * to-scientific-string rules as Python's Decimal.__str__.
     */
    public static String dec(BigDecimal value) {
        return value == null ? "0" : value.toString();
    }

    /** Python round(x, 2) style string for already-quantized values. */
    public static String money(BigDecimal value) {
        return value == null ? "0.00" : value.setScale(2, java.math.RoundingMode.HALF_EVEN).toPlainString();
    }

    /** urllib.parse.quote(s, safe). */
    public static String quote(String s, String safe) {
        return encode(s, "_.-~" + safe, false);
    }

    /** urllib.parse.quote_plus(s). */
    public static String quotePlus(String s) {
        return encode(s, "_.-~", true);
    }

    /** urllib.parse.urlencode(dict) (quote_plus on keys and values). */
    public static String urlencode(Map<String, String> params) {
        StringBuilder sb = new StringBuilder();
        for (Map.Entry<String, String> e : params.entrySet()) {
            if (sb.length() > 0) {
                sb.append('&');
            }
            sb.append(quotePlus(e.getKey())).append('=').append(quotePlus(e.getValue()));
        }
        return sb.toString();
    }

    private static String encode(String s, String safe, boolean plus) {
        StringBuilder sb = new StringBuilder();
        for (byte b : s.getBytes(StandardCharsets.UTF_8)) {
            int c = b & 0xff;
            if ((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9')
                    || (c < 128 && safe.indexOf(c) >= 0)) {
                sb.append((char) c);
            } else if (plus && c == ' ') {
                sb.append('+');
            } else {
                sb.append('%').append(String.format("%02X", c));
            }
        }
        return sb.toString();
    }

    /** urllib.parse.unquote(s). */
    public static String unquote(String s) {
        if (s == null || s.indexOf('%') < 0) {
            return s;
        }
        java.io.ByteArrayOutputStream out = new java.io.ByteArrayOutputStream();
        byte[] bytes = s.getBytes(StandardCharsets.UTF_8);
        for (int i = 0; i < bytes.length; i++) {
            if (bytes[i] == '%' && i + 2 < bytes.length && isHex(bytes[i + 1]) && isHex(bytes[i + 2])) {
                out.write(Integer.parseInt(new String(bytes, i + 1, 2, StandardCharsets.US_ASCII), 16));
                i += 2;
            } else {
                out.write(bytes[i]);
            }
        }
        return out.toString(StandardCharsets.UTF_8);
    }

    private static boolean isHex(byte b) {
        return (b >= '0' && b <= '9') || (b >= 'a' && b <= 'f') || (b >= 'A' && b <= 'F');
    }

    /** Python bool(value): None, False, 0, "", empty list/dict are false. */
    public static boolean truthy(Object v) {
        if (v == null) {
            return false;
        }
        if (v instanceof Boolean b) {
            return b;
        }
        if (v instanceof Number n) {
            return n.doubleValue() != 0d;
        }
        if (v instanceof CharSequence s) {
            return s.length() > 0;
        }
        if (v instanceof java.util.Collection<?> c) {
            return !c.isEmpty();
        }
        if (v instanceof Map<?, ?> m) {
            return !m.isEmpty();
        }
        return true;
    }

    /** Python str(value) of a JSON scalar ("" for None handled by callers). */
    public static String str(Object v) {
        return RequestData.pyStr(v);
    }

    /** html.escape(s, quote=True). */
    public static String escape(String s) {
        if (s == null) {
            return "";
        }
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace("\"", "&quot;").replace("'", "&#x27;");
    }

    /** repr(str). */
    public static String repr(String s) {
        char quote = s.indexOf('\'') >= 0 && s.indexOf('"') < 0 ? '"' : '\'';
        StringBuilder sb = new StringBuilder().append(quote);
        for (char c : s.toCharArray()) {
            if (c == quote || c == '\\') {
                sb.append('\\').append(c);
            } else if (c == '\n') {
                sb.append("\\n");
            } else if (c == '\r') {
                sb.append("\\r");
            } else if (c == '\t') {
                sb.append("\\t");
            } else if (c < 0x20 || c == 0x7f) {
                sb.append(String.format("\\x%02x", (int) c));
            } else {
                sb.append(c);
            }
        }
        return sb.append(quote).toString();
    }

    /** django.utils.http.urlsafe_base64_encode (padding stripped). */
    public static String urlsafeB64Encode(String s) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(s.getBytes(StandardCharsets.UTF_8));
    }

    /** django.utils.http.urlsafe_base64_decode; throws IllegalArgumentException on bad input. */
    public static String urlsafeB64Decode(String s) {
        String v = s.strip();
        int pad = (4 - v.length() % 4) % 4;
        v = v + "=".repeat(pad);
        return new String(Base64.getUrlDecoder().decode(v), StandardCharsets.UTF_8);
    }
}
