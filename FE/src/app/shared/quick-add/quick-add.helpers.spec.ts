import {
  SAME_AS_DESCRIPTION,
  duplicateQuickRow,
  newQuickRow,
  parseQuickAmount,
  quickRowError,
  quickRowErrorsFromResponse,
  quickRowHasData,
  quickTotals,
  toQuickInput,
} from './quick-add.helpers';

const DEFAULTS = { date: '2026-11-22', currency: 'SAR', accountId: 'acc1' };

describe('quick-add helpers', () => {
  it('starts as an expense with the defaults and "Same as description"', () => {
    const r = newQuickRow(DEFAULTS);
    expect(r.direction).toBe('expense');
    expect(r.date).toBe('2026-11-22');
    expect(r.currency).toBe('SAR');
    expect(r.accountId).toBe('acc1');
    expect(r.merchantId).toBe(SAME_AS_DESCRIPTION);
    expect(quickRowHasData(r)).toBeFalse();
  });

  it('carries type, date, currency, account and category over from the previous row', () => {
    const prev = { ...newQuickRow(DEFAULTS), direction: 'income' as const, date: '2026-11-01', currency: 'USD', accountId: '', groupId: 'g1', amount: '5', description: 'x' };
    const next = newQuickRow(DEFAULTS, prev);
    expect([next.direction, next.date, next.currency, next.accountId, next.groupId]).toEqual(['income', '2026-11-01', 'USD', '', 'g1']);
    expect(next.amount).toBe('');
    expect(next.description).toBe('');
    expect(next.key).not.toBe(prev.key);
    expect(duplicateQuickRow(prev).amount).toBe('5');
  });

  it('reads amounts with thousands commas', () => {
    expect(parseQuickAmount('1,250.50')).toBe(1250.5);
    expect(parseQuickAmount('')).toBeNaN();
  });

  it('explains what is missing', () => {
    const r = newQuickRow(DEFAULTS);
    expect(quickRowError(r)).toContain('amount');
    r.amount = '10';
    expect(quickRowError(r)).toContain('category');
    r.groupId = 'g1';
    expect(quickRowError(r)).toContain('description');
    r.merchantId = 'm1';
    expect(quickRowError(r)).toBe('');
    const income = { ...newQuickRow(DEFAULTS), direction: 'income' as const, amount: '10' };
    expect(quickRowError(income)).toContain('income');
    income.description = 'Salary';
    expect(quickRowError(income)).toBe('');
  });

  it('builds the request row', () => {
    const r = { ...newQuickRow(DEFAULTS), amount: '1,000', groupId: 'g1', description: ' Starbucks ' };
    expect(toQuickInput(r, '09:30')).toEqual({
      date: '2026-11-22',
      time: '09:30',
      direction: 'expense',
      description: 'Starbucks',
      amount: '1000',
      currency: 'SAR',
      account_id: 'acc1',
      group_id: 'g1',
      category_id: undefined,
      note: '',
    });
    expect(toQuickInput({ ...r, merchantId: 'm1' }).category_id).toBe('m1');
    const income = toQuickInput({ ...r, direction: 'income' });
    expect(income.group_id).toBeUndefined();
    expect(income.category_id).toBeUndefined();
  });

  it('adds up rows per type and currency', () => {
    const a = { ...newQuickRow(DEFAULTS), amount: '10.10' };
    const b = { ...newQuickRow(DEFAULTS), amount: '0.20' };
    const c = { ...newQuickRow(DEFAULTS), amount: '100', direction: 'income' as const, currency: 'USD' };
    const blank = newQuickRow(DEFAULTS);
    expect(quickTotals([a, b, c, blank])).toEqual([
      { currency: 'SAR', direction: 'expense', count: 2, total: 10.3 },
      { currency: 'USD', direction: 'income', count: 1, total: 100 },
    ]);
  });

  it('reads the server row errors', () => {
    const errors = quickRowErrorsFromResponse({ rows: { '1': { category_id: ['Wrong category.'], amount: ['Too small.'] } } });
    expect(errors.get(1)).toBe('Wrong category. Too small.');
    expect(quickRowErrorsFromResponse({ detail: 'x' }).size).toBe(0);
  });
});
