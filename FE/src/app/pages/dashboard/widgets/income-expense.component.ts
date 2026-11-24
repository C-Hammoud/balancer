import { Component, DestroyRef, OnChanges, OnInit, computed, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { IncomeExpenseTotals } from '../../../core/models';
import { RiskService } from '../../../core/risk.service';
import { FinanceDataRefreshService } from '../../../core/finance-data-refresh.service';
import { AmountPipe } from '../../../shared/amount.pipe';
import { barShares, differenceText, TOTALS_PERIODS, TotalsPeriod } from './income-expense.helpers';

const PERIOD_KEY = 'dashboard_totals_period';

/**
 * Dashboard widget: all income and all expenses, whatever account they were on, and the
 * difference. Card payments and other transfers between own accounts are left out.
 */
@Component({
  selector: 'app-income-expense-widget',
  standalone: true,
  imports: [RouterLink, AmountPipe],
  styleUrls: ['./widget.scss', './income-expense.component.scss'],
  template: `
    <section class="widget" aria-labelledby="totals-title">
      <header class="widget-head">
        <h2 id="totals-title">Income vs expenses</h2>
        <a routerLink="/budgeting/transactions">Transactions</a>
      </header>
      <div class="periods" role="group" aria-label="Period">
        @for (p of periods; track p.id) {
          <button type="button" [class.active]="period() === p.id" [attr.aria-pressed]="period() === p.id" (click)="setPeriod(p.id)">
            {{ p.label }}
          </button>
        }
      </div>
      @if (loading()) {
        <p class="empty">Loading…</p>
      } @else if (error()) {
        <p class="empty">Could not load the totals.</p>
      } @else if (current()) {
        @let t = current()!;
        <ul class="rows">
          <li>
            <span class="main"><strong><i class="sw in"></i>Income</strong><span class="sub">All accounts</span></span>
            <span class="amount">{{ t.income | amount }} {{ currency() }}</span>
          </li>
          <li>
            <span class="main"><strong><i class="sw out"></i>Expenses</strong><span class="sub">All accounts and cards</span></span>
            <span class="amount">{{ t.expense | amount }} {{ currency() }}</span>
          </li>
        </ul>
        <div class="bars" aria-hidden="true">
          <div class="bar"><i class="in" [style.width.%]="shares().income"></i></div>
          <div class="bar"><i class="out" [style.width.%]="shares().expense"></i></div>
        </div>
        <div class="total">
          <strong>Difference</strong>
          <strong [class.neg]="+t.net < 0" [class.pos]="+t.net > 0">{{ +t.net > 0 ? '+' : '' }}{{ t.net | amount }} {{ currency() }}</strong>
        </div>
        <p class="note">
          {{ sentence() }}
          @if (period() === 'all_time' && since()) { <span class="sub">Since {{ since() }}.</span> }
        </p>
        <p class="sub hint">Card payments and transfers between your accounts are not counted.</p>
      }
    </section>
  `,
})
export class IncomeExpenseWidgetComponent implements OnInit, OnChanges {
  private risk = inject(RiskService);
  private refresh = inject(FinanceDataRefreshService);
  private destroyRef = inject(DestroyRef);

  /** Main (report) currency the totals are converted to. */
  reportCurrency = input('');

  readonly periods = TOTALS_PERIODS;
  data = signal<IncomeExpenseTotals | null>(null);
  period = signal<TotalsPeriod>(this.loadPeriod());
  loading = signal(true);
  error = signal(false);
  private started = false;

  current = computed(() => this.data()?.[this.period()] ?? null);
  currency = computed(() => this.data()?.currency ?? '');
  since = computed(() => {
    const iso = this.data()?.all_time.since;
    if (!iso) return '';
    const [y, m, d] = iso.split('-').map(Number);
    return new Date(y, m - 1, d).toLocaleDateString(undefined, { dateStyle: 'medium' });
  });
  shares = computed(() => {
    const t = this.current();
    return t ? barShares(Number(t.income) || 0, Number(t.expense) || 0) : { income: 0, expense: 0 };
  });
  sentence = computed(() => {
    const t = this.current();
    return t ? differenceText(Number(t.income) || 0, Number(t.expense) || 0, this.currency()) : '';
  });

  ngOnInit(): void {
    this.started = true;
    this.load();
    this.refresh.changed$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.load());
  }

  ngOnChanges(): void {
    if (this.started) this.load();
  }

  load(): void {
    this.risk.incomeExpenseTotals(this.reportCurrency() || undefined).subscribe({
      next: (res) => {
        this.data.set(res);
        this.error.set(false);
        this.loading.set(false);
      },
      error: () => {
        this.error.set(true);
        this.loading.set(false);
      },
    });
  }

  setPeriod(p: TotalsPeriod): void {
    this.period.set(p);
    try {
      localStorage.setItem(PERIOD_KEY, p);
    } catch {
      /* storage unavailable */
    }
  }

  private loadPeriod(): TotalsPeriod {
    try {
      const v = localStorage.getItem(PERIOD_KEY);
      return TOTALS_PERIODS.some((p) => p.id === v) ? (v as TotalsPeriod) : 'month';
    } catch {
      return 'month';
    }
  }
}
