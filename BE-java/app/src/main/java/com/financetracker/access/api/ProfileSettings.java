package com.financetracker.access.api;

/** Notification switches and planner settings from the user's profile. */
public record ProfileSettings(
        boolean emailVerified,
        boolean notifyWeeklySummaries,
        boolean notifyLowBalance,
        boolean notifySetupNudges,
        boolean notifyPlanUpdates,
        int savingsTargetPct) {
}
