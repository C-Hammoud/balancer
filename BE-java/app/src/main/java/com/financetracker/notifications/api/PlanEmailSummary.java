package com.financetracker.notifications.api;

import java.math.BigDecimal;
import java.util.List;

/** The parts of a suggested budget plan shown in the plan email. */
public record PlanEmailSummary(
        int year,
        int month,
        String currency,
        BigDecimal incomeTotal,
        BigDecimal commitmentsTotal,
        BigDecimal needsTotal,
        BigDecimal wantsTotal,
        BigDecimal savingsAmount,
        String savingsPct,
        List<String> warnings) {
}
