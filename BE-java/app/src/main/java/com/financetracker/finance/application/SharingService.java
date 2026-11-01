package com.financetracker.finance.application;

import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;

import org.springframework.stereotype.Service;

import com.financetracker.access.api.UserDirectory;
import com.financetracker.access.api.UserSummary;
import com.financetracker.finance.domain.FinanceRepositories.PersonalBudgetInviteRepository;
import com.financetracker.finance.domain.FinanceRepositories.PersonalBudgetMemberRepository;
import com.financetracker.finance.domain.FinanceRepositories.PersonalBudgetNotificationRepository;
import com.financetracker.finance.domain.FinanceRepositories.PersonalBudgetRepository;
import com.financetracker.finance.domain.PersonalBudget;
import com.financetracker.finance.domain.PersonalBudgetInvite;
import com.financetracker.finance.domain.PersonalBudgetMember;
import com.financetracker.finance.domain.PersonalBudgetNotification;
import com.financetracker.notifications.api.TransactionalEmails;
import com.financetracker.shared.web.Py;

/** Port of budgeting/personal_budget_sharing_service.py: share by email, invites, members. */
@Service
public class SharingService {

    private final PersonalBudgetRepository budgets;
    private final PersonalBudgetMemberRepository members;
    private final PersonalBudgetInviteRepository invites;
    private final PersonalBudgetNotificationRepository notifications;
    private final PersonalBudgetAccess access;
    private final PersonalBudgetService budgetService;
    private final UserDirectory users;
    private final TransactionalEmails emails;
    private final Clock clock;

    public SharingService(PersonalBudgetRepository budgets, PersonalBudgetMemberRepository members,
            PersonalBudgetInviteRepository invites, PersonalBudgetNotificationRepository notifications,
            PersonalBudgetAccess access, PersonalBudgetService budgetService, UserDirectory users,
            TransactionalEmails emails, Clock clock) {
        this.budgets = budgets;
        this.members = members;
        this.invites = invites;
        this.notifications = notifications;
        this.access = access;
        this.budgetService = budgetService;
        this.users = users;
        this.emails = emails;
        this.clock = clock;
    }

    /** _user_display: {"id", "email", "name", "username"}. */
    static Map<String, Object> display(UserSummary u) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", u.id());
        m.put("email", u.email() == null ? "" : u.email());
        m.put("name", displayName(u));
        m.put("username", u.username());
        return m;
    }

    static String displayName(UserSummary u) {
        StringBuilder sb = new StringBuilder();
        if (u.firstName() != null && !u.firstName().isEmpty()) {
            sb.append(u.firstName());
        }
        if (u.lastName() != null && !u.lastName().isEmpty()) {
            if (sb.length() > 0) {
                sb.append(' ');
            }
            sb.append(u.lastName());
        }
        String name = sb.toString().strip();
        return name.isEmpty() ? u.username() : name;
    }

    private static String normalizeEmail(String email) {
        return email == null ? "" : email.strip().toLowerCase(Locale.ROOT);
    }

    private static Map<String, Object> unknownOwner(String userId) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", userId);
        m.put("email", "");
        m.put("name", "");
        return m;
    }

    /** Whether an email belongs to a registered user (no other details are returned). */
    public boolean emailHasAccount(String email) {
        String e = normalizeEmail(email);
        return !e.isEmpty() && users.findByEmail(e).isPresent();
    }

    private List<Map<String, Object>> pendingInvites(String budgetId) {
        List<Map<String, Object>> out = new ArrayList<>();
        for (PersonalBudgetInvite inv : invites.listByBudget(budgetId)) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", inv.id);
            m.put("email", inv.email);
            m.put("role", inv.role);
            m.put("pending", true);
            m.put("created_at", Py.isoformat(inv.createdAt));
            out.add(m);
        }
        return out;
    }

    public Map<String, Object> listMembers(String ownerId, String budgetId) {
        PersonalBudget budget = access.requireOwner(ownerId, budgetId);
        Optional<UserSummary> owner = users.findById(budget.userId);
        List<Map<String, Object>> rows = new ArrayList<>();
        for (PersonalBudgetMember m : members.listByBudget(budgetId)) {
            Optional<UserSummary> u = users.findById(m.userId);
            if (u.isEmpty()) {
                continue;
            }
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("id", m.id);
            row.put("user_id", m.userId);
            row.put("email", u.get().email() == null ? "" : u.get().email());
            row.put("name", displayName(u.get()));
            row.put("role", m.role);
            row.put("pending", false);
            row.put("created_at", Py.isoformat(m.createdAt));
            rows.add(row);
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("owner", owner.map(SharingService::display).orElseGet(() -> unknownOwner(budget.userId)));
        out.put("members", rows);
        out.put("pending_invites", pendingInvites(budgetId));
        return out;
    }

    private void grantAndNotify(UserSummary owner, UserSummary target, PersonalBudget budget, String budgetId, String role) {
        PersonalBudgetMember member = new PersonalBudgetMember();
        member.budgetId = budgetId;
        member.userId = target.userId();
        member.role = role;
        members.save(member);
        String sharerName = displayName(owner);
        String permLabel = PersonalBudgetMember.VIEWER.equals(role) ? "Viewer" : "Editor";
        PersonalBudgetNotification n = new PersonalBudgetNotification();
        n.recipientId = target.userId();
        n.budgetId = budgetId;
        n.sharedById = owner.userId();
        n.role = role;
        n.title = sharerName + " shared \"" + budget.name + "\" with you";
        n.message = "Permission: " + permLabel;
        notifications.save(n);
        emails.budgetShared(CommitmentScheduleService.recipient(target), CommitmentScheduleService.recipient(owner),
                budget.name, budgetId, role);
    }

    private UserSummary user(String userId) {
        return users.findById(userId).orElseThrow(() -> new PersonalBudgetAccess.Denied("Budget not found."));
    }

    public Map<String, Object> shareWithRegisteredUser(String ownerId, String budgetId, String email, String role) {
        if (!PersonalBudgetMember.ROLES.contains(role)) {
            throw new PersonalBudgetAccess.Invalid("Invalid permission. Choose Viewer or Editor.");
        }
        PersonalBudget budget = access.requireOwner(ownerId, budgetId);
        String emailNorm = normalizeEmail(email);
        UserSummary target = users.findByEmail(emailNorm)
                .orElseThrow(() -> new PersonalBudgetAccess.Invalid("user_not_found"));
        if (target.userId().equals(ownerId)) {
            throw new PersonalBudgetAccess.Invalid("You already own this budget.");
        }
        if (members.getForBudgetUser(budgetId, target.userId()).isPresent()) {
            throw new PersonalBudgetAccess.Invalid("This user already has access to this budget.");
        }
        invites.getForBudgetEmail(budgetId, emailNorm).ifPresent(invites::delete);
        grantAndNotify(user(ownerId), target, budget, budgetId, role);
        Map<String, Object> data = listMembers(ownerId, budgetId);
        data.put("result", "shared");
        return data;
    }

    public Map<String, Object> inviteExternalUser(String ownerId, String budgetId, String email, String role) {
        if (!PersonalBudgetMember.ROLES.contains(role)) {
            throw new PersonalBudgetAccess.Invalid("Invalid permission. Choose Viewer or Editor.");
        }
        PersonalBudget budget = access.requireOwner(ownerId, budgetId);
        String emailNorm = normalizeEmail(email);
        if (emailNorm.isEmpty()) {
            throw new PersonalBudgetAccess.Invalid("Email is required.");
        }
        UserSummary owner = user(ownerId);
        if (emailNorm.equals(normalizeEmail(owner.email()))) {
            throw new PersonalBudgetAccess.Invalid("You already own this budget.");
        }
        if (users.findByEmail(emailNorm).isPresent()) {
            throw new PersonalBudgetAccess.Invalid("This email belongs to a registered user. Share directly instead.");
        }
        PersonalBudgetInvite invite = invites.getForBudgetEmail(budgetId, emailNorm).orElse(null);
        if (invite != null) {
            invite.role = role;
            invite.invitedById = ownerId;
        } else {
            invite = new PersonalBudgetInvite();
            invite.budgetId = budgetId;
            invite.email = emailNorm;
            invite.role = role;
            invite.invitedById = ownerId;
        }
        invites.save(invite);
        boolean sent = emails.budgetInvite(emailNorm, CommitmentScheduleService.recipient(owner), budget.name, budgetId, role);
        Map<String, Object> data = listMembers(ownerId, budgetId);
        data.put("result", "invited");
        data.put("email_sent", sent);
        data.put("invited_email", emailNorm);
        return data;
    }

    /** Share with a registered user, or send an invitation email. */
    public Map<String, Object> shareOrInvite(String ownerId, String budgetId, String email, String role) {
        String emailNorm = normalizeEmail(email);
        if (!emailNorm.isEmpty() && users.findByEmail(emailNorm).isPresent()) {
            return shareWithRegisteredUser(ownerId, budgetId, emailNorm, role);
        }
        return inviteExternalUser(ownerId, budgetId, emailNorm, role);
    }

    public Map<String, Object> cancelInvite(String ownerId, String budgetId, String inviteId) {
        access.requireOwner(ownerId, budgetId);
        PersonalBudgetInvite invite = invites.get(inviteId).filter(i -> budgetId.equals(i.budgetId))
                .orElseThrow(() -> new PersonalBudgetAccess.Denied("Invitation not found."));
        invites.delete(invite);
        return listMembers(ownerId, budgetId);
    }

    /** After email verification: turn pending invites for the address into memberships. */
    public int acceptPendingInvites(String userId, String email) {
        String e = normalizeEmail(email);
        if (e.isEmpty()) {
            return 0;
        }
        Optional<UserSummary> target = users.findById(userId);
        if (target.isEmpty()) {
            return 0;
        }
        int count = 0;
        for (PersonalBudgetInvite inv : invites.listByEmail(e)) {
            Optional<PersonalBudget> budget = budgets.get(inv.budgetId);
            if (budget.isEmpty() || members.getForBudgetUser(inv.budgetId, userId).isPresent()) {
                invites.delete(inv);
                continue;
            }
            Optional<UserSummary> owner = users.findById(budget.get().userId);
            if (owner.isEmpty()) {
                invites.delete(inv);
                continue;
            }
            grantAndNotify(owner.get(), target.get(), budget.get(), inv.budgetId, inv.role);
            invites.delete(inv);
            count++;
        }
        return count;
    }

    public Map<String, Object> updateMemberRole(String ownerId, String budgetId, String memberId, String role) {
        if (!PersonalBudgetMember.ROLES.contains(role)) {
            throw new PersonalBudgetAccess.Invalid("Invalid permission.");
        }
        access.requireOwner(ownerId, budgetId);
        PersonalBudgetMember m = members.get(memberId).filter(x -> budgetId.equals(x.budgetId))
                .orElseThrow(() -> new PersonalBudgetAccess.Denied("Member not found."));
        m.role = role;
        members.save(m);
        return listMembers(ownerId, budgetId);
    }

    public Map<String, Object> removeMember(String ownerId, String budgetId, String memberId) {
        access.requireOwner(ownerId, budgetId);
        PersonalBudgetMember m = members.get(memberId).filter(x -> budgetId.equals(x.budgetId))
                .orElseThrow(() -> new PersonalBudgetAccess.Denied("Member not found."));
        members.delete(m);
        return listMembers(ownerId, budgetId);
    }

    public List<Map<String, Object>> sharedWithMe(String userId) {
        List<Map<String, Object>> out = new ArrayList<>();
        for (PersonalBudgetMember m : members.listByUser(userId)) {
            Optional<PersonalBudget> budget = budgets.get(m.budgetId);
            if (budget.isEmpty()) {
                continue;
            }
            Map<String, Object> summary = budgetService.summary(budget.get(), userId, false, m.role);
            summary.put("is_owner", false);
            summary.put("owner", users.findById(budget.get().userId).map(SharingService::display)
                    .orElseGet(() -> unknownOwner(budget.get().userId)));
            out.add(summary);
        }
        return out;
    }

    public List<Map<String, Object>> listNotifications(String userId, int limit) {
        List<Map<String, Object>> rows = new ArrayList<>();
        for (PersonalBudgetNotification n : notifications.listForRecipient(userId, limit)) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", n.id);
            m.put("budget_id", n.budgetId);
            m.put("budget_name", budgets.get(n.budgetId).map(b -> b.name).orElse(""));
            m.put("title", n.title);
            m.put("message", n.message == null ? "" : n.message);
            m.put("role", n.role);
            m.put("shared_by", users.findById(n.sharedById).map(SharingService::display).orElse(null));
            m.put("read", n.readAt != null);
            m.put("created_at", Py.isoformat(n.createdAt));
            rows.add(m);
        }
        return rows;
    }

    public void markNotificationRead(String userId, String notificationId) {
        PersonalBudgetNotification n = notifications.get(notificationId).filter(x -> userId.equals(x.recipientId))
                .orElseThrow(() -> new PersonalBudgetAccess.Denied("Notification not found."));
        n.readAt = Instant.now(clock);
        notifications.save(n);
    }
}
