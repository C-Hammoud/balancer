import { Commitment, UtilizationRow, YearlyMonthRow, YearlyOverview } from '../../core/models';

/** API amounts arrive as decimal strings; anything unreadable counts as 0. */
export function num(value: string | number | null | undefined): number {
  const n = typeof value === 'number' ? value : Number(value ?? 0);
  return Number.isFinite(n) ? n : 0;
}

/** Percent change from `previous` to `current`, or null when there is nothing to compare with. */
export function percentChange(current: string | number | null | undefined, previous: string | number | null | undefined): number | null {
  const prev = num(previous);
  if (!prev) return null;
  return ((num(current) - prev) / Math.abs(prev)) * 100;
}

/** Share of income kept: (income − expense) ÷ income, in percent; null without income. */
export function savingsRate(income: string | number | null | undefined, expense: string | number | null | undefined): number | null {
  const inc = num(income);
  if (inc <= 0) return null;
  return ((inc - Math.abs(num(expense))) / inc) * 100;
}

export function daysInMonth(year: number, month: number): number {
  return new Date(year, month, 0).getDate();
}

export interface SpendingPace {
  dailyAverage: number;
  /** Month-end spend at the current daily rate; only for the month in progress. */
  projected: number | null;
  isCurrentMonth: boolean;
}

/**
 * Spending pace for a month. The month in progress is divided by the days so far and projected
 * to its full length; a past (or future) month is divided by all of its days.
 */
export function spendingPace(expense: string | number | null | undefined, year: number, month: number, today: Date): SpendingPace {
  const spent = Math.abs(num(expense));
  const total = daysInMonth(year, month);
  const isCurrentMonth = today.getFullYear() === year && today.getMonth() + 1 === month;
  if (isCurrentMonth) {
    const elapsed = Math.max(1, today.getDate());
    const dailyAverage = spent / elapsed;
    return { dailyAverage, projected: dailyAverage * total, isCurrentMonth };
  }
  return { dailyAverage: spent / total, projected: null, isCurrentMonth };
}

export type ProgressTone = 'ok' | 'warn' | 'critical' | 'none';

export interface BudgetProgress {
  /** actual ÷ forecast in percent; null without a forecast. */
  pct: number | null;
  /** Bar width in percent, capped at 100. */
  width: number;
  tone: ProgressTone;
}

const TONES: Record<string, ProgressTone> = {
  ok: 'ok',
  warn: 'warn',
  warning: 'warn',
  critical: 'critical',
  over: 'critical',
};

/**
 * Progress of one category against its budget. Without a budget the bar shows the category's
 * share of `totalSpend` in a neutral tone.
 */
export function budgetProgress(row: UtilizationRow, totalSpend: number): BudgetProgress {
  const actual = Math.abs(num(row.actual));
  const forecast = num(row.forecast);
  if (forecast <= 0) {
    const share = totalSpend > 0 ? (actual / totalSpend) * 100 : 0;
    return { pct: null, width: Math.min(100, share), tone: 'none' };
  }
  const pct = (actual / forecast) * 100;
  const tone = TONES[(row.status || '').toLowerCase()] ?? (pct > 100 ? 'critical' : 'ok');
  return { pct, width: Math.min(100, pct), tone };
}

export interface UpcomingPayment {
  commitment: Commitment;
  dueDate: string;
  /** Negative when overdue. */
  daysUntil: number;
}

function isoToLocalDate(iso: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
  return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null;
}

/** Commitments with a payment due within `days` (overdue ones included), soonest first. */
export function upcomingDue(commitments: Commitment[], today: Date, days = 30): UpcomingPayment[] {
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const dayMs = 24 * 60 * 60 * 1000;
  const out: UpcomingPayment[] = [];
  for (const c of commitments) {
    if (!c.next_due_date || !c.next_due_line_id) continue;
    const due = isoToLocalDate(c.next_due_date);
    if (!due) continue;
    const daysUntil = Math.round((due.getTime() - start.getTime()) / dayMs);
    if (daysUntil <= days) out.push({ commitment: c, dueDate: c.next_due_date.slice(0, 10), daysUntil });
  }
  return out.sort((a, b) => a.daysUntil - b.daysUntil || a.commitment.name.localeCompare(b.commitment.name));
}

/**
 * The month before (year, month): from this year's overview, or for January from the previous
 * year's December (pass that year's overview when it has been loaded).
 */
export function previousMonthRow(
  year: number,
  month: number,
  thisYear: YearlyOverview | null,
  previousYear: YearlyOverview | null
): YearlyMonthRow | null {
  if (month > 1) return thisYear?.months.find((r) => r.month === month - 1) ?? null;
  if (previousYear?.year !== year - 1) return null;
  return previousYear.months.find((r) => r.month === 12) ?? null;
}
