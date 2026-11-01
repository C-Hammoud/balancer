package com.financetracker.access.application;

import java.time.Clock;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import com.financetracker.access.domain.AccessRepositories.UserAccountRepository;
import com.financetracker.access.domain.AccessRepositories.UserProfileRepository;
import com.financetracker.access.domain.UserProfile;
import com.financetracker.notifications.api.TransactionalEmails;
import com.financetracker.shared.config.AppProperties;

/**
 * Port of process_setup_nudges (manage.py send_setup_nudges / the dev self-ping loop):
 * "push" nudges are only logged (no push provider yet), email nudges are sent.
 */
@Component
public class SetupNudgeJob {

    private static final Logger log = LoggerFactory.getLogger(SetupNudgeJob.class);
    static final String SETUP_PUSH_COPY = "Finish setting up your wallet to start tracking your daily expenses!";

    private final UserProfileRepository profiles;
    private final UserAccountRepository users;
    private final TransactionalEmails emails;
    private final AppProperties props;
    private final Clock clock;

    public SetupNudgeJob(UserProfileRepository profiles, UserAccountRepository users, TransactionalEmails emails,
            AppProperties props, Clock clock) {
        this.profiles = profiles;
        this.users = users;
        this.emails = emails;
        this.props = props;
        this.clock = clock;
    }

    @Scheduled(fixedDelayString = "${app.jobs.setup-nudges-delay:PT100S}", initialDelayString = "${app.jobs.initial-delay:PT60S}")
    public void scheduled() {
        if (!props.getJobs().isEnabled()) {
            return;
        }
        try {
            process(25);
        } catch (RuntimeException e) {
            log.warn("Setup nudges failed", e);
        }
    }

    public Map<String, Integer> process(int limit) {
        Instant now = Instant.now(clock);
        List<UserProfile> candidates = profiles.findBySetupStatusAndNotifySetupNudgesTrue(UserProfile.SETUP_INCOMPLETE);
        int push = 0;
        for (UserProfile p : candidates.stream()
                .filter(p -> p.getSetupNudgePushDueAt() != null && !p.getSetupNudgePushDueAt().isAfter(now)
                        && p.getSetupNudgePushSentAt() == null)
                .limit(limit).toList()) {
            log.info("Setup nudge (push) for user {}: {}", p.getUserId(), SETUP_PUSH_COPY);
            p.setSetupNudgePushSentAt(now);
            profiles.save(p);
            push++;
        }
        int sent = 0;
        for (UserProfile p : candidates.stream()
                .filter(p -> p.getSetupNudgeEmailDueAt() != null && !p.getSetupNudgeEmailDueAt().isAfter(now)
                        && p.getSetupNudgeEmailSentAt() == null)
                .limit(limit).toList()) {
            users.findById(p.getUserId()).ifPresent(u -> emails.setupNudge(ProfileService.recipient(u)));
            p.setSetupNudgeEmailSentAt(now);
            profiles.save(p);
            sent++;
        }
        Map<String, Integer> result = new LinkedHashMap<>();
        result.put("push_logged", push);
        result.put("emails_sent", sent);
        return result;
    }
}
