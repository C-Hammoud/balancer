package com.financetracker.access.domain;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/** Port of api.models.UserProfile (one row per user). */
@Entity
@Table(name = "access_user_profiles")
public class UserProfile {

    public static final String SETUP_PENDING = "pending";
    public static final String SETUP_INCOMPLETE = "incomplete";
    public static final String SETUP_COMPLETE = "complete";

    @Id
    private Long userId;

    @Column(nullable = false)
    private boolean emailVerified;
    private Instant emailVerifiedAt;
    @Column(nullable = false, length = 32)
    private String phone = "";
    @Column(nullable = false, length = 20)
    private String setupStatus = SETUP_PENDING;
    private Instant setupSkippedAt;
    private Instant setupCompletedAt;
    private Instant setupNudgePushDueAt;
    private Instant setupNudgeEmailDueAt;
    private Instant setupNudgePushSentAt;
    private Instant setupNudgeEmailSentAt;
    @Column(nullable = false)
    private boolean notifyWeeklySummaries = true;
    @Column(nullable = false)
    private boolean notifyLowBalance = true;
    @Column(nullable = false)
    private boolean notifySetupNudges = true;
    @Column(nullable = false)
    private boolean notifyPlanUpdates = true;
    @Column(nullable = false)
    private int savingsTargetPct = 20;

    protected UserProfile() {
    }

    public UserProfile(Long userId) {
        this.userId = userId;
    }

    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }
    public boolean isEmailVerified() { return emailVerified; }
    public void setEmailVerified(boolean v) { this.emailVerified = v; }
    public Instant getEmailVerifiedAt() { return emailVerifiedAt; }
    public void setEmailVerifiedAt(Instant v) { this.emailVerifiedAt = v; }
    public String getPhone() { return phone; }
    public void setPhone(String v) { this.phone = v == null ? "" : v; }
    public String getSetupStatus() { return setupStatus; }
    public void setSetupStatus(String v) { this.setupStatus = v; }
    public Instant getSetupSkippedAt() { return setupSkippedAt; }
    public void setSetupSkippedAt(Instant v) { this.setupSkippedAt = v; }
    public Instant getSetupCompletedAt() { return setupCompletedAt; }
    public void setSetupCompletedAt(Instant v) { this.setupCompletedAt = v; }
    public Instant getSetupNudgePushDueAt() { return setupNudgePushDueAt; }
    public void setSetupNudgePushDueAt(Instant v) { this.setupNudgePushDueAt = v; }
    public Instant getSetupNudgeEmailDueAt() { return setupNudgeEmailDueAt; }
    public void setSetupNudgeEmailDueAt(Instant v) { this.setupNudgeEmailDueAt = v; }
    public Instant getSetupNudgePushSentAt() { return setupNudgePushSentAt; }
    public void setSetupNudgePushSentAt(Instant v) { this.setupNudgePushSentAt = v; }
    public Instant getSetupNudgeEmailSentAt() { return setupNudgeEmailSentAt; }
    public void setSetupNudgeEmailSentAt(Instant v) { this.setupNudgeEmailSentAt = v; }
    public boolean isNotifyWeeklySummaries() { return notifyWeeklySummaries; }
    public void setNotifyWeeklySummaries(boolean v) { this.notifyWeeklySummaries = v; }
    public boolean isNotifyLowBalance() { return notifyLowBalance; }
    public void setNotifyLowBalance(boolean v) { this.notifyLowBalance = v; }
    public boolean isNotifySetupNudges() { return notifySetupNudges; }
    public void setNotifySetupNudges(boolean v) { this.notifySetupNudges = v; }
    public boolean isNotifyPlanUpdates() { return notifyPlanUpdates; }
    public void setNotifyPlanUpdates(boolean v) { this.notifyPlanUpdates = v; }
    public int getSavingsTargetPct() { return savingsTargetPct; }
    public void setSavingsTargetPct(int v) { this.savingsTargetPct = v; }
}
