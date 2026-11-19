import { Pipe, PipeTransform } from '@angular/core';

const formatters = new Map<number, Intl.NumberFormat>();

function formatter(digits: number): Intl.NumberFormat {
  let f = formatters.get(digits);
  if (!f) {
    // Fixed en-US grouping so amounts always read 1,234,567.89 whatever the browser locale.
    f = new Intl.NumberFormat('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
    formatters.set(digits, f);
  }
  return f;
}

/**
 * Money amount with thousands separators: 1234567.5 → "1,234,567.50".
 * Accepts the API's decimal strings; empty values give `fallback`, and text that is not a
 * number is shown unchanged.
 */
export function formatAmount(value: unknown, digits = 2, fallback = '—'): string {
  if (value === null || value === undefined || value === '') return fallback;
  if (typeof value !== 'number' && typeof value !== 'string') return String(value);
  const n = typeof value === 'number' ? value : Number(value.replace(/,/g, '').trim());
  if (!Number.isFinite(n)) return String(value);
  return formatter(digits).format(n);
}

/** `{{ t.amount | amount }}` → "1,568.00"; `{{ x | amount: 0 }}` → "1,568". */
@Pipe({ name: 'amount', standalone: true })
export class AmountPipe implements PipeTransform {
  transform(value: unknown, digits = 2, fallback = '—'): string {
    return formatAmount(value, digits, fallback);
  }
}
