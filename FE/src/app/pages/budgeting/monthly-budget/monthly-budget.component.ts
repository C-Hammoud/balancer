import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { BudgetingService } from '../../../core/budgeting.service';
import { FinanceDataRefreshService } from '../../../core/finance-data-refresh.service';
import { LocaleService } from '../../../core/locale.service';
import {
  BudgetPlan,
  IncomeFrequency,
  IncomeStream,
  IncomeStreamList,
  PlanBucket,
  PlanBucketRow,
  PlanType,
} from '../../../core/models';
import { ToastService } from '../../../core/toast.service';
import { PlanSubBudgetsComponent } from './plan-sub-budgets.component';

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

@Component({
  selector: 'app-plan',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, PlanSubBudgetsComponent],
  templateUrl: './plan.component.html',
  styleUrl: './plan.component.scss',
})
export class PlanComponent implements OnInit {
  private api = inject(BudgetingService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private toast = inject(ToastService);
  private refresh = inject(FinanceDataRefreshService);
  private locale = inject(LocaleService);

  readonly currencyOptions = this.locale.currencies;
  readonly reasonLabels = REASON_LABELS;
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
  income = signal<IncomeStreamList | null>(null);
  previews = signal<BudgetPlan[]>([]);
  active = signal<BudgetPlan | null>(null);
  buckets = signal<PlanBucketRow[]>([]);
  loading = signal(true);
  busy = signal(false);
  showBuckets = signal(false);

  // Income form (add or edit)
  editingStreamId = signal<string | null>(null);
  streamDraft = this.emptyStream();

  // Editable amounts of the active suggestion: group_id -> amount
  amounts: Record<string, string> = {};
  bucketDraft: Record<string, PlanBucket> = {};

  isEditable = computed(() => this.active()?.status === 'suggested');

  segments = computed<Segment[]>(() => {
    const p = this.active() ?? this.previews()[0];
    if (!p) return [];
    const income = Number(p.income_total) || 0;
    if (income <= 0) return [];
    const parts: [string, string, number][] = [
      ['commitments', 'Commitments', Number(p.commitments_total)],
      ['needs', 'Needs', Number(p.needs_total)],
      ['wants', 'Wants', Number(p.wants_total)],
      ['invested', 'Investing', Number(p.invested_total)],
      ['reserved', 'Sub-budgets', Number(p.reserved_total || 0)],
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
      this.api.plan(id).subscribe({
        next: (p) => {
          this.monthValue = p.year + '-' + String(p.month).padStart(2, '0');
          this.setActive(p);
          this.loadPreviews();
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

  private ym(): [number, number] {
    const [y, m] = this.monthValue.split('-').map(Number);
    return [y, m];
  }

  private emptyStream(): Partial<IncomeStream> {
    return { name: '', amount: '', currency: this.locale.defaultCurrency(), frequency: 'monthly' };
  }

  onMonthChange(): void {
    this.router.navigate([], { queryParams: {}, replaceUrl: true });
    this.loadMonth();
  }

  loadMonth(): void {
    const [y, m] = this.ym();
    this.loading.set(true);
    this.api.plans(y, m).subscribe({
      next: (rows) => {
        const current = rows.find((p) => p.status === 'suggested') ?? rows.find((p) => p.status === 'accepted');
        this.setActive(current ?? null);
        this.loadPreviews();
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not load plans.');
      },
    });
  }

  loadPreviews(): void {
    const [y, m] = this.ym();
    this.api.previewPlans(y, m).subscribe({
      next: (r) => {
        this.previews.set(r.plans);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not calculate plans.');
      },
    });
  }

  private setActive(p: BudgetPlan | null): void {
    this.active.set(p);
    this.amounts = {};
    for (const line of p?.lines ?? []) this.amounts[line.group_id] = String(Number(line.amount));
  }

  reasonLabel(p: BudgetPlan): string {
    return REASON_LABELS[p.reason || 'manual'] || 'Suggested';
  }

  // ---- Income ----

  loadIncome(): void {
    this.api.incomeStreams().subscribe({
      next: (r) => this.income.set(r),
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
        this.afterInputsChanged();
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
        this.afterInputsChanged();
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not remove income.'),
    });
  }

  private afterInputsChanged(): void {
    this.loadIncome();
    this.loadPreviews();
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
        this.toast.success('Needs and wants saved. Plans recalculated.');
        this.loadPreviews();
      },
      error: (err) => {
        this.busy.set(false);
        this.toast.fromHttpError(err, 'Could not save.');
      },
    });
  }

  // ---- Plans ----

  choose(type: PlanType): void {
    const [y, m] = this.ym();
    this.busy.set(true);
    this.api.createPlan(y, m, type).subscribe({
      next: (p) => {
        this.busy.set(false);
        this.setActive(p);
        this.router.navigate([], { queryParams: { id: p.id }, replaceUrl: true });
        this.toast.success('Plan ready to review. Adjust amounts, then accept it.');
      },
      error: (err) => {
        this.busy.set(false);
        this.toast.fromHttpError(err, 'Could not create the plan.');
      },
    });
  }

  amountsChanged(): boolean {
    const p = this.active();
    return !!p && p.lines.some((l) => Number(this.amounts[l.group_id]) !== Number(l.amount));
  }

  /** Savings if the edited amounts were saved (shown live while typing). */
  draftSavings(): number {
    const p = this.active();
    if (!p) return 0;
    const lines = p.lines.reduce((sum, l) => sum + (Number(this.amounts[l.group_id]) || 0), 0);
    return Number(p.available) - lines - Number(p.reserved_total || 0);
  }

  saveAmounts(then?: () => void): void {
    const p = this.active();
    if (!p?.id) return;
    if (Object.values(this.amounts).some((v) => Number(v) < 0 || v === '' || isNaN(Number(v)))) {
      this.toast.error('Amounts must be zero or more.');
      return;
    }
    this.busy.set(true);
    this.api.updatePlanAmounts(p.id, this.amounts).subscribe({
      next: (updated) => {
        this.busy.set(false);
        this.setActive(updated);
        if (then) then();
        else this.toast.success('Changes saved.');
      },
      error: (err) => {
        this.busy.set(false);
        this.toast.fromHttpError(err, 'Could not save changes.');
      },
    });
  }

  accept(): void {
    if (this.amountsChanged()) {
      this.saveAmounts(() => this.doAccept());
      return;
    }
    this.doAccept();
  }

  private doAccept(): void {
    const p = this.active();
    if (!p?.id) return;
    this.busy.set(true);
    this.api.acceptPlan(p.id).subscribe({
      next: (accepted) => {
        this.busy.set(false);
        this.setActive(accepted);
        this.refresh.notify();
        this.toast.success('Plan accepted. Monthly budgets and the savings target are updated.');
      },
      error: (err) => {
        this.busy.set(false);
        this.toast.fromHttpError(err, 'Could not accept the plan.');
      },
    });
  }

  /** Sub-budgets were added, removed or changed: recalculate what the plan reserves. */
  onSubBudgetsChanged(): void {
    this.loadPreviews();
    const p = this.active();
    if (p?.status === 'suggested') {
      // Re-create the suggestion so it includes the change (amounts are recalculated).
      this.choose(p.plan_type);
    } else if (p?.status === 'accepted') {
      this.subBudgetsChangedAfterAccept.set(true);
    }
  }

  /** The accepted plan was made before the latest sub-budget change. */
  subBudgetsChangedAfterAccept = signal(false);

  dismiss(): void {
    const p = this.active();
    if (!p?.id || !confirm('Dismiss this suggestion?')) return;
    this.api.dismissPlan(p.id).subscribe({
      next: () => {
        this.toast.success('Suggestion dismissed.');
        this.setActive(null);
        this.router.navigate([], { queryParams: {}, replaceUrl: true });
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not dismiss.'),
    });
  }
}
