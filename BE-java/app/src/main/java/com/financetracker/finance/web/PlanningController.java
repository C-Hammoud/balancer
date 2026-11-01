package com.financetracker.finance.web;

import static com.financetracker.finance.web.FinanceJson.dec;
import static com.financetracker.finance.web.FinanceJson.detail;
import static com.financetracker.finance.web.FinanceJson.uid;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.financetracker.access.api.UserDirectory;
import com.financetracker.finance.application.Dec;
import com.financetracker.finance.application.PlanningService;
import com.financetracker.finance.domain.BudgetPlan;
import com.financetracker.finance.domain.CategoryGroup;
import com.financetracker.finance.domain.FinanceRepositories.AccountRepository;
import com.financetracker.finance.domain.FinanceRepositories.BudgetPlanRepository;
import com.financetracker.finance.domain.FinanceRepositories.GroupBucketRepository;
import com.financetracker.finance.domain.FinanceRepositories.IncomeStreamRepository;
import com.financetracker.finance.domain.GroupBucket;
import com.financetracker.finance.domain.IncomeStream;
import com.financetracker.shared.error.ApiException;
import com.financetracker.shared.locale.LocaleConstants;
import com.financetracker.shared.web.Py;

/** Budget planning API: income streams, needs/wants buckets, plan suggestions (api/views/planning.py). */
@RestController
@RequestMapping("/api/v1/budgeting")
class PlanningController {

    private static final List<String> FREQUENCIES = List.of("monthly", "biweekly", "weekly", "yearly");

    private final IncomeStreamRepository streams;
    private final GroupBucketRepository buckets;
    private final BudgetPlanRepository plans;
    private final AccountRepository accounts;
    private final PlanningService planning;
    private final UserDirectory users;
    private final Clock clock;

    PlanningController(IncomeStreamRepository streams, GroupBucketRepository buckets, BudgetPlanRepository plans,
            AccountRepository accounts, PlanningService planning, UserDirectory users, Clock clock) {
        this.streams = streams;
        this.buckets = buckets;
        this.plans = plans;
        this.accounts = accounts;
        this.planning = planning;
        this.users = users;
        this.clock = clock;
    }

    /** _year_month: year 2000-2100, month 1-12, defaults to today; null when invalid. */
    private int[] yearMonth(Map<String, ?> data) {
        LocalDate today = LocalDate.now(clock);
        Object y = data.get("year");
        Object m = data.get("month");
        Integer year = Py.truthy(y) ? com.financetracker.shared.web.RequestData.parseInt(y) : Integer.valueOf(today.getYear());
        Integer month = Py.truthy(m) ? com.financetracker.shared.web.RequestData.parseInt(m) : Integer.valueOf(today.getMonthValue());
        if (year == null || month == null || year < 2000 || year > 2100 || month < 1 || month > 12) {
            return null;
        }
        return new int[] {year, month};
    }

    // ---------------------------------------------------------------- income streams

    private Map<String, Object> streamJson(IncomeStream s) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", s.id);
        m.put("name", s.name);
        m.put("amount", s.amount);
        m.put("currency", s.currency);
        m.put("frequency", s.frequency);
        m.put("monthly_amount", Dec.q(PlanningService.streamMonthlyAmount(s), 2));
        m.put("account_id", s.accountId == null ? "" : s.accountId);
        m.put("is_active", s.active);
        return dec(m);
    }

    /** _apply_stream: validate and copy fields; returns errors or null. */
    private Map<String, Object> applyStream(IncomeStream s, Map<String, Object> data, String uid, boolean partial) {
        Map<String, Object> errors = new LinkedHashMap<>();
        if (data.containsKey("name") || !partial) {
            String name = Py.truthy(data.get("name")) ? Py.str(data.get("name")).strip() : "";
            if (name.isEmpty()) {
                errors.put("name", List.of("Name is required (e.g. Salary)."));
            }
            s.name = name.length() > 120 ? name.substring(0, 120) : name;
        }
        if (data.containsKey("amount") || !partial) {
            try {
                BigDecimal amount = new BigDecimal(Py.str(data.get("amount")).strip());
                if (amount.signum() <= 0) {
                    throw new NumberFormatException();
                }
                s.amount = amount;
            } catch (RuntimeException e) {
                errors.put("amount", List.of("Enter an amount greater than zero."));
            }
        }
        if (data.containsKey("currency") || !partial) {
            String cur = (Py.truthy(data.get("currency")) ? Py.str(data.get("currency"))
                    : s.currency != null && !s.currency.isEmpty() ? s.currency : "USD").strip().toUpperCase();
            if (!LocaleConstants.VALID_CURRENCIES.contains(cur)) {
                errors.put("currency", List.of("Unsupported currency."));
            }
            s.currency = cur;
        }
        if (data.containsKey("frequency")) {
            Object f = data.get("frequency");
            if (!FREQUENCIES.contains(f)) {
                errors.put("frequency", List.of("Use monthly, biweekly, weekly or yearly."));
            }
            s.frequency = f == null ? null : Py.str(f);
        }
        if (data.containsKey("account_id")) {
            String accId = Py.truthy(data.get("account_id")) ? Py.str(data.get("account_id")).strip() : "";
            if (!accId.isEmpty() && accounts.get(accId).filter(a -> uid.equals(a.userId)).isEmpty()) {
                errors.put("account_id", List.of("Account not found."));
            }
            s.accountId = accId;
        }
        if (data.containsKey("is_active")) {
            s.active = Py.truthy(data.get("is_active"));
        }
        return errors.isEmpty() ? null : errors;
    }

    @GetMapping("/income-streams/")
    Map<String, Object> listStreams(@RequestParam(required = false) String currency) {
        String uid = uid();
        String cur = users.reportCurrency(uid, currency);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("streams", streams.listByUser(uid).stream().map(this::streamJson).toList());
        out.put("currency", cur);
        out.put("monthly_total", Py.dec(PlanningService.moneyRound(planning.expectedIncome(uid, cur), cur)));
        return out;
    }

    @PostMapping("/income-streams/")
    ResponseEntity<Object> createStream(@RequestBody(required = false) Map<String, Object> body) {
        String uid = uid();
        IncomeStream s = new IncomeStream();
        s.userId = uid;
        Map<String, Object> errors = applyStream(s, body == null ? Map.of() : body, uid, false);
        if (errors != null) {
            return ResponseEntity.badRequest().body(errors);
        }
        streams.save(s);
        return ResponseEntity.status(HttpStatus.CREATED).body(streamJson(s));
    }

    private IncomeStream ownedStream(String uid, String pk) {
        return streams.get(pk).filter(s -> uid.equals(s.userId)).orElseThrow(ApiException::notFound);
    }

    @PatchMapping("/income-streams/{pk}/")
    ResponseEntity<Object> updateStream(@PathVariable String pk, @RequestBody(required = false) Map<String, Object> body) {
        String uid = uid();
        IncomeStream s = ownedStream(uid, pk);
        Map<String, Object> errors = applyStream(s, body == null ? Map.of() : body, uid, true);
        if (errors != null) {
            return ResponseEntity.badRequest().body(errors);
        }
        streams.save(s);
        return ResponseEntity.ok(streamJson(s));
    }

    @DeleteMapping("/income-streams/{pk}/")
    ResponseEntity<Void> deleteStream(@PathVariable String pk) {
        streams.delete(ownedStream(uid(), pk));
        return ResponseEntity.noContent().build();
    }

    // ---------------------------------------------------------------- buckets

    @GetMapping("/plans/buckets/")
    List<Map<String, Object>> getBuckets() {
        String uid = uid();
        List<CategoryGroup> groups = planning.plannableGroups(uid);
        Set<String> saved = new HashSet<>();
        buckets.listByUser(uid).forEach(b -> saved.add(b.groupId));
        Map<String, String> assigned = planning.groupBuckets(uid, groups);
        List<Map<String, Object>> out = new ArrayList<>();
        for (CategoryGroup g : groups) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("group_id", g.id);
            m.put("group_name", g.name);
            m.put("bucket", assigned.get(g.id));
            m.put("is_default", !saved.contains(g.id));
            out.add(m);
        }
        return out;
    }

    @PutMapping("/plans/buckets/")
    @SuppressWarnings("unchecked")
    ResponseEntity<Object> putBuckets(@RequestBody(required = false) Map<String, Object> body) {
        String uid = uid();
        Object wanted = body == null || !Py.truthy(body.get("buckets")) ? Map.of() : body.get("buckets");
        if (!(wanted instanceof Map<?, ?> wantedMap)) {
            return ResponseEntity.badRequest().body(FinanceJson.fieldError("buckets", "Send {group_id: bucket}."));
        }
        Set<String> visible = new HashSet<>();
        planning.plannableGroups(uid).forEach(g -> visible.add(g.id));
        Map<String, GroupBucket> existing = new LinkedHashMap<>();
        buckets.listByUser(uid).forEach(b -> existing.put(b.groupId, b));
        for (Map.Entry<String, Object> e : ((Map<String, Object>) wantedMap).entrySet()) {
            String gid = e.getKey();
            Object bucket = e.getValue();
            if (!visible.contains(gid) || !PlanningService.BUCKETS.contains(bucket)) {
                return ResponseEntity.badRequest().body(FinanceJson.fieldError("buckets", "Invalid group or bucket: " + gid));
            }
            GroupBucket row = existing.get(gid);
            if (row == null) {
                row = new GroupBucket();
                row.userId = uid;
                row.groupId = gid;
            }
            row.bucket = (String) bucket;
            buckets.save(row);
        }
        return ResponseEntity.ok(getBuckets());
    }

    // ---------------------------------------------------------------- plans

    private int savingsPct(String uid) {
        return users.profileSettings(uid).savingsTargetPct();
    }

    @PostMapping("/plans/preview/")
    ResponseEntity<Object> preview(@RequestBody(required = false) Map<String, Object> body) {
        String uid = uid();
        Map<String, Object> data = body == null ? Map.of() : body;
        int[] ym = yearMonth(data);
        String currency = users.reportCurrency(uid, data.get("currency") == null ? null : Py.str(data.get("currency")));
        int pct = savingsPct(uid);
        if (ym == null) {
            return ResponseEntity.badRequest().body(detail("Invalid year or month."));
        }
        List<Map<String, Object>> built = new ArrayList<>();
        for (String type : PlanningService.PLAN_TYPES) {
            built.add(planning.buildPlan(uid, ym[0], ym[1], type, currency, pct));
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("year", ym[0]);
        out.put("month", ym[1]);
        out.put("currency", currency);
        out.put("plans", built);
        return ResponseEntity.ok(dec(out));
    }

    @GetMapping("/plans/")
    List<Map<String, Object>> listPlans(@RequestParam Map<String, String> query) {
        String uid = uid();
        int[] ym = query.get("month") != null && !query.get("month").isEmpty() ? yearMonth(query) : null;
        List<BudgetPlan> rows = ym != null ? plans.listForMonth(uid, ym[0], ym[1]) : plans.listByUser(uid, 50);
        String status = query.get("status");
        if (status != null && !status.isEmpty()) {
            rows = rows.stream().filter(p -> status.equals(p.status)).toList();
        }
        return dec(rows.stream().map(planning::planToMap).toList());
    }

    @PostMapping("/plans/")
    ResponseEntity<Object> createPlan(@RequestBody(required = false) Map<String, Object> body) {
        String uid = uid();
        Map<String, Object> data = body == null ? Map.of() : body;
        int[] ym = yearMonth(data);
        String currency = users.reportCurrency(uid, data.get("currency") == null ? null : Py.str(data.get("currency")));
        int pct = savingsPct(uid);
        Object planType = Py.truthy(data.get("plan_type")) ? data.get("plan_type") : "rule_50_30_20";
        if (ym == null) {
            return ResponseEntity.badRequest().body(detail("Invalid year or month."));
        }
        if (!PlanningService.PLAN_TYPES.contains(planType)) {
            return ResponseEntity.badRequest().body(FinanceJson.fieldError("plan_type", "Unknown plan type."));
        }
        Map<String, Object> plan = planning.buildPlan(uid, ym[0], ym[1], (String) planType, currency, pct);
        BudgetPlan saved = planning.savePlan(uid, plan, "manual");
        return ResponseEntity.status(HttpStatus.CREATED).body(dec(planning.planToMap(saved)));
    }

    private BudgetPlan ownedPlan(String uid, String pk) {
        return plans.get(pk).filter(p -> uid.equals(p.userId)).orElseThrow(ApiException::notFound);
    }

    @GetMapping("/plans/{pk}/")
    Map<String, Object> getPlan(@PathVariable String pk) {
        return dec(planning.planToMap(ownedPlan(uid(), pk)));
    }

    /** Edit line amounts: {"amounts": {group_id: amount}}. */
    @PatchMapping("/plans/{pk}/")
    @SuppressWarnings("unchecked")
    ResponseEntity<Object> editPlan(@PathVariable String pk, @RequestBody(required = false) Map<String, Object> body) {
        BudgetPlan p = ownedPlan(uid(), pk);
        Object amounts = body == null || !Py.truthy(body.get("amounts")) ? Map.of() : body.get("amounts");
        if (!(amounts instanceof Map<?, ?>)) {
            return ResponseEntity.badRequest().body(FinanceJson.fieldError("amounts", "Send {group_id: amount}."));
        }
        try {
            p = planning.updateLines(p, (Map<String, Object>) amounts);
        } catch (PlanningService.PlanError e) {
            return ResponseEntity.badRequest().body(detail(e.getMessage()));
        }
        return ResponseEntity.ok(dec(planning.planToMap(p)));
    }

    @PostMapping("/plans/{pk}/accept/")
    ResponseEntity<Object> accept(@PathVariable String pk) {
        String uid = uid();
        BudgetPlan p = ownedPlan(uid, pk);
        try {
            planning.accept(uid, p);
        } catch (PlanningService.PlanError e) {
            return ResponseEntity.badRequest().body(detail(e.getMessage()));
        }
        return ResponseEntity.ok(dec(planning.planToMap(p)));
    }

    @PostMapping("/plans/{pk}/dismiss/")
    Map<String, Object> dismiss(@PathVariable String pk) {
        BudgetPlan p = ownedPlan(uid(), pk);
        if ("suggested".equals(p.status)) {
            p.status = "dismissed";
            plans.save(p);
        }
        return dec(planning.planToMap(p));
    }
}
