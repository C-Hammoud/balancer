package com.financetracker.finance.application;

import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

/**
 * Python decimal semantics: multiplication and division round to 28 significant digits with
 * ROUND_HALF_EVEN (the default context); quantize() defaults to ROUND_HALF_EVEN. Addition and
 * subtraction are exact, as they are for the amounts this app handles.
 */
public final class Dec {

    public static final BigDecimal ZERO = BigDecimal.ZERO;
    public static final BigDecimal HUNDRED = BigDecimal.valueOf(100);
    static final MathContext PY = new MathContext(28, RoundingMode.HALF_EVEN);

    private Dec() {
    }

    public static BigDecimal of(String s) {
        return new BigDecimal(s);
    }

    public static BigDecimal mul(BigDecimal a, BigDecimal b) {
        return a.multiply(b, PY);
    }

    public static BigDecimal div(BigDecimal a, BigDecimal b) {
        return a.divide(b, PY);
    }

    public static BigDecimal div(BigDecimal a, int b) {
        return a.divide(BigDecimal.valueOf(b), PY);
    }

    /** value.quantize(Decimal("1e-scale")) with ROUND_HALF_EVEN. */
    public static BigDecimal q(BigDecimal value, int scale) {
        return value.setScale(scale, RoundingMode.HALF_EVEN);
    }

    public static BigDecimal orZero(BigDecimal v) {
        return v == null ? ZERO : v;
    }

    public static boolean pos(BigDecimal v) {
        return v != null && v.signum() > 0;
    }

    /** Python max(a, b): the first argument wins ties. */
    public static BigDecimal max(BigDecimal a, BigDecimal b) {
        return b.compareTo(a) > 0 ? b : a;
    }

    /** Python min(a, b): the first argument wins ties. */
    public static BigDecimal min(BigDecimal a, BigDecimal b) {
        return b.compareTo(a) < 0 ? b : a;
    }

    /** Decimal(str(value or "0")) with a 0 fallback (personal_budget_service._decimal). */
    public static BigDecimal parseOrZero(Object value) {
        if (value == null || value instanceof Boolean || "".equals(value)) {
            return ZERO;
        }
        try {
            return value instanceof BigDecimal bd ? bd : new BigDecimal(com.financetracker.shared.web.Py.str(value).strip());
        } catch (NumberFormatException e) {
            return ZERO;
        }
    }

    /** Python f"{value:,.0f}" for a Decimal (ROUND_HALF_EVEN, comma thousands). */
    public static String thousands0(BigDecimal value) {
        BigDecimal rounded = value.setScale(0, RoundingMode.HALF_EVEN);
        DecimalFormat f = new DecimalFormat("#,##0", DecimalFormatSymbols.getInstance(Locale.US));
        String s = f.format(rounded);
        return value.signum() < 0 && rounded.signum() == 0 ? "-" + s : s;
    }
}
