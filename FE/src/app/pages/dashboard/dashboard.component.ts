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

const DISMISS_KEY = 'ft_dismiss_accounts_prompt';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink, RiskSummaryComponent],
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

  ngOnInit(): void {
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
    return `${val} ${cur}`;
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

  maxExpense(): number {
    const rows = this.yearly()?.months || [];
    const vals = rows.map((r) => Math.abs(+r.expense_total || 0));
    return Math.max(...vals, 1);
  }

  barHeight(row: YearlyMonthRow): number {
    const v = Math.abs(+row.expense_total || 0);
    return Math.max(6, Math.round((v / this.maxExpense()) * 100));
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
