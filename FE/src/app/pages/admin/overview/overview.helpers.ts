import { AdminDashboard, ChannelStats, DailyCount, OverviewCampaign } from '../../../core/models';

export type Tone = 'good' | 'bad' | 'flat';

export interface Change {
  /** "+12 vs previous 30 days", "Same as previous 7 days", "New" */
  text: string;
  tone: Tone;
}

/**
 * A number against the period before. `upIsGood` says which direction is green:
 * more sign-ups is good, more failed emails is bad.
 */
export function periodChange(current: number, previous: number, days: number, upIsGood = true): Change {
  const diff = current - previous;
  const period = `previous ${days} days`;
  if (diff === 0) return { text: `Same as ${period}`, tone: 'flat' };
  const pct = previous > 0 ? ` (${diff > 0 ? '+' : ''}${Math.round((diff / previous) * 100)}%)` : '';
  const good = diff > 0 === upIsGood;
  return { text: `${diff > 0 ? '+' : ''}${diff}${pct} vs ${period}`, tone: good ? 'good' : 'bad' };
}

/** Whole percent of part in total ("—" for an empty total). */
export function percent(part: number | null | undefined, total: number | null | undefined): string {
  if (part == null || !total) return '—';
  return `${Math.round((part / total) * 100)}%`;
}

/** 0.4 → "24 min", 5 → "5 h", 50 → "2.1 days". */
export function hoursText(hours: number | null | undefined): string {
  if (hours == null) return '—';
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} min`;
  if (hours < 48) return `${Math.round(hours * 10) / 10} h`;
  return `${Math.round((hours / 24) * 10) / 10} days`;
}

/** "just now", "3 min ago", "2 h ago" for the "Updated …" line. */
export function agoText(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return '';
  const ms = now - new Date(iso).getTime();
  if (isNaN(ms) || ms < 60_000) return 'just now';
  const min = Math.floor(ms / 60_000);
  if (min < 60) return `${min} min ago`;
  return `${Math.floor(min / 60)} h ago`;
}

/** A rounded axis maximum (1, 2, 5, 10, 20, 50, …) at or above the largest value. */
export function niceMax(values: number[]): number {
  const max = Math.max(0, ...values);
  if (max <= 1) return 1;
  const pow = 10 ** Math.floor(Math.log10(max));
  for (const step of [1, 2, 5, 10]) {
    if (step * pow >= max) return step * pow;
  }
  return 10 * pow;
}

export interface BarGeom {
  x: number;
  y: number;
  width: number;
  height: number;
  /** Hit area: the whole column, wider than the bar. */
  hitX: number;
  hitWidth: number;
}

/** Bars for a series in a width × height plot; 2px gap between bars, empty days have no bar. */
export function barGeometry(series: DailyCount[], width: number, height: number, max: number): BarGeom[] {
  const n = series.length || 1;
  const col = width / n;
  const gap = Math.min(2, col * 0.25);
  return series.map((d, i) => {
    const h = max > 0 ? (d.count / max) * height : 0;
    return { x: i * col + gap / 2, y: height - h, width: Math.max(1, col - gap), height: h, hitX: i * col, hitWidth: col };
  });
}

/** Points of a line series (the centre of each day's column). */
export function linePoints(series: DailyCount[], width: number, height: number, max: number): { x: number; y: number }[] {
  const n = series.length || 1;
  const col = width / n;
  return series.map((d, i) => ({ x: i * col + col / 2, y: max > 0 ? height - (d.count / max) * height : height }));
}

export function pointsAttr(points: { x: number; y: number }[]): string {
  return points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
}

/** "Mon 3 Nov" for a YYYY-MM-DD day. */
export function dayLabel(date: string): string {
  const [y, m, d] = date.split('-').map(Number);
  const day = new Date(y, (m || 1) - 1, d || 1);
  return isNaN(day.getTime()) ? date : day.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
}

/** Read rate of in-app messages and click rate of emails for a campaign row. */
export function campaignRates(c: OverviewCampaign): { read: string; clicked: string } {
  const inApp: Partial<ChannelStats> = c.stats.by_channel.in_app ?? {};
  const email: Partial<ChannelStats> = c.stats.by_channel.email ?? {};
  return { read: percent(inApp.read ?? null, inApp.sent ?? 0), clicked: percent(email.clicked ?? null, email.sent ?? 0) };
}

export interface AttentionItem {
  key: string;
  label: string;
  count: number;
  severity: 'high' | 'warn';
  link: string;
  query?: Record<string, string>;
}

/** The problems with a non-zero count, most urgent first. */
export function attentionItems(d: AdminDashboard): AttentionItem[] {
  const items: AttentionItem[] = [
    { key: 'pool', label: 'Tickets in the pool', count: d.tickets_pool, severity: 'high', link: '/admin/tickets', query: { view: 'pool' } },
    { key: 'mine', label: 'My open tickets', count: d.my_open_tickets, severity: 'warn', link: '/admin/tickets', query: { view: 'mine' } },
    {
      key: 'stuck', label: 'Campaigns stuck sending', count: d.messaging?.stuck ?? 0, severity: 'high',
      link: '/admin/notifications', query: { status: 'sending' },
    },
    {
      key: 'email_failed', label: 'Failed emails (7 days)', count: d.emails_failed_7d, severity: 'high',
      link: '/admin/users', query: { pool: 'attention', flag: 'email_failed' },
    },
    {
      key: 'email_unverified', label: 'Unverified after 24 h', count: d.email_unverified, severity: 'warn',
      link: '/admin/users', query: { pool: 'attention', flag: 'email_unverified' },
    },
    {
      key: 'setup_stuck', label: 'Setup not finished', count: d.setup_stuck, severity: 'warn',
      link: '/admin/users', query: { pool: 'attention', flag: 'setup_stuck' },
    },
  ];
  return items.filter((i) => i.count > 0);
}
