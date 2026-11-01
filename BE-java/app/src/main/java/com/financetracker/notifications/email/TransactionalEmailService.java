package com.financetracker.notifications.email;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.financetracker.notifications.api.EmailRecipient;
import com.financetracker.notifications.api.PlanEmailSummary;
import com.financetracker.notifications.api.TransactionalEmails;
import com.financetracker.shared.config.AppProperties;
import com.financetracker.shared.web.Py;

/** Port of api/emails.py: same subjects, copy and links. */
@Service
class TransactionalEmailService implements TransactionalEmails {

    private static final Logger log = LoggerFactory.getLogger(TransactionalEmailService.class);

    private final EmailDelivery delivery;
    private final AppProperties props;

    TransactionalEmailService(EmailDelivery delivery, AppProperties props) {
        this.delivery = delivery;
        this.props = props;
    }

    private String frontend() {
        return props.getFrontendUrl();
    }

    private static String email(EmailRecipient r) {
        return r == null || r.email() == null ? "" : r.email().strip();
    }

    @Override
    public boolean welcomeAndVerification(EmailRecipient to, String verifyUrl, String mobileVerifyUrl) {
        String email = email(to);
        if (email.isEmpty()) {
            log.info("Welcome/verification email skipped: user {} has no email.", to.userId());
            return false;
        }
        String name = to.displayName("there");
        BrandedEmail content = new BrandedEmail(
                "Welcome to Finance Tracker — verify your email",
                "Confirm your email to start tracking budgets and expenses.",
                "Welcome, " + name + "!")
                .paragraph("Your Finance Tracker account is ready. Verify your email address to sign in and "
                        + "start planning budgets, tracking transactions, and reaching your financial goals.")
                .paragraph("This verification link expires after a while. If it stops working, request a new "
                        + "one from the sign-in page.")
                .cta("Verify email address", verifyUrl)
                .secondaryCta("Already have the app? Open Finance Tracker", mobileVerifyUrl)
                .secondaryNote("If you did not create this account, you can safely ignore this email.")
                .footerReason("You received this email because an account was registered with this address.");
        return delivery.send(content, List.of(email));
    }

    @Override
    public boolean verification(EmailRecipient to, String verifyUrl, String mobileVerifyUrl) {
        String email = email(to);
        if (email.isEmpty()) {
            return false;
        }
        String name = to.displayName("there");
        BrandedEmail content = new BrandedEmail(
                "Verify your Finance Tracker email",
                "Confirm your email to continue using Finance Tracker.",
                "Verify your email")
                .paragraph("Hello " + name + ",")
                .paragraph("Use the button below to verify your email address.")
                .cta("Verify email address", verifyUrl)
                .secondaryCta("Already have the app? Open Finance Tracker", mobileVerifyUrl)
                .secondaryNote("If you did not request this, you can ignore this email.")
                .footerReason("You received this because a verification was requested for your account.");
        return delivery.send(content, List.of(email));
    }

    @Override
    public boolean setupNudge(EmailRecipient to) {
        String email = email(to);
        if (email.isEmpty()) {
            return false;
        }
        String name = to.displayName("there");
        BrandedEmail content = new BrandedEmail(
                "Complete your profile to get a clear view of your monthly spending.",
                "Add a main account so income and expenses can be balanced.",
                "Finish setting up your wallet")
                .paragraph("Hello " + name + ",")
                .paragraph("You skipped adding a main account. Without one, income and expenses can't be balanced.")
                .paragraph("Add a bank, cash, or card account to start tracking daily spending.")
                .cta("Complete your profile", frontend() + "/login")
                .secondaryNote("You can also open Profile in the mobile app and tap the setup banner.")
                .footerReason("You received this because you skipped wallet setup. Turn off setup nudges in Profile to stop these emails.");
        return delivery.sendNotification(content, List.of(email));
    }

    @Override
    public boolean passwordReset(EmailRecipient to, String resetUrl, String appUrl) {
        String email = email(to);
        if (email.isEmpty()) {
            log.info("Password reset skipped: user {} has no email.", to.userId());
            return false;
        }
        String name = to.displayName("there");
        BrandedEmail content = new BrandedEmail(
                "Reset your Finance Tracker password",
                "Use this link to choose a new password. Link expires soon.",
                "Reset your password")
                .paragraph("Hello " + name + ",")
                .paragraph("We received a request to reset your Finance Tracker password. "
                        + "Click the button below to choose a new one.")
                .cta("Reset password", resetUrl)
                .secondaryNote("This link is valid for a limited time. If you did not request a reset, ignore this email.")
                .footerReason("You received this because a password reset was requested for your account.");
        if (appUrl != null && !appUrl.isEmpty()) {
            content.secondaryCta("Open in the Finance Tracker app", appUrl);
        }
        return delivery.send(content, List.of(email));
    }

    @Override
    public boolean budgetShared(EmailRecipient to, EmailRecipient sharedBy, String budgetName, String budgetId, String role) {
        String email = email(to);
        if (email.isEmpty()) {
            log.info("Budget share email skipped: recipient {} has no email.", to == null ? "?" : to.userId());
            return false;
        }
        String sharerName = sharedBy.sharerDisplay();
        String recipientName = to.displayName("there");
        String permLabel = "viewer".equals(role) ? "Viewer" : "Editor";
        String budgetUrl = frontend() + "/budgeting/budgets/" + budgetId;
        BrandedEmail content = new BrandedEmail(
                sharerName + " shared \"" + budgetName + "\" with you",
                "You have " + permLabel.toLowerCase(Locale.ROOT) + " access to this budget on Finance Tracker.",
                "A budget was shared with you")
                .paragraph("Hello " + recipientName + ",")
                .row("Shared by", sharerName)
                .row("Budget", budgetName)
                .row("Your access", permLabel)
                .cta("View budget", budgetUrl)
                .secondaryNote("After signing in, you can also find this budget under Budgets → Shared with me.")
                .footerReason("You received this because " + sharerName + " shared a budget with your account.");
        return delivery.send(content, List.of(email));
    }

    @Override
    public boolean budgetInvite(String recipientEmail, EmailRecipient sharedBy, String budgetName, String budgetId, String role) {
        String email = recipientEmail == null ? "" : recipientEmail.strip();
        if (email.isEmpty()) {
            return false;
        }
        String sharerName = sharedBy.sharerDisplay();
        String permLabel = "viewer".equals(role) ? "Viewer" : "Editor";
        String registerUrl = frontend() + "/register?email=" + Py.quote(email, "/");
        BrandedEmail content = new BrandedEmail(
                sharerName + " invited you to \"" + budgetName + "\"",
                "Create a free Finance Tracker account to accept this budget invitation.",
                "You're invited to collaborate")
                .paragraph(sharerName + " wants to share a personal budget with you on Finance Tracker — "
                        + "plan and track spending for trips, projects, and goals in one place.")
                .paragraph("Create an account with this email address to accept the invitation.")
                .row("Budget", budgetName)
                .row("Access level", permLabel)
                .row("Invited by", sharerName)
                .cta("Create account & accept", registerUrl)
                .secondaryNote("After you register and verify your email, the budget will appear under "
                        + "Budgets → Shared with me.")
                .footerReason("You received this because " + sharerName + " invited you to a shared budget.");
        return delivery.send(content, List.of(email));
    }

    @Override
    public boolean budgetAlert(EmailRecipient to, String title, String description, String severity) {
        String email = email(to);
        if (email.isEmpty()) {
            return false;
        }
        String desc = description == null ? "" : description;
        BrandedEmail content = new BrandedEmail(
                "Budget alert: " + title,
                !desc.isEmpty() ? desc.substring(0, Math.min(120, desc.length())) : "Review this alert in Finance Tracker.",
                title)
                .cta("Review alerts", frontend() + "/budgeting/alerts")
                .footerReason("You received this because a budget threshold or alert was triggered on your account.");
        if (!desc.isEmpty()) {
            content.paragraph(desc);
        }
        if (severity != null && !severity.isEmpty()) {
            content.row("Severity", pyTitle(severity));
        }
        return delivery.sendNotification(content, List.of(email));
    }

    @Override
    public boolean commitmentReminder(EmailRecipient to, String commitmentName, String dueDate, String amount, int sequence) {
        String email = email(to);
        if (email.isEmpty()) {
            return false;
        }
        BrandedEmail content = new BrandedEmail(
                "Payment reminder: " + commitmentName,
                "Installment #" + sequence + " is due soon.",
                "Upcoming commitment payment")
                .paragraph("A payment for \"" + commitmentName + "\" is due soon.")
                .row("Due date", dueDate)
                .row("Amount", amount)
                .row("Installment", "#" + sequence)
                .cta("View commitments", frontend() + "/budgeting/commitments")
                .footerReason("You received this because payment reminders are enabled for this commitment.");
        return delivery.sendNotification(content, List.of(email));
    }

    @Override
    public boolean planSuggestion(EmailRecipient to, PlanEmailSummary plan, String headline, String intro, String linkPath) {
        String email = email(to);
        if (email.isEmpty()) {
            return false;
        }
        String cur = plan.currency() == null ? "" : plan.currency();
        List<String> paragraphs = new ArrayList<>();
        paragraphs.add(intro);
        List<String> warnings = plan.warnings() == null ? List.of() : plan.warnings();
        for (String w : warnings.subList(0, Math.min(3, warnings.size()))) {
            paragraphs.add("Note: " + w);
        }
        String subject = headline + " (" + plan.year() + "-" + String.format("%02d", plan.month()) + ")";
        BrandedEmail content = new BrandedEmail(subject, intro.substring(0, Math.min(120, intro.length())), headline)
                .paragraphs(paragraphs)
                .row("Expected income", fmt(plan.incomeTotal(), cur))
                .row("Commitments due", fmt(plan.commitmentsTotal(), cur))
                .row("Needs", fmt(plan.needsTotal(), cur))
                .row("Wants", fmt(plan.wantsTotal(), cur))
                .row("Savings", fmt(plan.savingsAmount(), cur) + " (" + (plan.savingsPct() == null ? "0" : plan.savingsPct()) + "%)")
                .cta("Review the plan", frontend() + linkPath)
                .footerReason("You received this because budget plan updates are on. Turn them off in your profile.");
        return delivery.sendNotification(content, List.of(email));
    }

    /** f"{float(value):,.0f} {cur}".strip() */
    static String fmt(BigDecimal value, String cur) {
        double d = value == null ? 0d : value.doubleValue();
        BigDecimal rounded = new BigDecimal(d).setScale(0, RoundingMode.HALF_EVEN);
        DecimalFormat f = new DecimalFormat("#,##0", DecimalFormatSymbols.getInstance(Locale.US));
        return (f.format(rounded) + " " + cur).strip();
    }

    /** str.title() for single words such as "warning" / "critical". */
    static String pyTitle(String s) {
        StringBuilder sb = new StringBuilder(s.length());
        boolean prevLetter = false;
        for (char c : s.toCharArray()) {
            if (Character.isLetter(c)) {
                sb.append(prevLetter ? Character.toLowerCase(c) : Character.toUpperCase(c));
                prevLetter = true;
            } else {
                sb.append(c);
                prevLetter = false;
            }
        }
        return sb.toString();
    }
}
