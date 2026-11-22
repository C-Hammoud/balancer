import { AdminDashboard, OverviewCampaign } from '../../../core/models';
import {
  agoText,
  attentionItems,
  barGeometry,
  campaignRates,
  hoursText,
  linePoints,
  niceMax,
  percent,
  periodChange,
} from './overview.helpers';

describe('admin overview helpers', () => {
  it('words the change against the previous period', () => {
    expect(periodChange(12, 10, 30)).toEqual({ text: '+2 (+20%) vs previous 30 days', tone: 'good' });
    expect(periodChange(5, 10, 7)).toEqual({ text: '-5 (-50%) vs previous 7 days', tone: 'bad' });
    expect(periodChange(3, 0, 7)).toEqual({ text: '+3 vs previous 7 days', tone: 'good' });
    expect(periodChange(4, 4, 90).tone).toBe('flat');
    // More failures is bad.
    expect(periodChange(6, 2, 7, false).tone).toBe('bad');
    expect(periodChange(1, 2, 7, false).tone).toBe('good');
  });

  it('formats percentages and durations', () => {
    expect(percent(1, 3)).toBe('33%');
    expect(percent(0, 0)).toBe('—');
    expect(percent(null, 5)).toBe('—');
    expect(hoursText(null)).toBe('—');
    expect(hoursText(0.4)).toBe('24 min');
    expect(hoursText(5)).toBe('5 h');
    expect(hoursText(50)).toBe('2.1 days');
  });

  it('says how long ago', () => {
    const now = Date.parse('2026-11-22T12:00:00Z');
    expect(agoText('2026-11-22T11:59:30Z', now)).toBe('just now');
    expect(agoText('2026-11-22T11:55:00Z', now)).toBe('5 min ago');
    expect(agoText('2026-11-22T09:00:00Z', now)).toBe('3 h ago');
    expect(agoText(null, now)).toBe('');
  });

  it('rounds the axis maximum', () => {
    expect(niceMax([])).toBe(1);
    expect(niceMax([0, 1])).toBe(1);
    expect(niceMax([3])).toBe(5);
    expect(niceMax([7])).toBe(10);
    expect(niceMax([12])).toBe(20);
    expect(niceMax([51])).toBe(100);
  });

  it('scales bars and line points to the plot', () => {
    const series = [
      { date: '2026-11-20', count: 0 },
      { date: '2026-11-21', count: 5 },
      { date: '2026-11-22', count: 10 },
    ];
    const bars = barGeometry(series, 300, 100, 10);
    expect(bars.map((b) => b.height)).toEqual([0, 50, 100]);
    expect(bars[2].y).toBe(0);
    expect(bars[1].hitX).toBe(100);
    expect(bars[1].hitWidth).toBe(100);
    expect(bars[1].width).toBe(98); // 2px gap between bars
    const pts = linePoints(series, 300, 100, 10);
    expect(pts.map((p) => p.x)).toEqual([50, 150, 250]);
    expect(pts.map((p) => p.y)).toEqual([100, 50, 0]);
  });

  it('computes campaign read and click rates', () => {
    const c = {
      stats: {
        recipients: 4, processed: 4, opted_out: 0,
        by_channel: {
          in_app: { total: 4, sent: 4, failed: 0, skipped: 0, read: 1, clicked: 0 },
          email: { total: 4, sent: 2, failed: 2, skipped: 0, read: 0, clicked: 1 },
        },
      },
    } as unknown as OverviewCampaign;
    expect(campaignRates(c)).toEqual({ read: '25%', clicked: '50%' });
    const none = { stats: { recipients: 0, processed: 0, opted_out: 0, by_channel: {} } } as unknown as OverviewCampaign;
    expect(campaignRates(none)).toEqual({ read: '—', clicked: '—' });
  });

  it('lists only the problems with a count', () => {
    const d = {
      tickets_pool: 2, my_open_tickets: 0, emails_failed_7d: 1, email_unverified: 0, setup_stuck: 3,
      messaging: { stuck: 1 },
    } as unknown as AdminDashboard;
    const items = attentionItems(d);
    expect(items.map((i) => i.key)).toEqual(['pool', 'stuck', 'email_failed', 'setup_stuck']);
    expect(items[0].query).toEqual({ view: 'pool' });
    expect(attentionItems({ ...d, messaging: null } as AdminDashboard).map((i) => i.key)).not.toContain('stuck');
  });
});
