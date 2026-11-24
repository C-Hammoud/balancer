import { barShares, differenceText } from './income-expense.helpers';

describe('income vs expenses helpers', () => {
  it('says how much of the income was kept', () => {
    expect(differenceText(1000, 820, 'SAR')).toBe('You kept 18% of your income.');
    expect(differenceText(1000, 1000, 'SAR')).toBe('You spent exactly what you earned.');
  });

  it('says how much was overspent', () => {
    expect(differenceText(1000, 2200, 'SAR')).toBe('You spent 1,200.00 SAR more than you earned.');
    expect(differenceText(0, 50, 'USD')).toBe('You spent 50.00 USD more than you earned.');
  });

  it('handles empty periods', () => {
    expect(differenceText(0, 0, 'USD')).toBe('No income or expenses yet.');
  });

  it('scales the bars to the larger amount', () => {
    expect(barShares(1000, 500)).toEqual({ income: 100, expense: 50 });
    expect(barShares(250, 1000)).toEqual({ income: 25, expense: 100 });
    expect(barShares(0, 0)).toEqual({ income: 0, expense: 0 });
  });
});
