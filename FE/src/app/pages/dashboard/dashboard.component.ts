import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { BudgetingService } from '../../core/budgeting.service';
import {
  BudgetDashboard,
  UNMAPPED_CATEGORY_ID,
  UtilizationRow,
  YearlyMonthRow,
  YearlyOverview,
} from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { LocaleService } from '../../core/locale.service';
import { FinanceDataRefreshService } from '../../core/finance-data-refresh.service';
import { RiskSummaryComponent } from '../../shared/risk-summary/risk-summary.component';
import { AuthService } from '../../core/auth.service';
import { AccountBalancesWidgetComponent } from './widgets/account-balances.component';
import { UpcomingPaymentsWidgetComponent } from './widgets/upcoming-payments.component';
import { RecentTransactionsWidgetComponent } from './widgets/recent-transactions.component';
import { QuickAddWidgetComponent } from './widgets/quick-add.component';
import {
  BudgetProgress,
  SpendingPace,
  budgetProgress,
  num,
  percentChange,
  previousMonthRow,
  savingsRate,
  spendingPace,
} from './dashboard.helpers';
import { MonthQuestionsComponent } from '../../shared/month-questions/month-questions.component';
import { formatAmount } from '../../shared/amount.pipe';

const DISMISS_KEY = 'ft_dismiss_accounts_prompt';
const HIDDEN_WIDGETS_KEY = 'ft_dashboard_hidden';

/** Dashboard sections the user can show or hide (Customize). */
export const DASHBOARD_WIDGETS = [
  { id: 'quickAdd', label: 'Quick add' },
  { id: 'risk', label: 'Risk summary' },
  { id: 'year', label: 'Year overview' },
  { id: 'month', label: 'Monthly statistics' },
  { id: 'spend', label: 'Spend by category' },
  { id: 'alerts', label: 'Alerts' },
  { id: 'budgetTable', label: 'Budget table' },
  { id: 'balances', label: 'Account balances' },
  { id: 'upcoming', label: 'Upcoming payments' },
  { id: 'recent', label: 'Recent transactions' },
  { id: 'reports', label: 'Reports' },
] as const;
export type DashboardWidgetId = (typeof DASHBOARD_WIDGETS)[number]['id'];
const WIDGET_IDS = new Set<string>(DASHBOARD_WIDGETS.map((w) => w.id));

/** Change against the previous month, worded and coloured for a stat tile. */
export interface TileDelta {
  text: string;
  good: boolean;
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterLink,
    MonthQuestionsComponent,
    RiskSummaryComponent,
    AccountBalancesWidgetComponent,
    UpcomingPaymentsWidgetComponent,
    RecentTransactionsWidgetComponent,
    QuickAddWidgetComponent,
  ],
  templateUrl: './dashboard.component.html',
  styleUrl: './dashboard.component.scss',
})
export class DashboardComponent implements OnInit {
  private budgeting = inject(BudgetingService);
  private toast = inject(ToastService);
  private locale = inject(LocaleService);
  private route = inject(ActivatedRoute);
  private refresh = inject(FinanceDataRefreshService);
  private destroyRef = inject(DestroyRef);
  private auth = inject(AuthService);

  reportCurrency = this.locale.defaultCurrency();

  readonly unmappedId = UNMAPPED_CATEGORY_ID;

  now = new Date();
  year = this.now.getFullYear();
  month = this.now.getMonth() + 1;
  years = Array.from({ length: 5 }, (_, i) => this.year - 2 + i);
  months = [
    { v: 1, n: 'Jan' }, { v: 2, n: 'Feb' }, { v: 3, n: 'Mar' }, { v: 4, n: 'Apr' },
    { v: 5, n: 'May' }, { v: 6, n: 'Jun' }, { v: 7, n: 'Jul' }, { v: 8, n: 'Aug' },
    { v: 9, n: 'Sep' }, { v: 10, n: 'Oct' }, { v: 11, n: 'Nov' }, { v: 12, n: 'Dec' },
  ];

  yearly = signal<YearlyOverview | null>(null);
  budget = signal<BudgetDashboard | null>(null);
  loadingYear = signal(true);
  loadingMonth = signal(true);
  showIncomePrompt = signal(false);
  reportScope: 'year' | 'month' = 'year';
  /** Previous year's overview: only loaded to compare January with December. */
  previousYearly = signal<YearlyOverview | null>(null);

  readonly widgets = DASHBOARD_WIDGETS;
  hiddenWidgets = signal<ReadonlySet<DashboardWidgetId>>(new Set());
  showCustomize = signal(false);

  ngOnInit(): void {
    this.hiddenWidgets.set(this.loadHiddenWidgets());
    this.syncReportCurrency();
    this.locale.loadMeta().subscribe();
    const forceSetup = this.route.snapshot.queryParamMap.get('setup') === 'accounts';
    this.checkAccounts(forceSetup);
    this.reloadYear();
    // Saving a transaction, budget or commitment anywhere refreshes the totals here.
    this.refresh.changed$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.reloadYear());
  }

  private syncReportCurrency(): void {
    this.reportCurrency = this.locale.defaultCurrency();
  }

  fmt(val: string | number | null | undefined): string {
    const cur = this.reportCurrency || this.locale.reportCurrency();
    if (val == null || val === '') return `— ${cur}`;
    return `${formatAmount(val)} ${cur}`;
  }

  checkAccounts(force = false): void {
    if (!force && localStorage.getItem(DISMISS_KEY) === '1') {
      this.showIncomePrompt.set(false);
      return;
    }
    this.budgeting.accounts(true).subscribe({
      next: (rows) => this.showIncomePrompt.set(!rows.length),
      error: () => this.showIncomePrompt.set(false),
    });
  }

  dismissIncomePrompt(): void {
    localStorage.setItem(DISMISS_KEY, '1');
    this.showIncomePrompt.set(false);
  }

  onYearChange(): void {
    this.reloadYear();
  }

  selectMonth(m: number): void {
    this.month = m;
    this.reloadMonth();
  }

  reloadYear(): void {
    this.loadingYear.set(true);
    this.budgeting.yearly(this.year).subscribe({
      next: (y) => {
        this.yearly.set(y);
        if (y.report_currency) {
          this.reportCurrency = y.report_currency;
        }
        this.loadingYear.set(false);
        this.reloadMonth();
      },
      error: (err) => {
        this.yearly.set(null);
        this.loadingYear.set(false);
        this.toast.fromHttpError(err, 'Could not load yearly overview.');
        this.reloadMonth();
      },
    });
  }

  reloadMonth(): void {
    this.loadPreviousYearIfNeeded();
    this.loadingMonth.set(true);
    this.budgeting.dashboard(this.year, this.month).subscribe({
      next: (b) => {
        this.budget.set(b);
        if (b.report_currency) {
          this.reportCurrency = b.report_currency;
        }
        this.loadingMonth.set(false);
      },
      error: (err) => {
        this.loadingMonth.set(false);
        this.toast.fromHttpError(err, 'Could not load monthly dashboard.');
      },
    });
  }

  // ---- Year chart: income and expense side by side ----

  /** Largest monthly income or expense: both series share one scale. */
  chartMax(): number {
    const rows = this.yearly()?.months || [];
    const vals = rows.flatMap((r) => [Math.abs(num(r.income_total)), Math.abs(num(r.expense_total))]);
    return Math.max(...vals, 1);
  }

  /** Bar height in percent; a month with no money has no bar. */
  barHeight(value: string): number {
    const v = Math.abs(num(value));
    if (!v) return 0;
    return Math.max(3, Math.round((v / this.chartMax()) * 100));
  }

  chartTitle(row: YearlyMonthRow): string {
    return `${row.month_name}: income ${this.fmt(row.income_total)}, expense ${this.fmt(row.expense_total)}, net ${this.fmt(row.net)}`;
  }

  // ---- Month tiles: change vs last month, savings rate, spending pace ----

  private loadPreviousYearIfNeeded(): void {
    if (this.month !== 1 || this.previousYearly()?.year === this.year - 1) return;
    this.budgeting.yearly(this.year - 1).subscribe({
      next: (y) => this.previousYearly.set(y),
      error: () => this.previousYearly.set(null),
    });
  }

  private previousMonth(): YearlyMonthRow | null {
    return previousMonthRow(this.year, this.month, this.yearly(), this.previousYearly());
  }

  previousMonthLabel(): string {
    const prev = this.month === 1 ? 12 : this.month - 1;
    return this.months.find((m) => m.v === prev)?.n || '';
  }

  /** "↑ 12% vs Oct": for expenses a rise is bad, for income a rise is good. */
  amountDelta(kind: 'income' | 'expense'): TileDelta | null {
    const prev = this.previousMonth();
    const b = this.budget();
    if (!prev || !b) return null;
    const current = kind === 'income' ? b.income_total : b.expense_total;
    const previous = kind === 'income' ? prev.income_total : prev.expense_total;
    const change = percentChange(Math.abs(num(current)), Math.abs(num(previous)));
    if (change === null) return null;
    const rounded = Math.round(change);
    const arrow = rounded > 0 ? '↑' : rounded < 0 ? '↓' : '→';
    const up = rounded > 0;
    return {
      text: `${arrow} ${Math.abs(rounded)}% vs ${this.previousMonthLabel()}`,
      good: rounded === 0 || (kind === 'income' ? up : !up),
    };
  }

  monthSavingsRate(): number | null {
    const b = this.budget();
    return b ? savingsRate(b.income_total, b.expense_total) : null;
  }

  yearSavingsRate(): number | null {
    const y = this.yearly();
    return y ? savingsRate(y.income_total, y.expense_total) : null;
  }

  /** Change in savings rate, in percentage points. */
  savingsDelta(): TileDelta | null {
    const prev = this.previousMonth();
    const current = this.monthSavingsRate();
    const before = prev ? savingsRate(prev.income_total, prev.expense_total) : null;
    if (current === null || before === null) return null;
    const pts = Math.round(current - before);
    const arrow = pts > 0 ? '↑' : pts < 0 ? '↓' : '→';
    return { text: `${arrow} ${Math.abs(pts)} pts vs ${this.previousMonthLabel()}`, good: pts >= 0 };
  }

  rateText(rate: number | null): string {
    return rate === null ? '—' : `${Math.round(rate)}%`;
  }

  pace(): SpendingPace | null {
    const b = this.budget();
    return b ? spendingPace(b.expense_total, this.year, this.month, new Date()) : null;
  }

  /** Projected month-end spend minus the month's total budget; null without a budget. */
  paceBudgetGap(): number | null {
    const p = this.pace();
    const forecast = num(this.budget()?.report?.total_forecast);
    if (!p?.projected || forecast <= 0) return null;
    return p.projected - forecast;
  }

  absAmount(value: number): number {
    return Math.abs(value);
  }

  // ---- Spend by category: progress against each budget ----

  progress(row: UtilizationRow): BudgetProgress {
    return budgetProgress(row, this.spendTotal());
  }

  // ---- Show / hide widgets ----

  private hiddenKey(): string {
    const id = this.auth.user()?.id;
    return id ? `${HIDDEN_WIDGETS_KEY}_${id}` : HIDDEN_WIDGETS_KEY;
  }

  private loadHiddenWidgets(): Set<DashboardWidgetId> {
    try {
      const raw = JSON.parse(localStorage.getItem(this.hiddenKey()) || '[]');
      return new Set(
        (Array.isArray(raw) ? raw : []).filter((id): id is DashboardWidgetId => WIDGET_IDS.has(id))
      );
    } catch {
      return new Set();
    }
  }

  private saveHiddenWidgets(): void {
    try {
      localStorage.setItem(this.hiddenKey(), JSON.stringify([...this.hiddenWidgets()]));
    } catch {
      /* storage unavailable: the choice lasts until the page is closed */
    }
  }

  shown(id: DashboardWidgetId): boolean {
    return !this.hiddenWidgets().has(id);
  }

  toggleWidget(id: DashboardWidgetId): void {
    this.hiddenWidgets.update((set) => {
      const next = new Set(set);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    this.saveHiddenWidgets();
  }

  showAllWidgets(): void {
    this.hiddenWidgets.set(new Set());
    this.saveHiddenWidgets();
  }

  hiddenCount(): number {
    return this.hiddenWidgets().size;
  }

  monthLabel(): string {
    return this.months.find((m) => m.v === this.month)?.n || String(this.month);
  }

  /** Parent budget categories only (excludes subcategories / merchants). */
  categoryRows(): UtilizationRow[] {
    const rows = this.budget()?.report?.rows || [];
    return rows.filter((r) => r.row_type === 'group' || r.row_type === 'unmapped');
  }

  spendByCategory(): UtilizationRow[] {
    return this.categoryRows().filter((r) => r.row_type === 'group' && +r.actual > 0);
  }

  spendTotal(): number {
    return this.spendByCategory().reduce((sum, r) => sum + (+r.actual || 0), 0);
  }

  spendPercent(row: UtilizationRow): number {
    const total = this.spendTotal();
    if (!total) return 0;
    return Math.round(((+row.actual || 0) / total) * 1000) / 10;
  }

  downloadReport(): void {
    const cur = this.reportCurrency || this.locale.reportCurrency();
    const lines: string[] = [];
    if (this.reportScope === 'year' && this.yearly()) {
      const y = this.yearly()!;
      lines.push(`Finance Tracker Report — ${y.year} (${cur})`);
      lines.push(`Report currency,${cur}`);
      lines.push(`Income,${y.income_total}`);
      lines.push(`Expense,${y.expense_total}`);
      lines.push(`Net,${y.net}`);
      lines.push('');
      lines.push('Month,Income,Expense,Net,Budget Util %,Remaining');
      for (const m of y.months) {
        lines.push(
          [
            m.month_name,
            m.income_total,
            m.expense_total,
            m.net,
            m.overall_util ?? '',
            m.remaining,
          ].join(',')
        );
      }
    } else {
      const b = this.budget();
      const spendRows = this.spendByCategory();
      lines.push(`Finance Tracker Report — ${this.monthLabel()} ${this.year} (${cur})`);
      lines.push(`Report currency,${cur}`);
      lines.push(`Income,${b?.income_total ?? ''}`);
      lines.push(`Expense,${b?.expense_total ?? ''}`);
      lines.push(`Utilization,${b?.report?.overall_util ?? ''}%`);
      lines.push(`Remaining,${b?.report?.remaining ?? ''}`);
      lines.push('');
      lines.push('Category,Forecast,Actual,Util %,Status');
      for (const r of this.categoryRows()) {
        lines.push(
          [
            `"${r.category_name.replace(/"/g, '""')}"`,
            r.forecast,
            r.actual,
            r.utilization_pct ?? '',
            r.status,
          ].join(',')
        );
      }
      if (spendRows.length) {
        lines.push('');
        lines.push(`Spend by category (${cur}),Amount,Percent`);
        for (const row of spendRows) {
          lines.push(`${row.category_name},${row.actual},${this.spendPercent(row)}`);
        }
      }
    }

    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download =
      this.reportScope === 'year'
        ? `finance-report-${this.year}.csv`
        : `finance-report-${this.year}-${String(this.month).padStart(2, '0')}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    this.toast.success('Report downloaded.');
  }

  printReport(): void {
    window.print();
  }
}
