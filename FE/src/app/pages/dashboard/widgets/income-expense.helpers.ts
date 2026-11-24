import { formatAmount } from '../../../shared/amount.pipe';

export type TotalsPeriod = 'month' | 'year' | 'all_time';

export const TOTALS_PERIODS: { id: TotalsPeriod; label: string }[] = [
  { id: 'month', label: 'This month' },
  { id: 'year', label: 'This year' },
  { id: 'all_time', label: 'All time' },
];

/** One sentence under the difference: how much of the income was kept, or how much was overspent. */
export function differenceText(income: number, expense: number, currency: string): string {
  const net = income - expense;
  if (!income && !expense) return 'No income or expenses yet.';
  if (net < 0) return `You spent ${formatAmount(-net)} ${currency} more than you earned.`;
  if (!income) return 'No income recorded.';
  if (net === 0) return 'You spent exactly what you earned.';
  return `You kept ${Math.round((net / income) * 100)}% of your income.`;
}

/** Bar widths (in %) of income and expenses, relative to the larger of the two. */
export function barShares(income: number, expense: number): { income: number; expense: number } {
  const max = Math.max(income, expense, 0);
  if (max <= 0) return { income: 0, expense: 0 };
  return { income: (Math.max(0, income) / max) * 100, expense: (Math.max(0, expense) / max) * 100 };
}
