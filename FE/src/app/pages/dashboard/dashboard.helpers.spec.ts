import { Commitment, UtilizationRow, YearlyMonthRow, YearlyOverview } from '../../core/models';
import {
  budgetProgress,
  percentChange,
  previousMonthRow,
  savingsRate,
  spendingPace,
  upcomingDue,
} from './dashboard.helpers';

function row(partial: Partial<UtilizationRow>): UtilizationRow {
  return {
    category_id: 'c', category_name: 'Food', group_name: 'Food', forecast: '0', actual: '0',
    remaining: '0', variance: '0', utilization_pct: null, status: 'ok', warn_pct: '80', critical_pct: '100',
    ...partial,
  };
}

function month(m: number, expense = '0'): YearlyMonthRow {
  return {
    month: m, month_name: '', month_short: '', income_total: '0', expense_total: expense, net: '0',
    total_forecast: '0', total_actual: '0', remaining: '0', overall_util: null, overall_status: '',
  };
}

function year(y: number, months: YearlyMonthRow[]): YearlyOverview {
  return { year: y, income_total: '0', expense_total: '0', net: '0', months };
}

function commitment(name: string, due: string | null): Commitment {
  return { id: name, name, next_due_date: due, next_due_line_id: due ? 'line' : null, next_due_amount: '100' } as Commitment;
}

describe('dashboard helpers', () => {
  it('percentChange compares with the previous value, null without one', () => {
    expect(percentChange('120', '100')).toBeCloseTo(20);
    expect(percentChange('80', '100')).toBeCloseTo(-20);
    expect(percentChange('50', '0')).toBeNull();
    expect(percentChange('50', null)).toBeNull();
  });

  it('savingsRate is the share of income kept, null without income', () => {
    expect(savingsRate('5000', '4100')).toBeCloseTo(18);
    expect(savingsRate('1000', '1500')).toBeCloseTo(-50);
    expect(savingsRate('0', '300')).toBeNull();
  });

  it('spendingPace projects the month in progress and averages past months', () => {
    const today = new Date(2026, 10, 10); // 10 Nov 2026
    const now = spendingPace('1000', 2026, 11, today);
    expect(now.isCurrentMonth).toBeTrue();
    expect(now.dailyAverage).toBeCloseTo(100);
    expect(now.projected).toBeCloseTo(3000);
    const past = spendingPace('3100', 2026, 10, today);
    expect(past.isCurrentMonth).toBeFalse();
    expect(past.dailyAverage).toBeCloseTo(100);
    expect(past.projected).toBeNull();
  });

  it('budgetProgress caps the bar and maps the status to a tone', () => {
    expect(budgetProgress(row({ forecast: '200', actual: '100', status: 'ok' }), 0)).toEqual({ pct: 50, width: 50, tone: 'ok' });
    expect(budgetProgress(row({ forecast: '100', actual: '85', status: 'warning' }), 0).tone).toBe('warn');
    const over = budgetProgress(row({ forecast: '100', actual: '150', status: 'over' }), 0);
    expect(over.width).toBe(100);
    expect(over.tone).toBe('critical');
    expect(over.pct).toBeCloseTo(150);
    const noBudget = budgetProgress(row({ forecast: '0', actual: '25' }), 100);
    expect(noBudget).toEqual({ pct: null, width: 25, tone: 'none' });
  });

  it('upcomingDue keeps the next 30 days and overdue ones, soonest first', () => {
    const today = new Date(2026, 10, 21);
    const list = upcomingDue(
      [
        commitment('Car', '2026-12-01'),
        commitment('Rent', '2026-11-19'),
        commitment('Far', '2027-01-30'),
        commitment('Done', null),
      ],
      today
    );
    expect(list.map((p) => [p.commitment.name, p.daysUntil])).toEqual([
      ['Rent', -2],
      ['Car', 10],
    ]);
  });

  it('previousMonthRow uses December of the previous year for January', () => {
    const y2026 = year(2026, [month(1, '10'), month(2, '20')]);
    const y2025 = year(2025, [month(12, '99')]);
    expect(previousMonthRow(2026, 2, y2026, null)?.expense_total).toBe('10');
    expect(previousMonthRow(2026, 1, y2026, y2025)?.expense_total).toBe('99');
    expect(previousMonthRow(2026, 1, y2026, null)).toBeNull();
    expect(previousMonthRow(2026, 1, y2026, year(2024, [month(12)]))).toBeNull();
  });
});
