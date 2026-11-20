import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { BudgetingService } from '../../core/budgeting.service';
import { FinanceDataRefreshService } from '../../core/finance-data-refresh.service';
import { BudgetDashboard, PersonalBudget } from '../../core/models';
import { formatAmount } from '../amount.pipe';

type Pace = 'none' | 'ok' | 'fast' | 'over';

interface ProjectView {
  id: string;
  name: string;
  currency: string;
  pct: number;
  remaining: number;
  endDate: string | null;
  tone: 'ok' | 'warn' | 'over';
  note: string;
}

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

/**
 * Dashboard widget answering the three everyday questions for the current month:
 * how much can I spend, how am I doing, and are my projects on track.
 */
@Component({
  selector: 'app-month-questions',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './month-questions.component.html',
  styleUrl: './month-questions.component.scss',
})
export class MonthQuestionsComponent implements OnInit {
  private api = inject(BudgetingService);
  private refresh = inject(FinanceDataRefreshService);
  private destroyRef = inject(DestroyRef);

  private readonly today = new Date();
  readonly year = this.today.getFullYear();
  readonly month = this.today.getMonth() + 1;
  readonly monthName = MONTHS[this.month - 1];
  readonly daysInMonth = new Date(this.year, this.month, 0).getDate();
  readonly day = this.today.getDate();
  readonly daysLeft = this.daysInMonth - this.day + 1;
  readonly monthPct = (this.day / this.daysInMonth) * 100;

  data = signal<BudgetDashboard | null>(null);
  projects = signal<PersonalBudget[]>([]);
  loading = signal(true);
  failed = signal(false);

  currency = computed(() => this.data()?.report_currency || '');
  budget = computed(() => Number(this.data()?.report?.total_forecast || 0));
  spent = computed(() => Number(this.data()?.report?.total_actual || 0));
  left = computed(() => this.budget() - this.spent());
  perDay = computed(() => (this.daysLeft > 0 ? this.left() / this.daysLeft : 0));
  usedPct = computed(() => (this.budget() > 0 ? (this.spent() / this.budget()) * 100 : 0));

  pace = computed<Pace>(() => {
    if (this.budget() <= 0) return 'none';
    if (this.usedPct() > 100) return 'over';
    return this.usedPct() > this.monthPct + 10 ? 'fast' : 'ok';
  });

  paceLabel = computed(() => {
    switch (this.pace()) {
      case 'over':
        return 'Over budget';
      case 'fast':
        return 'Spending fast';
      case 'ok':
        return 'On track';
      default:
        return 'No budget yet';
    }
  });

  /** Spending at the current daily rate until month end (shown from day 5, when the rate means something). */
  projected = computed(() => (this.day >= 5 ? (this.spent() / this.day) * this.daysInMonth : null));

  /** Categories at or past their limit this month. */
  overCategories = computed(() =>
    (this.data()?.report?.rows || [])
      .filter((r) => r.row_type === 'group' && (r.status === 'over' || r.status === 'critical'))
      .map((r) => r.category_name)
  );

  projectViews = computed<ProjectView[]>(() =>
    this.projects()
      .slice()
      .sort((a, b) => (a.end_date || '9999').localeCompare(b.end_date || '9999'))
      .slice(0, 3)
      .map((p) => this.toView(p))
  );

  ngOnInit(): void {
    this.load();
    this.refresh.changed$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.load());
  }

  load(): void {
    this.api.dashboard(this.year, this.month).subscribe({
      next: (d) => {
        this.data.set(d);
        this.failed.set(false);
        this.loading.set(false);
      },
      error: () => {
        this.failed.set(true);
        this.loading.set(false);
      },
    });
    this.api.personalBudgets({ status: 'active' }).subscribe({
      next: (r) => this.projects.set(r.budgets || []),
      error: () => this.projects.set([]),
    });
  }

  money(value: number, currency = this.currency()): string {
    return `${formatAmount(value, 0)} ${currency}`.trim();
  }

  clamp(pct: number): number {
    return Math.max(0, Math.min(pct, 100));
  }

  private toView(p: PersonalBudget): ProjectView {
    const pct = Number(p.percent_used) || 0;
    const timePct = this.timeElapsedPct(p.start_date, p.end_date);
    let tone: ProjectView['tone'] = 'ok';
    let note = 'On track';
    if (pct > 100) {
      tone = 'over';
      note = 'Over its budget';
    } else if (timePct != null && pct > timePct + 15) {
      tone = 'warn';
      note = 'Spending ahead of schedule';
    } else if (pct >= 85) {
      tone = 'warn';
      note = 'Almost used up';
    }
    return {
      id: p.id,
      name: p.name,
      currency: p.currency,
      pct,
      remaining: Number(p.remaining) || 0,
      endDate: p.end_date,
      tone,
      note,
    };
  }

  private timeElapsedPct(start: string | null, end: string | null): number | null {
    if (!start || !end) return null;
    const s = new Date(start).getTime();
    const e = new Date(end).getTime();
    if (!(e > s)) return null;
    return this.clamp(((this.today.getTime() - s) / (e - s)) * 100);
  }
}
