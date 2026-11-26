import { bottomTab } from './bottom-nav';

describe('bottomTab', () => {
  it('maps the home page', () => {
    expect(bottomTab('/')).toBe('home');
    expect(bottomTab('/dashboard')).toBe('home');
    expect(bottomTab('/dashboard?x=1')).toBe('home');
  });

  it('keeps Utilization apart from the rest of budgeting', () => {
    expect(bottomTab('/budgeting/utilization')).toBe('utilization');
    expect(bottomTab('/budgeting/utilization?month=2026-11')).toBe('utilization');
    expect(bottomTab('/budgeting')).toBe('budgeting');
    expect(bottomTab('/budgeting/')).toBe('budgeting');
    expect(bottomTab('/budgeting/monthly-budget')).toBe('budgeting');
    expect(bottomTab('/budgeting/transactions#top')).toBe('budgeting');
    expect(bottomTab('/budgeting/config/accounts')).toBe('budgeting');
  });

  it('maps the profile and leaves other pages without a tab', () => {
    expect(bottomTab('/profile')).toBe('profile');
    expect(bottomTab('/support')).toBeNull();
    expect(bottomTab('/budgetingx')).toBeNull();
    expect(bottomTab('')).toBe('home');
  });
});
