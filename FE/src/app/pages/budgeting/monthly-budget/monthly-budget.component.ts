import { Component, OnInit, ViewChild, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { forkJoin, Observable } from 'rxjs';
import { BudgetingService } from '../../../core/budgeting.service';
import { FinanceDataRefreshService } from '../../../core/finance-data-refresh.service';
import { LocaleService } from '../../../core/locale.service';
import {
  BudgetPlan,
  BudgetRow,
  IncomeFrequency,
  IncomeStream,
  IncomeStreamList,
  PlanBucket,
  PlanBucketRow,
  PlanType,
} from '../../../core/models';
import { ToastService } from '../../../core/toast.service';
import { AmountPipe } from '../../../shared/amount.pipe';
import { BudgetTableComponent } from './budget-table.component';
import { PlanSubBudgetsComponent } from './plan-sub-budgets.component';
import { StackCollapseDirective } from '../../../shared/stack-collapse.directive';

interface Segment {
  key: string;
  label: string;
  amount: number;
  pct: number;
}

const REASON_LABELS: Record<string, string> = {
  monthly: 'New month',
  income_change: 'Your income changed',
  commitment_change: 'Your commitments changed',
  overspending: 'Spending is ahead of plan',
  manual: 'Created by you',
};

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

/**
 * One page for the month's budget: the planner suggests amounts from income and commitments,
 * the accepted amounts become the budgets, and the same page tracks spending against them.
 */
@Component({
  selector: 'app-monthly-budget',
  standalone: true,
  imports: [StackCollapseDirective, CommonModule, FormsModule, RouterLink, AmountPipe, BudgetTableComponent, PlanSubBudgetsComponent],
  templateUrl: './monthly-budget.component.html',
  styleUrl: './monthly-budget.component.scss',
})
export class MonthlyBudgetComponent implements OnInit {
  private api = inject(BudgetingService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private toast = inject(ToastService);
  private refresh = inject(FinanceDataRefreshService);
  private locale = inject(LocaleService);

  @ViewChild(BudgetTableComponent) table?: BudgetTableComponent;

  readonly currencyOptions = this.locale.currencies;
  readonly frequencies: { code: IncomeFrequency; label: string }[] = [
    { code: 'monthly', label: 'Monthly' },
    { code: 'biweekly', label: 'Every two weeks' },
    { code: 'weekly', label: 'Weekly' },
    { code: 'yearly', label: 'Yearly' },
  ];
  readonly bucketOptions: { code: PlanBucket; label: string }[] = [
    { code: 'needs', label: 'Need' },
    { code: 'wants', label: 'Want' },
    { code: 'savings', label: 'Savings / investing' },
  ];

  monthValue = this.monthKey(new Date());
  year = signal(new Date().getFullYear());
  month = signal(new Date().getMonth() + 1);

  income = signal<IncomeStreamList | null>(null);
  previews = signal<BudgetPlan[]>([]);
  active = signal<BudgetPlan | null>(null);
  buckets = signal<PlanBucketRow[]>([]);
  loadingPreviews = signal(true);
  busy = signal(false);

  /** This month's budget rows (from the table) and last month's (for "copy last month"). */
  rows = signal<BudgetRow[]>([]);
  tableReady = signal(false);
  plansReady = signal(false);
  prevRows = signal<BudgetRow[]>([]);
  /** The user asked to re-plan a month that already has budgets, or to type amounts by hand. */
  showStart = signal(false);
  manual = signal(false);

  // Income form (add or edit)
  editingStreamId = signal<string | null>(null);
  streamDraft = this.emptyStream();
  incomeOpen = false;
  private incomeLoadedOnce = false;

  // Editable amounts of the suggestion under review: group_id -> amount
  amounts: Record<string, string> = {};
  bucketDraft: Record<string, PlanBucket> = {};

  monthName = computed(() => MONTH_NAMES[this.month() - 1]);
  isCurrentMonth = computed(() => this.monthValue === this.monthKey(new Date()));
  suggestion = computed(() => (this.active()?.status === 'suggested' ? this.active() : null));
  accepted = computed(() => (this.active()?.status === 'accepted' ? this.active() : null));
  hasBudgets = computed(() => this.rows().some((r) => Number(r.forecast) > 0));
  canCopy = computed(() => this.prevRows().some((r) => Number(r.forecast) > 0));
  prevTotal = computed(() => this.prevRows().reduce((s, r) => s + (Number(r.forecast) || 0), 0));
  /** Figures that do not depend on the plan type (income, commitments, projects). */
  basis = computed<BudgetPlan | null>(() => this.active() ?? this.previews()[0] ?? null);
  hasIncome = computed(() => Number(this.basis()?.income_total || 0) > 0);

  /** Which main block to show. */
  mode = computed<'loading' | 'review' | 'start' | 'budget'>(() => {
    if (this.suggestion()) return 'review';
    if (!this.tableReady() || !this.plansReady()) return 'loading';
    return this.hasBudgets() || this.manual() ? 'budget' : 'start';
  });

  budgeted = computed(() => this.rows().reduce((s, r) => s + (Number(r.forecast) || 0), 0));
  spent = computed(() => this.rows().reduce((s, r) => s + (Number(r.actual) || 0), 0));
  available = computed(() => Number(this.basis()?.available || 0));
  reserved = computed(() => Number(this.basis()?.reserved_total || 0));
  unbudgeted = computed(() => this.available() - this.budgeted() - this.reserved());
  leftToSpend = computed(() => this.budgeted() - this.spent());
  daysLeft = computed(() => {
    if (!this.isCurrentMonth()) return 0;
    const now = new Date();
    const last = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
    return last - now.getDate() + 1;
  });
  perDay = computed(() => (this.daysLeft() > 0 ? this.leftToSpend() / this.daysLeft() : 0));
  spentPct = computed(() => (this.budgeted() > 0 ? (this.spent() / this.budgeted()) * 100 : 0));

  segments = computed<Segment[]>(() => {
    const p = this.suggestion() ?? this.previews()[0];
    if (!p) return [];
    const income = Number(p.income_total) || 0;
    if (income <= 0) return [];
    const parts: [string, string, number][] = [
      ['commitments', 'Commitments', Number(p.commitments_total)],
      ['needs', 'Needs', Number(p.needs_total)],
      ['wants', 'Wants', Number(p.wants_total)],
      ['invested', 'Investing', Number(p.invested_total)],
      ['reserved', 'Projects', Number(p.reserved_total || 0)],
      ['savings', 'Savings', Math.max(Number(p.savings_amount), 0)],
    ];
    return parts
      .filter(([, , amount]) => amount > 0)
      .map(([key, label, amount]) => ({ key, label, amount, pct: Math.min((amount / income) * 100, 100) }));
  });

  ngOnInit(): void {
    const id = this.route.snapshot.queryParamMap.get('id');
    this.loadIncome();
    this.loadBuckets();
    if (id) {
      // Notification links open a specific suggestion.
      this.api.plan(id).subscribe({
        next: (p) => {
          this.setMonth(p.year + '-' + String(p.month).padStart(2, '0'));
          this.setActive(p);
          this.plansReady.set(true);
          this.loadPreviews();
          this.loadPrevMonth();
        },
        error: () => {
          this.toast.error('That plan was not found.');
          this.loadMonth();
        },
      });
    } else {
      this.loadMonth();
    }
  }

  private monthKey(d: Date): string {
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0');
  }

  private setMonth(value: string): void {
    this.monthValue = value;
    const [y, m] = value.split('-').map(Number);
    if (y !== this.year() || m !== this.month()) {
      // The table reloads when its year/month inputs change; wait for it.
      this.tableReady.set(false);
      this.rows.set([]);
    }
    this.year.set(y);
    this.month.set(m);
  }

  private emptyStream(): Partial<IncomeStream> {
    return { name: '', amount: '', currency: this.locale.defaultCurrency(), frequency: 'monthly' };
  }

  onMonthChange(): void {
    if (!this.monthValue) return;
    this.router.navigate([], { queryParams: {}, replaceUrl: true });
    this.setMonth(this.monthValue);
    this.loadMonth();
  }

  loadMonth(): void {
    this.plansReady.set(false);
    this.showStart.set(false);
    this.manual.set(false);
    this.api.plans(this.year(), this.month()).subscribe({
      next: (rows) => {
        const current = rows.find((p) => p.status === 'suggested') ?? rows.find((p) => p.status === 'accepted');
        this.setActive(current ?? null);
        this.plansReady.set(true);
      },
      error: () => {
        this.setActive(null);
        this.plansReady.set(true);
      },
    });
    this.loadPreviews();
    this.loadPrevMonth();
  }

  loadPreviews(): void {
    this.loadingPreviews.set(true);
    this.api.previewPlans(this.year(), this.month()).subscribe({
      next: (r) => {
        this.previews.set(r.plans);
        this.loadingPreviews.set(false);
      },
      error: (err) => {
        this.loadingPreviews.set(false);
        this.toast.fromHttpError(err, 'Could not calculate suggestions.');
      },
    });
  }

  private loadPrevMonth(): void {
    const y = this.month() === 1 ? this.year() - 1 : this.year();
    const m = this.month() === 1 ? 12 : this.month() - 1;
    this.api.budgets(y, m).subscribe({
      next: (r) => this.prevRows.set(r.rows.filter((row) => row.group_id)),
      error: () => this.prevRows.set([]),
    });
  }

  onTableLoaded(rows: BudgetRow[]): void {
    this.rows.set(rows);
    this.tableReady.set(true);
  }

  private setActive(p: BudgetPlan | null): void {
    this.active.set(p);
    this.amounts = {};
    for (const line of p?.lines ?? []) this.amounts[line.group_id] = String(Number(line.amount));
  }

  reasonLabel(p: BudgetPlan): string {
    return REASON_LABELS[p.reason || 'manual'] || 'Suggested';
  }

  currency(): string {
    return this.basis()?.currency || this.locale.defaultCurrency();
  }

  // ---- Start the month ----

  copyLastMonth(): void {
    const calls: Observable<unknown>[] = [];
    for (const r of this.prevRows()) {
      const own = Number(r.forecast_explicit);
      if (own > 0) calls.push(this.api.updateGroupBudget(this.year(), this.month(), r.group_id!, own));
      for (const s of r.sub_budgets || []) {
        if (Number(s.forecast) > 0) calls.push(this.api.updateBudget(this.year(), this.month(), s.category_id, s.forecast));
      }
    }
    if (!calls.length) return;
    this.busy.set(true);
    forkJoin(calls).subscribe({
      next: () => {
        this.busy.set(false);
        this.showStart.set(false);
        this.toast.success(`Copied last month’s budget into ${this.monthName()}.`);
        this.refresh.notify();
        this.table?.reload();
      },
      error: (err) => {
        this.busy.set(false);
        this.toast.fromHttpError(err, 'Could not copy last month.');
        this.table?.reload();
      },
    });
  }

  startManual(): void {
    this.manual.set(true);
    this.showStart.set(false);
  }

  choose(type: PlanType): void {
    this.busy.set(true);
    this.api.createPlan(this.year(), this.month(), type).subscribe({
      next: (p) => {
        this.busy.set(false);
        this.setActive(p);
        this.showStart.set(false);
        this.router.navigate([], { queryParams: { id: p.id }, replaceUrl: true });
      },
      error: (err) => {
        this.busy.set(false);
        this.toast.fromHttpError(err, 'Could not create the suggestion.');
      },
    });
  }

  // ---- Review a suggestion ----

  amountsChanged(): boolean {
    const p = this.suggestion();
    return !!p && p.lines.some((l) => Number(this.amounts[l.group_id]) !== Number(l.amount));
  }

  /** Savings if the edited amounts were used (shown live while typing). */
  draftSavings(): number {
    const p = this.suggestion();
    if (!p) return 0;
    const lines = p.lines.reduce((sum, l) => sum + (Number(this.amounts[l.group_id]) || 0), 0);
    return Number(p.available) - lines - Number(p.reserved_total || 0);
  }

  draftTotal(): number {
    const p = this.suggestion();
    return p ? p.lines.reduce((sum, l) => sum + (Number(this.amounts[l.group_id]) || 0), 0) : 0;
  }

  accept(): void {
    const p = this.suggestion();
    if (!p?.id) return;
    if (Object.values(this.amounts).some((v) => Number(v) < 0 || v === '' || isNaN(Number(v)))) {
      this.toast.error('Amounts must be zero or more.');
      return;
    }
    this.busy.set(true);
    const save$ = this.amountsChanged() ? this.api.updatePlanAmounts(p.id, this.amounts) : null;
    const doAccept = () =>
      this.api.acceptPlan(p.id!).subscribe({
        next: (accepted) => {
          this.busy.set(false);
          this.setActive(accepted);
          this.router.navigate([], { queryParams: {}, replaceUrl: true });
          this.refresh.notify();
          this.toast.success(`${this.monthName()} budget is set. Your savings target is updated too.`);
          this.tableReady.set(false);
          this.table?.reload();
        },
        error: (err) => {
          this.busy.set(false);
          this.toast.fromHttpError(err, 'Could not use these amounts.');
        },
      });
    if (!save$) {
      doAccept();
      return;
    }
    save$.subscribe({
      next: () => doAccept(),
      error: (err) => {
        this.busy.set(false);
        this.toast.fromHttpError(err, 'Could not save your changes.');
      },
    });
  }

  dismiss(): void {
    const p = this.suggestion();
    if (!p?.id) return;
    this.api.dismissPlan(p.id).subscribe({
      next: () => {
        this.setActive(null);
        this.router.navigate([], { queryParams: {}, replaceUrl: true });
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not dismiss.'),
    });
  }

  /** Projects were added, removed or changed: recalculate what the month sets aside. */
  onSubBudgetsChanged(): void {
    this.loadPreviews();
    const p = this.suggestion();
    if (p) this.choose(p.plan_type);
  }

  // ---- Income ----

  openIncome(): void {
    this.incomeOpen = true;
    setTimeout(() => document.getElementById('income')?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
  }

  loadIncome(): void {
    this.api.incomeStreams().subscribe({
      next: (r) => {
        this.income.set(r);
        if (!this.incomeLoadedOnce) {
          this.incomeLoadedOnce = true;
          this.incomeOpen = !r.streams.length;
        }
      },
      error: () => this.income.set(null),
    });
  }

  editStream(s: IncomeStream): void {
    this.editingStreamId.set(s.id);
    this.streamDraft = { name: s.name, amount: String(Number(s.amount)), currency: s.currency, frequency: s.frequency };
  }

  cancelStream(): void {
    this.editingStreamId.set(null);
    this.streamDraft = this.emptyStream();
  }

  saveStream(): void {
    const d = this.streamDraft;
    if (!(d.name || '').trim() || !(Number(d.amount) > 0)) {
      this.toast.error('Enter a name and an amount greater than zero.');
      return;
    }
    const id = this.editingStreamId();
    const req = id ? this.api.updateIncomeStream(id, d) : this.api.createIncomeStream(d);
    this.busy.set(true);
    req.subscribe({
      next: () => {
        this.busy.set(false);
        this.toast.success(id ? 'Income updated.' : 'Income added.');
        this.cancelStream();
        this.loadIncome();
        this.loadPreviews();
      },
      error: (err) => {
        this.busy.set(false);
        this.toast.fromHttpError(err, 'Could not save income.');
      },
    });
  }

  removeStream(s: IncomeStream): void {
    if (!confirm('Remove income "' + s.name + '"?')) return;
    this.api.deleteIncomeStream(s.id).subscribe({
      next: () => {
        this.toast.success('Income removed.');
        this.loadIncome();
        this.loadPreviews();
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not remove income.'),
    });
  }

  // ---- Needs / wants ----

  loadBuckets(): void {
    this.api.planBuckets().subscribe({
      next: (rows) => {
        this.buckets.set(rows);
        this.bucketDraft = Object.fromEntries(rows.map((r) => [r.group_id, r.bucket]));
      },
      error: () => this.buckets.set([]),
    });
  }

  saveBuckets(): void {
    this.busy.set(true);
    this.api.savePlanBuckets(this.bucketDraft).subscribe({
      next: (rows) => {
        this.busy.set(false);
        this.buckets.set(rows);
        this.toast.success('Needs and wants saved. Suggestions recalculated.');
        this.loadPreviews();
      },
      error: (err) => {
        this.busy.set(false);
        this.toast.fromHttpError(err, 'Could not save.');
      },
    });
  }
}
