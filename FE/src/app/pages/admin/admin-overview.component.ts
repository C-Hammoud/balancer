import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { LowerCasePipe } from '@angular/common';
import { RouterLink } from '@angular/router';
import { AdminService } from '../../core/admin.service';
import { AuthService } from '../../core/auth.service';
import { AdminDashboard, AuditLogRow, OverviewCampaign, OverviewDays } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { AUDIT_ACTION_LABEL, CAMPAIGN_STATUS_CLASS, CAMPAIGN_STATUS_LABEL, shortDate } from './labels';
import {
  agoText,
  attentionItems,
  campaignRates,
  Change,
  hoursText,
  percent,
  periodChange,
} from './overview/overview.helpers';
import { ChartSeries, TrendChartComponent } from './overview/trend-chart.component';

export const OVERVIEW_WIDGETS = [
  { id: 'numbers', label: 'Key numbers' },
  { id: 'signups', label: 'Sign-ups' },
  { id: 'funnel', label: 'Activation funnel' },
  { id: 'active', label: 'Active users' },
  { id: 'tickets', label: 'Ticket flow' },
  { id: 'response', label: 'Response times' },
  { id: 'workload', label: 'Team workload' },
  { id: 'campaigns', label: 'Recent campaigns' },
  { id: 'email', label: 'Email health' },
  { id: 'activity', label: 'Recent admin activity' },
] as const;

export type OverviewWidgetId = (typeof OVERVIEW_WIDGETS)[number]['id'];
const WIDGET_IDS = new Set<string>(OVERVIEW_WIDGETS.map((w) => w.id));
const SECTION_WIDGETS: Record<string, OverviewWidgetId[]> = {
  users: ['numbers', 'signups', 'funnel', 'active'],
  support: ['tickets', 'response', 'workload'],
  messaging: ['campaigns'],
  system: ['email', 'activity'],
};

const HIDDEN_KEY = 'admin_overview_hidden';
const DAYS_KEY = 'admin_overview_days';
const PERIODS: OverviewDays[] = [7, 30, 90];
const REFRESH_MS = 60_000;
// Validated as a pair (colour-blind safe, 3:1 on white) for the two-line ticket chart.
const BLUE = '#2a78d6';
const ORANGE = '#eb6834';

@Component({
  selector: 'app-admin-overview',
  standalone: true,
  imports: [LowerCasePipe, RouterLink, TrendChartComponent],
  templateUrl: './admin-overview.component.html',
  styleUrls: ['./admin-shared.scss', './admin-overview.component.scss'],
})
export class AdminOverviewComponent implements OnInit {
  private admin = inject(AdminService);
  private auth = inject(AuthService);
  private toast = inject(ToastService);
  private destroyRef = inject(DestroyRef);

  readonly periods = PERIODS;
  readonly widgets = OVERVIEW_WIDGETS;
  readonly statusLabel = CAMPAIGN_STATUS_LABEL;
  readonly statusClass = CAMPAIGN_STATUS_CLASS;
  readonly percent = percent;
  readonly hoursText = hoursText;
  readonly shortDate = shortDate;

  data = signal<AdminDashboard | null>(null);
  loading = signal(false);
  failed = signal(false);
  days = signal<OverviewDays>(this.loadDays());
  hidden = signal<ReadonlySet<OverviewWidgetId>>(new Set());
  showCustomize = signal(false);
  private now = signal(Date.now());

  updated = computed(() => {
    this.now();
    return agoText(this.data()?.generated_at);
  });
  attention = computed(() => {
    const d = this.data();
    return d ? attentionItems(d) : [];
  });
  hiddenCount = computed(() => this.hidden().size);

  signupSeries = computed<ChartSeries[]>(() => {
    const u = this.data()?.users;
    return u ? [{ name: 'Sign-ups', color: BLUE, data: u.signups.series }] : [];
  });
  ticketSeries = computed<ChartSeries[]>(() => {
    const s = this.data()?.support;
    return s
      ? [
          { name: 'Opened', color: BLUE, data: s.opened.series },
          { name: 'Closed', color: ORANGE, data: s.closed.series },
        ]
      : [];
  });
  /** First day of the period, for "joined since" links. */
  periodStart = computed(() => this.data()?.users?.signups.series[0]?.date ?? '');
  emailFailRate = computed(() => {
    const e = this.data()?.email?.current;
    return e ? percent(e.failed, e.sent + e.failed) : '—';
  });
  maxWorkload = computed(() => Math.max(1, ...(this.data()?.support?.workload ?? []).map((r) => r.open + r.waiting)));

  ngOnInit(): void {
    this.hidden.set(this.loadHidden());
    this.load();
    const refresh = setInterval(() => this.load(true), REFRESH_MS);
    const tick = setInterval(() => this.now.set(Date.now()), 30_000);
    this.destroyRef.onDestroy(() => {
      clearInterval(refresh);
      clearInterval(tick);
    });
  }

  load(silent = false): void {
    if (this.loading()) return;
    this.loading.set(true);
    this.admin.dashboard(this.days()).subscribe({
      next: (d) => {
        this.data.set(d);
        this.failed.set(false);
        this.loading.set(false);
        this.now.set(Date.now());
      },
      error: (err) => {
        this.loading.set(false);
        if (!this.data()) this.failed.set(true);
        if (!silent) this.toast.fromHttpError(err, 'Could not load the admin overview.');
      },
    });
  }

  setDays(days: OverviewDays): void {
    if (days === this.days()) return;
    this.days.set(days);
    try {
      localStorage.setItem(DAYS_KEY, String(days));
    } catch {
      /* storage unavailable */
    }
    this.load();
  }

  change(current: number, previous: number, upIsGood = true): Change {
    return periodChange(current, previous, this.days(), upIsGood);
  }

  rates(c: OverviewCampaign): { read: string; clicked: string } {
    return campaignRates(c);
  }

  actionLabel(r: AuditLogRow): string {
    return AUDIT_ACTION_LABEL[r.action] ?? r.action.replace(/_/g, ' ');
  }

  ago(iso: string | null): string {
    return agoText(iso, this.now());
  }

  // ---- Show / hide widgets (saved per admin in this browser) ----

  shown(id: OverviewWidgetId): boolean {
    return !this.hidden().has(id);
  }

  sectionShown(section: string): boolean {
    return SECTION_WIDGETS[section].some((id) => this.shown(id));
  }

  toggleWidget(id: OverviewWidgetId): void {
    this.hidden.update((set) => {
      const next = new Set(set);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    this.saveHidden();
  }

  showAll(): void {
    this.hidden.set(new Set());
    this.saveHidden();
  }

  private hiddenKey(): string {
    const id = this.auth.user()?.id;
    return id ? `${HIDDEN_KEY}_${id}` : HIDDEN_KEY;
  }

  private loadHidden(): Set<OverviewWidgetId> {
    try {
      const raw = JSON.parse(localStorage.getItem(this.hiddenKey()) || '[]');
      return new Set((Array.isArray(raw) ? raw : []).filter((id): id is OverviewWidgetId => WIDGET_IDS.has(id)));
    } catch {
      return new Set();
    }
  }

  private saveHidden(): void {
    try {
      localStorage.setItem(this.hiddenKey(), JSON.stringify([...this.hidden()]));
    } catch {
      /* storage unavailable: the choice lasts until the page is closed */
    }
  }

  private loadDays(): OverviewDays {
    try {
      const v = Number(localStorage.getItem(DAYS_KEY));
      return (PERIODS as number[]).includes(v) ? (v as OverviewDays) : 30;
    } catch {
      return 30;
    }
  }
}
