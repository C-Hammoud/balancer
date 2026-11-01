package com.financetracker.finance.application;

import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import com.financetracker.access.api.UserDirectory;
import com.financetracker.access.api.UserSummary;
import com.financetracker.shared.config.AppProperties;

/**
 * Scheduled replacements for the Django management commands (process_budget_alerts,
 * send_commitment_reminders, review_budget_plans). Schedules are configurable; run with
 * JOBS_ENABLED=false on all but one instance until a distributed lock is added.
 */
@Component
class FinanceJobs {

    private static final Logger log = LoggerFactory.getLogger(FinanceJobs.class);

    private final AlertService alerts;
    private final CommitmentScheduleService schedules;
    private final PlanTriggerService planTriggers;
    private final UserDirectory users;
    private final AppProperties props;

    FinanceJobs(AlertService alerts, CommitmentScheduleService schedules, PlanTriggerService planTriggers,
            UserDirectory users, AppProperties props) {
        this.alerts = alerts;
        this.schedules = schedules;
        this.planTriggers = planTriggers;
        this.users = users;
        this.props = props;
    }

    /** "Suggested schedule: every 15–60 minutes" (process_budget_alerts). */
    @Scheduled(fixedDelayString = "${app.jobs.budget-alerts-delay:PT30M}", initialDelayString = "${app.jobs.initial-delay:PT60S}")
    void processBudgetAlerts() {
        if (!props.getJobs().isEnabled()) {
            return;
        }
        Map<String, Integer> stats = alerts.process(null);
        log.info("Processed {} user(s); sent {} alert email(s); {} error(s).",
                stats.get("users"), stats.get("emails_sent"), stats.get("errors"));
    }

    /** send_commitment_reminders (daily). */
    @Scheduled(cron = "${app.jobs.commitment-reminders-cron:0 0 7 * * *}")
    void sendCommitmentReminders() {
        if (!props.getJobs().isEnabled()) {
            return;
        }
        int sent = schedules.evaluateReminders(users.findAll().stream().filter(UserSummary::active).toList());
        log.info("Sent {} commitment reminder email(s).", sent);
    }

    /** review_budget_plans ("Run daily, e.g. at 08:00"). */
    @Scheduled(cron = "${app.jobs.review-plans-cron:0 0 8 * * *}")
    void reviewBudgetPlans() {
        if (!props.getJobs().isEnabled()) {
            return;
        }
        Map<String, Integer> totals = planTriggers.reviewAll();
        log.info("Reviewed {} user(s): {} monthly, {} income-change, {} overspending notification(s); {} error(s).",
                totals.get("users"), totals.get("monthly"), totals.get("income_change"), totals.get("overspending"),
                totals.get("errors"));
    }
}
