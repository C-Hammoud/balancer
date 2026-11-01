/** Shared labels for the Admin and Help & support pages. */
export const TICKET_STATUS_LABEL: Record<string, string> = {
  open: 'Open',
  waiting_user: 'Waiting for user',
  resolved: 'Resolved, awaiting confirmation',
  closed: 'Closed',
};

export const CLOSE_REASON_LABEL: Record<string, string> = {
  user_confirmed: 'confirmed fixed by the user',
  auto: 'closed automatically (no answer)',
};

export const TICKET_CATEGORY_LABEL: Record<string, string> = {
  account: 'Account & sign-in',
  bug: 'Something is broken',
  data: 'My data',
  other: 'Other',
};

export const FLAG_LABEL: Record<string, string> = {
  deactivated: 'Deactivated',
  email_failed: 'Email failed',
  open_ticket: 'Open ticket',
  high_risk: 'High risk',
  email_unverified: 'Unverified',
  setup_stuck: 'Setup stuck',
  no_activity: 'No activity',
};

export const AUDIT_ACTION_LABEL: Record<string, string> = {
  view_user: 'Viewed user',
  resend_verification: 'Resent verification',
  mark_verified: 'Marked verified',
  send_reset: 'Sent password reset',
  deactivate: 'Deactivated',
  reactivate: 'Reactivated',
  grant_staff: 'Made admin',
  revoke_staff: 'Removed admin',
  ticket_reply: 'Replied to ticket',
  ticket_status: 'Updated ticket',
  ticket_assign: 'Assigned ticket',
  ticket_resolved: 'Marked resolved',
  ticket_reopened: 'User said not fixed',
  ticket_closed: 'Closed ticket',
  support_settings: 'Changed support settings',
};

/** Pill class for a ticket status. */
export function statusClass(status: string): string {
  if (status === 'open') return 'warn';
  if (status === 'waiting_user' || status === 'resolved') return 'ok';
  return 'muted';
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}
