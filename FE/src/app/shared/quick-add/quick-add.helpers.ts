import { QuickTransactionInput } from '../../core/models';
import { SAME_AS_DESCRIPTION } from '../../pages/budgeting/transactions/transaction-assign.helpers';

export { SAME_AS_DESCRIPTION };

export type QuickDirection = 'expense' | 'income';

/** One transaction being typed in the quick-add screen or the dashboard widget. */
export interface QuickRow {
  /** Local id for tracking rows in the list (not sent). */
  key: number;
  direction: QuickDirection;
  date: string;
  amount: string;
  currency: string;
  /** Expense: parent category. */
  groupId: string;
  /** Expense: a merchant of the category, or SAME_AS_DESCRIPTION (named after the description). */
  merchantId: string;
  description: string;
  /** Empty: the default expense account. */
  accountId: string;
  note: string;
}

/** Values a brand-new row starts with. */
export interface QuickRowDefaults {
  date: string;
  currency: string;
  accountId: string;
}

let nextKey = 1;

/**
 * A new row: an expense with the defaults (today, default currency, default account). When a
 * previous row is given, its type, date, currency, account and category carry over, so a run of
 * similar transactions only needs the amount and description.
 */
export function newQuickRow(defaults: QuickRowDefaults, previous?: QuickRow | null, initial?: Partial<QuickRow>): QuickRow {
  return {
    direction: previous?.direction ?? 'expense',
    date: previous?.date || defaults.date,
    amount: '',
    currency: previous?.currency || defaults.currency,
    groupId: previous?.groupId ?? '',
    merchantId: SAME_AS_DESCRIPTION,
    description: '',
    accountId: previous ? previous.accountId : defaults.accountId,
    note: '',
    ...initial,
    key: nextKey++,
  };
}

/** A copy of the row (everything typed), as a new row. */
export function duplicateQuickRow(row: QuickRow): QuickRow {
  return { ...row, key: nextKey++ };
}

/** "1,250.50" → 1250.5; NaN when it is not a number. */
export function parseQuickAmount(value: string): number {
  const text = String(value ?? '').replace(/[,\s]/g, '');
  return text ? Number(text) : NaN;
}

/** Something was typed (used to ask before discarding). */
export function quickRowHasData(row: QuickRow): boolean {
  return !!(String(row.amount).trim() || row.description.trim() || row.note.trim());
}

/** What is missing in the row ('' when it can be saved). Same rules as the server. */
export function quickRowError(row: QuickRow): string {
  const amount = parseQuickAmount(row.amount);
  if (!(amount > 0)) return 'Enter an amount above 0.';
  if (!row.date) return 'Choose a date.';
  if (row.direction === 'income') {
    return row.description.trim() ? '' : 'Enter what this income is (e.g. Salary).';
  }
  if (!row.groupId) return 'Choose a category.';
  if (usesDescriptionAsMerchant(row) && !row.description.trim()) {
    return 'Enter a description (it becomes the merchant) or pick a merchant.';
  }
  return '';
}

export function usesDescriptionAsMerchant(row: QuickRow): boolean {
  return !row.merchantId || row.merchantId === SAME_AS_DESCRIPTION;
}

/** The row as the server expects it (POST transactions/bulk/create/). */
export function toQuickInput(row: QuickRow, time = ''): QuickTransactionInput {
  const expense = row.direction === 'expense';
  return {
    date: row.date,
    time,
    direction: row.direction,
    description: row.description.trim(),
    amount: String(parseQuickAmount(row.amount)),
    currency: row.currency || undefined,
    account_id: row.accountId || undefined,
    group_id: expense ? row.groupId : undefined,
    category_id: expense && !usesDescriptionAsMerchant(row) ? row.merchantId : undefined,
    note: row.note.trim(),
  };
}

export interface QuickTotal {
  currency: string;
  direction: QuickDirection;
  count: number;
  total: number;
}

/** Rows with a valid amount, added up per currency and type (expenses first). */
export function quickTotals(rows: QuickRow[]): QuickTotal[] {
  const byKey = new Map<string, QuickTotal & { cents: number }>();
  for (const r of rows) {
    const amount = parseQuickAmount(r.amount);
    if (!(amount > 0)) continue;
    const key = `${r.direction}|${r.currency}`;
    const t = byKey.get(key) ?? { currency: r.currency, direction: r.direction, count: 0, total: 0, cents: 0 };
    t.count += 1;
    t.cents += Math.round(amount * 100);
    byKey.set(key, t);
  }
  return [...byKey.values()]
    .map(({ cents, ...t }) => ({ ...t, total: cents / 100 }))
    .sort((a, b) => a.direction.localeCompare(b.direction) || a.currency.localeCompare(b.currency));
}

/** Server row errors ({rows: {"0": {field: [msg]}}}) as one message per row index. */
export function quickRowErrorsFromResponse(body: unknown): Map<number, string> {
  const out = new Map<number, string>();
  const rows = (body as { rows?: Record<string, Record<string, unknown>> } | null)?.rows;
  if (!rows || typeof rows !== 'object') return out;
  for (const [index, fields] of Object.entries(rows)) {
    const messages = Object.values(fields ?? {})
      .flatMap((v) => (Array.isArray(v) ? v : [v]))
      .map((v) => String(v));
    out.set(Number(index), messages.join(' '));
  }
  return out;
}
