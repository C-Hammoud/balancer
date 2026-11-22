import { CampaignAudience } from '../../core/models';
import { FLAG_LABEL } from './labels';

const LAST_LOGIN_TEXT: Record<string, string> = {
  never: 'never signed in',
  '30': 'no sign-in for 30 days',
  '90': 'no sign-in for 90 days',
  '180': 'no sign-in for 180 days',
};

/** One line describing who a campaign goes to. */
export function audienceSummary(a: CampaignAudience | null | undefined): string {
  if (!a || !a.type) return 'All active users';
  if (a.type === 'all') return 'All active users';
  if (a.type === 'users') {
    const n = a.user_ids?.length ?? 0;
    return `${n} chosen user${n === 1 ? '' : 's'}`;
  }
  const parts: string[] = [];
  if (a.flags?.length) parts.push(a.flags.map((f) => FLAG_LABEL[f] ?? f).join(' or '));
  if (a.countries?.length) parts.push(`in ${a.countries.join(', ')}`);
  if (a.currencies?.length) parts.push(`using ${a.currencies.join(', ')}`);
  if (a.verified === 'yes') parts.push('email verified');
  if (a.verified === 'no') parts.push('email not verified');
  if (a.joined_from || a.joined_to) parts.push(`joined ${a.joined_from || '…'} – ${a.joined_to || '…'}`);
  if (a.last_login) parts.push(LAST_LOGIN_TEXT[a.last_login] ?? a.last_login);
  return parts.length ? `Active users: ${parts.join('; ')}` : 'All active users';
}

/** "SA, ae ,LB" → ["SA", "AE", "LB"]. */
export function parseCodes(text: string): string[] {
  return [...new Set((text || '').split(/[\s,;]+/).map((c) => c.trim().toUpperCase()).filter(Boolean))];
}

/** A datetime-local value ("2026-12-01T09:00") as an ISO string with the browser's offset. */
export function localInputToIso(value: string): string | null {
  if (!value) return null;
  const d = new Date(value);
  return isNaN(d.getTime()) ? null : d.toISOString();
}
