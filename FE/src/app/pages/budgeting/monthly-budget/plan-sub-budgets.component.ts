import { Component, EventEmitter, OnInit, Output, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { BudgetingService } from '../../../core/budgeting.service';
import { LocaleService } from '../../../core/locale.service';
import { PersonalBudget } from '../../../core/models';
import { ToastService } from '../../../core/toast.service';

interface SubBudgetDraft {
  name: string;
  total_amount: string;
  currency: string;
  start_date: string;
  end_date: string;
  funding_months: number | null;
}

/**
 * Plan sub-budgets (trips, projects): their money is reserved inside the plan's main budget and
 * expenses tagged to them count only there, not in the regular category budgets.
 */
@Component({
  selector: 'app-plan-sub-budgets',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './plan-sub-budgets.component.html',
  styleUrl: './plan-sub-budgets.component.scss',
})
export class PlanSubBudgetsComponent implements OnInit {
  private api = inject(BudgetingService);
  private toast = inject(ToastService);
  private locale = inject(LocaleService);

  /** Attach / detach / create happened: the plan must be recalculated. */
  @Output() changed = new EventEmitter<void>();

  readonly currencyOptions = this.locale.currencies;
  attached = signal<PersonalBudget[]>([]);
  available = signal<PersonalBudget[]>([]);
  busy = signal(false);
  showForm = signal(false);
  draft: SubBudgetDraft = this.emptyDraft();

  /** Budgets that can join the plan (own, not archived/completed, not the old default). */
  candidates = computed(() =>
    this.available().filter((b) => b.is_owner !== false && !b.is_default && (b.status === 'active' || b.status === 'draft'))
  );

  ngOnInit(): void {
    this.load();
  }

  private emptyDraft(): SubBudgetDraft {
    return { name: '', total_amount: '', currency: this.locale.defaultCurrency(), start_date: '', end_date: '', funding_months: null };
  }

  load(): void {
    this.api.personalBudgets({ in_plan: true, sort: 'name' }).subscribe({
      next: (r) => this.attached.set(r.budgets),
      error: () => this.attached.set([]),
    });
    this.api.personalBudgets({ in_plan: false, sort: 'name' }).subscribe({
      next: (r) => this.available.set(r.budgets),
      error: () => this.available.set([]),
    });
  }

  /** Months from now until the month before the start date (the server uses the same default). */
  defaultMonths(): number {
    if (!this.draft.start_date) return 1;
    const start = new Date(this.draft.start_date + 'T00:00:00');
    const now = new Date();
    const months = (start.getFullYear() - now.getFullYear()) * 12 + start.getMonth() - now.getMonth();
    return Math.max(1, Math.min(months, 36));
  }

  perMonth(): number {
    const months = Number(this.draft.funding_months) || this.defaultMonths();
    return (Number(this.draft.total_amount) || 0) / months;
  }

  create(): void {
    const d = this.draft;
    if (!d.name.trim() || !(Number(d.total_amount) > 0)) {
      this.toast.error('Enter a name and an amount greater than zero.');
      return;
    }
    this.busy.set(true);
    this.api
      .createPersonalBudget({
        name: d.name.trim(),
        total_amount: String(d.total_amount),
        currency: d.currency,
        start_date: d.start_date || null,
        end_date: d.end_date || null,
        status: 'active',
        in_plan: true,
        funding_months: Number(d.funding_months) || undefined,
      })
      .subscribe({
        next: () => {
          this.busy.set(false);
          this.showForm.set(false);
          this.draft = this.emptyDraft();
          this.toast.success('Sub-budget added to your plan.');
          this.load();
          this.changed.emit();
        },
        error: (err) => {
          this.busy.set(false);
          this.toast.fromHttpError(err, 'Could not create the sub-budget.');
        },
      });
  }

  attach(b: PersonalBudget): void {
    const n = b.transactions_count ?? 0;
    const impact = n
      ? `\n\n${n} expense(s) tagged to it will stop counting in your regular category budgets and count only in "${b.name}".`
      : '';
    if (!confirm(`Add "${b.name}" to your plan? Its money is reserved in the plan.${impact}`)) return;
    this.setInPlan(b, true, `"${b.name}" is now part of your plan.`);
  }

  detach(b: PersonalBudget): void {
    if (!confirm(`Remove "${b.name}" from your plan? Its expenses will count in your category budgets again.`)) return;
    this.setInPlan(b, false, `"${b.name}" was removed from your plan.`);
  }

  setMonths(b: PersonalBudget, value: string): void {
    const months = Number(value);
    if (!(months >= 1 && months <= 36)) {
      this.toast.error('Spread it over 1 to 36 months.');
      return;
    }
    this.busy.set(true);
    this.api.updatePersonalBudget(b.id, { funding_months: months }).subscribe({
      next: () => {
        this.busy.set(false);
        this.load();
        this.changed.emit();
      },
      error: (err) => {
        this.busy.set(false);
        this.toast.fromHttpError(err, 'Could not update the sub-budget.');
      },
    });
  }

  private setInPlan(b: PersonalBudget, inPlan: boolean, done: string): void {
    this.busy.set(true);
    this.api.updatePersonalBudget(b.id, { in_plan: inPlan }).subscribe({
      next: () => {
        this.busy.set(false);
        this.toast.success(done);
        this.load();
        this.changed.emit();
      },
      error: (err) => {
        this.busy.set(false);
        this.toast.fromHttpError(err, 'Could not update the plan.');
      },
    });
  }
}
