import { Component, HostListener, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Observable } from 'rxjs';
import { BudgetingService } from '../../core/budgeting.service';
import { FinanceDataRefreshService } from '../../core/finance-data-refresh.service';
import {
  Account,
  AlertBulkAction,
  AlertCounts,
  AlertTab,
  BudgetAlert,
  BudgetCategory,
  UNMAPPED_CATEGORY_ID,
} from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { ThresholdsComponent } from '../budgeting/config/thresholds.component';

type TypeFilter = 'all' | 'utilization' | 'due' | 'risk';
type SeverityFilter = 'all' | 'CRITICAL' | 'WARN';
type SortKey = 'newest' | 'severity' | 'period';

const SEVERITY_RANK: Record<string, number> = { CRITICAL: 0, WARN: 1 };

export const SNOOZE_OPTIONS = [
  { days: 1, label: '1 day' },
  { days: 3, label: '3 days' },
  { days: 7, label: '1 week' },
];

@Component({
  selector: 'app-alerts',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, ThresholdsComponent],
  templateUrl: './alerts.component.html',
  styleUrl: './alerts.component.scss',
})
export class AlertsComponent implements OnInit {
  private api = inject(BudgetingService);
  private refresh = inject(FinanceDataRefreshService);
  private toast = inject(ToastService);

  readonly unmappedId = UNMAPPED_CATEGORY_ID;
  readonly snoozeOptions = SNOOZE_OPTIONS;
  readonly tabs: { key: AlertTab; label: string }[] = [
    { key: 'open', label: 'Open' },
    { key: 'snoozed', label: 'Snoozed' },
    { key: 'resolved', label: 'Resolved' },
    { key: 'all', label: 'All' },
  ];

  show = signal<AlertTab>('open');
  alerts = signal<BudgetAlert[]>([]);
  counts = signal<AlertCounts | null>(null);
  loading = signal(true);
  busy = signal(false);
  showSettings = signal(false);

  // Filters
  search = signal('');
  typeFilter = signal<TypeFilter>('all');
  severityFilter = signal<SeverityFilter>('all');
  sortKey = signal<SortKey>('newest');

  selected = signal<Set<string>>(new Set());

  // Pay dialog
  payAlert = signal<BudgetAlert | null>(null);
  categories = signal<BudgetCategory[]>([]);
  accounts = signal<Account[]>([]);
  payCategoryId = '';
  payAccountId = '';
  payDate = '';
  paying = signal(false);

  visible = computed(() => {
    const q = this.search().trim().toLowerCase();
    const type = this.typeFilter();
    const sev = this.severityFilter();
    const rows = this.alerts().filter((a) => {
      if (type === 'due' && !this.isCommitmentDue(a)) return false;
      if (type === 'risk' && !this.isRisk(a)) return false;
      if (type === 'utilization' && (this.isCommitmentDue(a) || this.isRisk(a))) return false;
      if (sev !== 'all' && (a.severity || '').toUpperCase() !== sev) return false;
      if (q) {
        const hay = [a.title, a.description, a.commitment_name || ''].join(' ').toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
    return [...rows].sort(this.comparator(this.sortKey()));
  });

  filtersActive = computed(
    () =>
      !!this.search().trim() || this.typeFilter() !== 'all' || this.severityFilter() !== 'all'
  );

  selectedVisible = computed(() => {
    const sel = this.selected();
    return this.visible().filter((a) => sel.has(a.id));
  });

  allVisibleSelected = computed(() => {
    const rows = this.visible();
    const sel = this.selected();
    return rows.length > 0 && rows.every((a) => sel.has(a.id));
  });

  ngOnInit(): void {
    this.reload(true);
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.payAlert() && !this.paying()) this.closePay();
  }

  setTab(tab: AlertTab): void {
    if (this.show() === tab) return;
    this.show.set(tab);
    this.reload();
  }

  reload(refresh = false): void {
    this.loading.set(true);
    this.selected.set(new Set());
    this.api.alerts(this.show(), refresh).subscribe({
      next: (rows) => {
        this.alerts.set(rows);
        this.loading.set(false);
      },
      error: (err) => {
        this.alerts.set([]);
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not load alerts.');
      },
    });
    this.api.alertCount().subscribe({
      next: (c) => this.counts.set(c),
      error: () => this.counts.set(null),
    });
  }

  countFor(tab: AlertTab): number | null {
    const c = this.counts();
    return c ? (c[tab] ?? null) : null;
  }

  clearFilters(): void {
    this.search.set('');
    this.typeFilter.set('all');
    this.severityFilter.set('all');
  }

  private comparator(key: SortKey): (a: BudgetAlert, b: BudgetAlert) => number {
    const newest = (a: BudgetAlert, b: BudgetAlert) =>
      (b.created_at || '').localeCompare(a.created_at || '');
    if (key === 'severity') {
      return (a, b) =>
        (SEVERITY_RANK[a.severity] ?? 9) - (SEVERITY_RANK[b.severity] ?? 9) || newest(a, b);
    }
    if (key === 'period') {
      return (a, b) => b.year * 100 + b.month - (a.year * 100 + a.month) || newest(a, b);
    }
    return newest;
  }

  // ---- Row helpers ----

  isUnmapped(a: BudgetAlert): boolean {
    return a.category_id === UNMAPPED_CATEGORY_ID;
  }

  isCommitmentDue(a: BudgetAlert): boolean {
    return a.alert_type === 'commitment_due' || (a.category_id || '').startsWith('commitment:');
  }

  isRisk(a: BudgetAlert): boolean {
    return a.alert_type === 'risk' || (a.category_id || '').startsWith('risk:');
  }

  typeLabel(a: BudgetAlert): string {
    return this.isCommitmentDue(a) ? 'Due date' : this.isRisk(a) ? 'Risk' : 'Budget';
  }

  stateOf(a: BudgetAlert): 'open' | 'snoozed' | 'resolved' {
    if (a.state) return a.state;
    return a.is_resolved ? 'resolved' : 'open';
  }

  // ---- Selection ----

  isSelected(id: string): boolean {
    return this.selected().has(id);
  }

  toggleSelected(id: string): void {
    this.selected.update((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  clearSelection(): void {
    this.selected.set(new Set());
  }

  toggleAllVisible(): void {
    const ids = this.visible().map((a) => a.id);
    this.selected.set(this.allVisibleSelected() ? new Set() : new Set(ids));
  }

  // ---- Single actions ----

  resolve(a: BudgetAlert): void {
    this.run(this.api.resolveAlert(a.id), 'Alert resolved.', 'Could not resolve alert.');
  }

  reopen(a: BudgetAlert): void {
    this.run(this.api.reopenAlert(a.id), 'Alert reopened.', 'Could not reopen alert.');
  }

  snooze(a: BudgetAlert, event: Event): void {
    const days = this.takeSelectValue(event);
    if (!days) return;
    this.run(
      this.api.snoozeAlert(a.id, days),
      'Snoozed for ' + this.snoozeLabel(days) + '.',
      'Could not snooze alert.'
    );
  }

  unsnooze(a: BudgetAlert): void {
    this.run(this.api.unsnoozeAlert(a.id), 'Alert is back in Open.', 'Could not unsnooze alert.');
  }

  /** Read a snooze <select> value and reset it so the same choice can be picked again. */
  private takeSelectValue(event: Event): number {
    const select = event.target as HTMLSelectElement;
    const days = Number(select.value);
    select.value = '';
    return days;
  }

  private snoozeLabel(days: number): string {
    return SNOOZE_OPTIONS.find((o) => o.days === days)?.label ?? days + ' days';
  }

  private run(req: Observable<unknown>, ok: string, fail: string): void {
    this.busy.set(true);
    req.subscribe({
      next: () => {
        this.busy.set(false);
        this.toast.success(ok);
        this.afterChange();
      },
      error: (err) => {
        this.busy.set(false);
        this.toast.fromHttpError(err, fail);
      },
    });
  }

  private afterChange(): void {
    this.refresh.notify();
    this.reload();
  }

  // ---- Bulk actions ----

  bulk(action: AlertBulkAction, days?: number): void {
    const ids = this.selectedVisible().map((a) => a.id);
    if (ids.length) this.applyBulk(action, ids, days);
  }

  bulkSnooze(event: Event): void {
    const days = this.takeSelectValue(event);
    if (days) this.bulk('snooze', days);
  }

  /** Resolve every unresolved alert currently listed (respects filters). */
  resolveAllVisible(): void {
    const ids = this.visible()
      .filter((a) => this.stateOf(a) !== 'resolved')
      .map((a) => a.id);
    if (!ids.length) return;
    const scope = this.filtersActive() ? 'matching the current filters' : 'in this list';
    if (!confirm('Resolve all ' + ids.length + ' alert(s) ' + scope + '?')) return;
    this.applyBulk('resolve', ids);
  }

  private applyBulk(action: AlertBulkAction, ids: string[], days?: number): void {
    const verb: Record<AlertBulkAction, string> = {
      resolve: 'Resolved',
      reopen: 'Reopened',
      snooze: 'Snoozed for ' + (days ? this.snoozeLabel(days) : '') + ':',
      unsnooze: 'Unsnoozed',
    };
    this.busy.set(true);
    this.api.bulkAlerts(action, ids, days).subscribe({
      next: (r) => {
        this.busy.set(false);
        const n = r.updated.length;
        const skipped = r.failed.length ? ' (' + r.failed.length + ' skipped)' : '';
        this.toast.success(verb[action] + ' ' + n + ' alert' + (n === 1 ? '' : 's') + skipped + '.');
        this.afterChange();
      },
      error: (err) => {
        this.busy.set(false);
        this.toast.fromHttpError(err, 'Bulk action failed.');
      },
    });
  }

  // ---- Pay commitment from alert ----

  openPay(a: BudgetAlert): void {
    this.payAlert.set(a);
    this.payCategoryId = '';
    this.payAccountId = '';
    this.payDate = new Date().toISOString().slice(0, 10);
    if (!this.categories().length) {
      this.api.categories().subscribe({
        next: (c) => this.categories.set(c.categories),
        error: () => this.categories.set([]),
      });
    }
    this.api.accounts(true).subscribe({
      next: (rows) => {
        this.accounts.set(rows);
        const def = rows.find((r) => r.is_default_for_expenses) ?? rows[0];
        if (def && !this.payAccountId) this.payAccountId = def.id;
      },
      error: () => this.accounts.set([]),
    });
  }

  closePay(): void {
    this.payAlert.set(null);
    this.paying.set(false);
  }

  commitmentLabel(a: BudgetAlert): string {
    return a.commitment_name || a.title.replace(/^(Due soon|Overdue):\s*/i, '') || 'Commitment';
  }

  confirmPay(): void {
    const a = this.payAlert();
    if (!a || this.paying()) return;
    if (!this.payCategoryId) {
      this.toast.error('Pick the budget category for this payment.');
      return;
    }
    this.paying.set(true);
    this.api
      .recordCommitmentDue(a.id, this.payCategoryId, {
        accountId: this.payAccountId || undefined,
        paymentDate: this.payDate || undefined,
      })
      .subscribe({
        next: () => {
          this.toast.success('Payment recorded and the installment is marked paid.');
          this.closePay();
          this.afterChange();
        },
        error: (err) => {
          this.paying.set(false);
          if (err?.status === 409) {
            this.toast.success('This payment was already recorded.');
            this.closePay();
            this.afterChange();
            return;
          }
          this.toast.fromHttpError(err, 'Could not record payment.');
        },
      });
  }
}
