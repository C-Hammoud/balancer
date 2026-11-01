package com.financetracker.finance.application;

import java.util.Optional;

import org.springframework.stereotype.Component;

import com.financetracker.finance.domain.FinanceRepositories.PersonalBudgetMemberRepository;
import com.financetracker.finance.domain.FinanceRepositories.PersonalBudgetRepository;
import com.financetracker.finance.domain.PersonalBudget;
import com.financetracker.finance.domain.PersonalBudgetMember;

/** Port of budgeting/personal_budget_access.py (owner / editor / viewer). */
@Component
public class PersonalBudgetAccess {

    /** Python PermissionError: no access, or not enough access. */
    public static class Denied extends RuntimeException {
        public Denied(String message) {
            super(message);
        }
    }

    /** Python ValueError raised by the budget services (shown as 400 {"detail": ...}). */
    public static class Invalid extends RuntimeException {
        public Invalid(String message) {
            super(message);
        }
    }

    public record Access(PersonalBudget budget, String role) {
    }

    private final PersonalBudgetRepository budgets;
    private final PersonalBudgetMemberRepository members;

    public PersonalBudgetAccess(PersonalBudgetRepository budgets, PersonalBudgetMemberRepository members) {
        this.budgets = budgets;
        this.members = members;
    }

    public Optional<String> memberRole(String userId, String budgetId) {
        return members.getForBudgetUser(budgetId, userId).map(m ->
                PersonalBudgetMember.ROLES.contains(m.role) ? m.role : PersonalBudgetMember.VIEWER);
    }

    public Optional<Access> resolve(String userId, String budgetId) {
        Optional<PersonalBudget> budget = budgets.get(budgetId);
        if (budget.isEmpty()) {
            return Optional.empty();
        }
        if (String.valueOf(budget.get().userId).equals(userId)) {
            return Optional.of(new Access(budget.get(), PersonalBudgetMember.OWNER));
        }
        return memberRole(userId, budgetId).map(role -> new Access(budget.get(), role));
    }

    public Access requireView(String userId, String budgetId) {
        return resolve(userId, budgetId).orElseThrow(() -> new Denied("Budget not found."));
    }

    public Access requireEdit(String userId, String budgetId) {
        Access a = requireView(userId, budgetId);
        if (!canEdit(a.role())) {
            throw new Denied("You do not have permission to edit this budget.");
        }
        return a;
    }

    public PersonalBudget requireOwner(String userId, String budgetId) {
        Access a = requireView(userId, budgetId);
        if (!PersonalBudgetMember.OWNER.equals(a.role())) {
            throw new Denied("Only the budget owner can perform this action.");
        }
        return a.budget();
    }

    public static boolean canEdit(String role) {
        return PersonalBudgetMember.OWNER.equals(role) || PersonalBudgetMember.EDITOR.equals(role);
    }
}
