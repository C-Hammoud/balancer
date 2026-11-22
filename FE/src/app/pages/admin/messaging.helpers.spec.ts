import { audienceSummary, localInputToIso, parseCodes } from './messaging.helpers';

describe('admin messaging helpers', () => {
  it('describes audiences', () => {
    expect(audienceSummary({ type: 'all' })).toBe('All active users');
    expect(audienceSummary({ type: 'users', user_ids: [1] })).toBe('1 chosen user');
    expect(audienceSummary({ type: 'users', user_ids: [1, 2] })).toBe('2 chosen users');
    expect(audienceSummary({ type: 'filter' })).toBe('All active users');
    expect(
      audienceSummary({ type: 'filter', flags: ['setup_stuck', 'no_activity'], countries: ['SA'], verified: 'no', last_login: '30' })
    ).toBe('Active users: Setup stuck or No activity; in SA; email not verified; no sign-in for 30 days');
  });

  it('reads country codes typed by hand', () => {
    expect(parseCodes(' sa, LB;sa  ae ')).toEqual(['SA', 'LB', 'AE']);
    expect(parseCodes('')).toEqual([]);
  });

  it('turns a datetime-local value into ISO', () => {
    expect(localInputToIso('')).toBeNull();
    expect(localInputToIso('nonsense')).toBeNull();
    const iso = localInputToIso('2026-12-01T09:00')!;
    expect(new Date(iso).getHours()).toBe(9);
  });
});
