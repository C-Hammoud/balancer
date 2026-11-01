package com.financetracker.finance.web;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import com.financetracker.finance.domain.Account;
import com.financetracker.finance.domain.BudgetAlert;
import com.financetracker.finance.domain.Transaction;
import com.financetracker.shared.error.ApiException;
import com.financetracker.shared.security.CurrentUser;
import com.financetracker.shared.web.Py;

/** JSON shapes shared by the finance controllers (api/utils.py helpers). */
final class FinanceJson {

    private FinanceJson() {
    }

    static String uid() {
        return CurrentUser.require().userId();
    }

    /** api.utils.decimal_to_json: Decimals become strings, recursively. */
    @SuppressWarnings("unchecked")
    static <T> T dec(T value) {
        if (value instanceof BigDecimal bd) {
            return (T) Py.dec(bd);
        }
        if (value instanceof Map<?, ?> map) {
            Map<String, Object> out = new LinkedHashMap<>();
            map.forEach((k, v) -> out.put(String.valueOf(k), dec(v)));
            return (T) out;
        }
        if (value instanceof List<?> list) {
            List<Object> out = new ArrayList<>(list.size());
            for (Object v : list) {
                out.add(dec(v));
            }
            return (T) out;
        }
        return value;
    }

    /** api.utils.transaction_to_dict */
    static Map<String, Object> transaction(Transaction t) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", t.id);
        m.put("date", Py.isoformat(t.date));
        m.put("time", t.time == null ? "" : t.time);
        m.put("month", t.month);
        m.put("description", t.description);
        m.put("category_id", t.categoryId);
        m.put("classification", t.classification);
        m.put("amount", Py.dec(t.amount));
        m.put("currency", t.currency == null || t.currency.isEmpty() ? "USD" : t.currency);
        m.put("note", t.note == null ? "" : t.note);
        m.put("direction", t.direction);
        m.put("source_account", t.sourceAccount == null ? "" : t.sourceAccount);
        m.put("account_id", t.incomeSourceId == null ? "" : t.incomeSourceId);
        m.put("income_source_id", t.incomeSourceId == null ? "" : t.incomeSourceId);
        m.put("commitment_id", t.commitmentId == null ? "" : t.commitmentId);
        m.put("schedule_line_id", t.scheduleLineId == null ? "" : t.scheduleLineId);
        m.put("external_id", t.externalId == null ? "" : t.externalId);
        m.put("include_in_utilization", t.includeInUtilization);
        m.put("budget_id", t.budgetId == null ? "" : t.budgetId);
        m.put("budget_category_id", t.budgetCategoryId == null ? "" : t.budgetCategoryId);
        m.put("created_at", Py.isoformat(t.createdAt));
        m.put("updated_at", Py.isoformat(t.updatedAt));
        return m;
    }

    /** views/budgeting._alert_dict */
    static Map<String, Object> alert(BudgetAlert a, Instant now) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", a.id);
        m.put("severity", a.severity);
        m.put("title", a.title);
        m.put("description", a.description);
        m.put("alert_type", a.alertType == null || a.alertType.isEmpty() ? "utilization" : a.alertType);
        m.put("year", a.year);
        m.put("month", a.month);
        m.put("category_id", a.categoryId);
        m.put("utilization_pct", a.utilizationPct == null ? null : Py.dec(a.utilizationPct));
        m.put("actual", Py.dec(a.actual));
        m.put("forecast", Py.dec(a.forecast));
        m.put("is_resolved", a.isResolved);
        m.put("state", a.state(now));
        m.put("resolution", a.resolution == null ? "" : a.resolution);
        m.put("resolved_at", Py.isoformat(a.resolvedAt));
        m.put("snoozed_until", a.isSnoozed(now) ? Py.isoformat(a.snoozedUntil) : null);
        m.put("created_at", Py.isoformat(a.createdAt));
        m.put("commitment_id", a.commitmentId == null ? "" : a.commitmentId);
        m.put("schedule_line_id", a.scheduleLineId == null ? "" : a.scheduleLineId);
        m.put("due_date", a.dueDate == null ? "" : a.dueDate);
        m.put("commitment_name", a.commitmentName == null ? "" : a.commitmentName);
        return m;
    }

    static Map<String, Object> account(Account a) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", a.id);
        m.put("name", a.name);
        m.put("account_type", a.accountType == null || a.accountType.isEmpty() ? "bank" : a.accountType);
        m.put("order", a.order);
        m.put("is_active", a.active);
        m.put("is_default_for_expenses", a.defaultForExpenses);
        return m;
    }

    /** int(request.query_params.get(name, default)) */
    static int queryInt(String raw, int dflt) {
        if (raw == null) {
            return dflt;
        }
        try {
            return Integer.parseInt(raw.strip());
        } catch (NumberFormatException e) {
            throw ApiException.badRequest("Invalid number: " + raw);
        }
    }

    static Map<String, Object> detail(String message) {
        return ApiException.detailBody(message);
    }

    static Map<String, Object> fieldError(String field, String message) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put(field, List.of(message));
        return m;
    }

    /** date.fromisoformat(str(value)[:10]) for request values; null for empty. */
    static LocalDate parseDate(Object value) {
        if (value == null || "".equals(value) || Boolean.FALSE.equals(value)) {
            return null;
        }
        String s = Py.str(value);
        try {
            return LocalDate.parse(s.length() > 10 ? s.substring(0, 10) : s);
        } catch (RuntimeException e) {
            throw ApiException.badRequest("Invalid isoformat string: '" + s + "'");
        }
    }
}
