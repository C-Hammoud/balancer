package com.financetracker.finance.web;

import static com.financetracker.finance.web.FinanceJson.detail;
import static com.financetracker.finance.web.FinanceJson.parseDate;
import static com.financetracker.finance.web.FinanceJson.uid;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.Supplier;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.financetracker.finance.application.PersonalBudgetAccess;
import com.financetracker.finance.application.PersonalBudgetService;
import com.financetracker.finance.application.SharingService;
import com.financetracker.finance.domain.PersonalBudget;
import com.financetracker.finance.domain.PersonalBudgetMember;
import com.financetracker.shared.config.AppProperties;
import com.financetracker.shared.web.Py;
import com.financetracker.shared.web.Throttler;

/** /budgeting/personal-budgets/* (api/views/personal_budgets.py). */
@RestController
@RequestMapping("/api/v1/budgeting/personal-budgets")
class PersonalBudgetsController {

    private final PersonalBudgetService budgets;
    private final SharingService sharing;
    private final PersonalBudgetAccess access;
    private final Throttler throttler;
    private final AppProperties props;

    PersonalBudgetsController(PersonalBudgetService budgets, SharingService sharing, PersonalBudgetAccess access,
            Throttler throttler, AppProperties props) {
        this.budgets = budgets;
        this.sharing = sharing;
        this.access = access;
        this.throttler = throttler;
        this.props = props;
    }

    private static ResponseEntity<Object> status(HttpStatus status, Object body) {
        return ResponseEntity.status(status).body(body);
    }

    /** PermissionError -> 404 "Budget not found." */
    private static ResponseEntity<Object> notFoundOn(Supplier<Object> action) {
        try {
            return ResponseEntity.ok(action.get());
        } catch (PersonalBudgetAccess.Denied e) {
            return status(HttpStatus.NOT_FOUND, detail("Budget not found."));
        }
    }

    /** PermissionError -> 403 when the message mentions permission, else 404. */
    private static ResponseEntity<Object> permissionAware(Supplier<Object> action) {
        try {
            return ResponseEntity.ok(action.get());
        } catch (PersonalBudgetAccess.Denied e) {
            String msg = e.getMessage() == null || e.getMessage().isEmpty() ? "Budget not found." : e.getMessage();
            return status(msg.toLowerCase().contains("permission") ? HttpStatus.FORBIDDEN : HttpStatus.NOT_FOUND, detail(msg));
        }
    }

    private static Map<String, Object> body(Map<String, Object> raw) {
        return raw == null ? new LinkedHashMap<>() : new LinkedHashMap<>(raw);
    }

    @GetMapping("/dashboard/")
    Map<String, Object> dashboard() {
        String uid = uid();
        return budgets.dashboard(uid, sharing.sharedWithMe(uid));
    }

    @GetMapping("/shared/")
    Map<String, Object> shared() {
        return Map.of("budgets", sharing.sharedWithMe(uid()));
    }

    /** Tells the sharer whether the email has an account (share vs invite); returns no account details. */
    @GetMapping("/users/lookup/")
    Map<String, Object> lookup(@RequestParam(defaultValue = "") String email) {
        String uid = uid();
        throttler.check("user_lookup", props.getThrottle().getUserLookup(), uid);
        Map<String, Object> out = new LinkedHashMap<>();
        if (!sharing.emailHasAccount(email)) {
            out.put("found", false);
            out.put("can_invite", true);
            out.put("detail", "No account with this email. You can send an invitation to join Finance Tracker.");
        } else {
            out.put("found", true);
            out.put("can_invite", false);
            out.put("detail", "This email has an account. They will be notified in the app and by email.");
        }
        return out;
    }

    @GetMapping("/notifications/")
    Map<String, Object> notifications() {
        return Map.of("notifications", sharing.listNotifications(uid(), 50));
    }

    @PostMapping("/notifications/{pk}/read/")
    ResponseEntity<Object> readNotification(@PathVariable String pk) {
        try {
            sharing.markNotificationRead(uid(), pk);
        } catch (PersonalBudgetAccess.Denied e) {
            return status(HttpStatus.NOT_FOUND, detail("Notification not found."));
        }
        return ResponseEntity.ok(Map.of("ok", true));
    }

    @GetMapping("/")
    Map<String, Object> list(@RequestParam(defaultValue = "") String search, @RequestParam(defaultValue = "") String status,
            @RequestParam(defaultValue = "created_desc") String sort,
            @RequestParam(name = "period_start", required = false) String periodStart,
            @RequestParam(name = "period_end", required = false) String periodEnd) {
        String uid = uid();
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("budgets", budgets.list(uid, search, status, sort, parseDate(periodStart), parseDate(periodEnd)));
        out.put("shared_with_me", sharing.sharedWithMe(uid));
        out.put("statuses", PersonalBudget.STATUSES);
        return out;
    }

    @PostMapping("/")
    ResponseEntity<Object> create(@RequestBody(required = false) Map<String, Object> raw) {
        Map<String, Object> data = body(raw);
        if (!Py.truthy(data.get("name"))) {
            return status(HttpStatus.BAD_REQUEST, detail("Budget name is required."));
        }
        return status(HttpStatus.CREATED, budgets.create(uid(), data, parseDate(data.get("start_date")), parseDate(data.get("end_date"))));
    }

    @GetMapping("/{pk}/")
    ResponseEntity<Object> get(@PathVariable String pk) {
        return notFoundOn(() -> budgets.detail(uid(), pk));
    }

    @PatchMapping("/{pk}/")
    ResponseEntity<Object> update(@PathVariable String pk, @RequestBody(required = false) Map<String, Object> raw) {
        Map<String, Object> data = body(raw);
        return permissionAware(() -> budgets.update(uid(), pk, data, parseDate(data.get("start_date")), parseDate(data.get("end_date"))));
    }

    @DeleteMapping("/{pk}/")
    ResponseEntity<Object> delete(@PathVariable String pk) {
        try {
            budgets.delete(uid(), pk);
        } catch (PersonalBudgetAccess.Denied e) {
            return status(HttpStatus.NOT_FOUND, detail("Budget not found."));
        } catch (PersonalBudgetAccess.Invalid e) {
            return status(HttpStatus.BAD_REQUEST, detail(e.getMessage()));
        }
        return ResponseEntity.noContent().build();
    }

    @PostMapping("/{pk}/clone/")
    ResponseEntity<Object> cloneBudget(@PathVariable String pk, @RequestBody(required = false) Map<String, Object> raw) {
        Map<String, Object> data = body(raw);
        try {
            return status(HttpStatus.CREATED,
                    budgets.cloneBudget(uid(), pk, data, parseDate(data.get("start_date")), parseDate(data.get("end_date"))));
        } catch (PersonalBudgetAccess.Denied e) {
            return status(HttpStatus.NOT_FOUND, detail("Budget not found."));
        }
    }

    @GetMapping("/{pk}/members/")
    ResponseEntity<Object> members(@PathVariable String pk) {
        return notFoundOn(() -> sharing.listMembers(uid(), pk));
    }

    @PostMapping("/{pk}/members/")
    ResponseEntity<Object> share(@PathVariable String pk, @RequestBody(required = false) Map<String, Object> raw) {
        Map<String, Object> data = body(raw);
        String email = Py.truthy(data.get("email")) ? Py.str(data.get("email")).strip() : "";
        String role = (Py.truthy(data.get("role")) ? Py.str(data.get("role")) : "viewer").strip().toLowerCase();
        if (!PersonalBudgetMember.ROLES.contains(role)) {
            return status(HttpStatus.BAD_REQUEST, detail("Invalid permission. Choose Viewer or Editor."));
        }
        try {
            return status(HttpStatus.CREATED, sharing.shareOrInvite(uid(), pk, email, role));
        } catch (PersonalBudgetAccess.Invalid e) {
            return status(HttpStatus.BAD_REQUEST, detail(e.getMessage()));
        } catch (PersonalBudgetAccess.Denied e) {
            return status(HttpStatus.NOT_FOUND, detail("Budget not found."));
        }
    }

    @DeleteMapping("/{pk}/invites/{invitePk}/")
    ResponseEntity<Object> cancelInvite(@PathVariable String pk, @PathVariable String invitePk) {
        try {
            return ResponseEntity.ok(sharing.cancelInvite(uid(), pk, invitePk));
        } catch (PersonalBudgetAccess.Denied e) {
            return status(HttpStatus.NOT_FOUND, detail(e.getMessage()));
        }
    }

    @PatchMapping("/{pk}/members/{memberPk}/")
    ResponseEntity<Object> updateMember(@PathVariable String pk, @PathVariable String memberPk,
            @RequestBody(required = false) Map<String, Object> raw) {
        Map<String, Object> data = body(raw);
        String role = (Py.truthy(data.get("role")) ? Py.str(data.get("role")) : "").strip().toLowerCase();
        if (!PersonalBudgetMember.ROLES.contains(role)) {
            return status(HttpStatus.BAD_REQUEST, detail("Invalid permission."));
        }
        try {
            return ResponseEntity.ok(sharing.updateMemberRole(uid(), pk, memberPk, role));
        } catch (PersonalBudgetAccess.Denied | PersonalBudgetAccess.Invalid e) {
            return status(HttpStatus.BAD_REQUEST, detail(e.getMessage()));
        }
    }

    @DeleteMapping("/{pk}/members/{memberPk}/")
    ResponseEntity<Object> removeMember(@PathVariable String pk, @PathVariable String memberPk) {
        try {
            return ResponseEntity.ok(sharing.removeMember(uid(), pk, memberPk));
        } catch (PersonalBudgetAccess.Denied e) {
            return status(HttpStatus.NOT_FOUND, detail(e.getMessage()));
        }
    }

    @PostMapping("/{pk}/categories/")
    ResponseEntity<Object> createCategory(@PathVariable String pk, @RequestBody(required = false) Map<String, Object> raw) {
        Map<String, Object> data = body(raw);
        String uid = uid();
        try {
            access.requireEdit(uid, pk);
        } catch (PersonalBudgetAccess.Denied e) {
            String msg = e.getMessage() == null || e.getMessage().isEmpty() ? "Budget not found." : e.getMessage();
            return status(msg.toLowerCase().contains("permission") ? HttpStatus.FORBIDDEN : HttpStatus.NOT_FOUND, detail(msg));
        }
        try {
            return ResponseEntity.ok(budgets.createCategory(pk, uid, data));
        } catch (PersonalBudgetAccess.Invalid e) {
            return status(HttpStatus.BAD_REQUEST, detail(e.getMessage()));
        }
    }

    @PatchMapping("/{budgetPk}/categories/{catPk}/")
    ResponseEntity<Object> updateCategory(@PathVariable String budgetPk, @PathVariable String catPk,
            @RequestBody(required = false) Map<String, Object> raw) {
        Map<String, Object> data = body(raw);
        try {
            return ResponseEntity.ok(budgets.updateCategory(uid(), budgetPk, catPk, data));
        } catch (PersonalBudgetAccess.Denied e) {
            return status(HttpStatus.NOT_FOUND, detail("Budget not found."));
        } catch (PersonalBudgetService.CategoryMissing e) {
            return status(HttpStatus.NOT_FOUND, detail("Category not found."));
        } catch (PersonalBudgetAccess.Invalid e) {
            return status(HttpStatus.BAD_REQUEST, detail(e.getMessage()));
        }
    }

    @DeleteMapping("/{budgetPk}/categories/{catPk}/")
    ResponseEntity<Object> deleteCategory(@PathVariable String budgetPk, @PathVariable String catPk) {
        try {
            return ResponseEntity.ok(budgets.deleteCategory(uid(), budgetPk, catPk));
        } catch (PersonalBudgetAccess.Denied e) {
            return status(HttpStatus.NOT_FOUND, detail("Budget not found."));
        } catch (PersonalBudgetService.CategoryMissing e) {
            return status(HttpStatus.NOT_FOUND, detail("Category not found."));
        }
    }
}
