import { AmountPipe, formatAmount } from './amount.pipe';

describe('formatAmount', () => {
  it('adds thousands separators and two decimals', () => {
    expect(formatAmount('134000.94')).toBe('134,000.94');
    expect(formatAmount(1568)).toBe('1,568.00');
    expect(formatAmount('1234567.5')).toBe('1,234,567.50');
    expect(formatAmount('-2456.1')).toBe('-2,456.10');
    expect(formatAmount('0')).toBe('0.00');
  });

  it('honours the digits argument', () => {
    expect(formatAmount(1568.4, 0)).toBe('1,568');
  });

  it('accepts values that already have separators', () => {
    expect(formatAmount('1,568.00')).toBe('1,568.00');
  });

  it('shows the fallback for empty values and leaves text unchanged', () => {
    expect(formatAmount(null)).toBe('—');
    expect(formatAmount(undefined)).toBe('—');
    expect(formatAmount('')).toBe('—');
    expect(formatAmount('', 2, '0.00')).toBe('0.00');
    expect(formatAmount('n/a')).toBe('n/a');
  });

  it('is what the pipe returns', () => {
    expect(new AmountPipe().transform('23034')).toBe('23,034.00');
  });
});
