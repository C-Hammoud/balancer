package com.financetracker.notifications.api;

/**
 * Transactional emails (port of api/emails.py). Each returns whether the message was handed to
 * the mail server, like the Django functions; callers that ignored the result may keep doing so.
 */
public interface TransactionalEmails {

    boolean welcomeAndVerification(EmailRecipient to, String verifyUrl, String mobileVerifyUrl);

    boolean verification(EmailRecipient to, String verifyUrl, String mobileVerifyUrl);

    boolean setupNudge(EmailRecipient to);

    boolean passwordReset(EmailRecipient to, String resetUrl, String appUrl);

    boolean budgetShared(EmailRecipient to, EmailRecipient sharedBy, String budgetName, String budgetId, String role);

    boolean budgetInvite(String recipientEmail, EmailRecipient sharedBy, String budgetName, String budgetId, String role);

    boolean budgetAlert(EmailRecipient to, String title, String description, String severity);

    boolean commitmentReminder(EmailRecipient to, String commitmentName, String dueDate, String amount, int sequence);

    boolean planSuggestion(EmailRecipient to, PlanEmailSummary plan, String headline, String intro, String linkPath);
}
