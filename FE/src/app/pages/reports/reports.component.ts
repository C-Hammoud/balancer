import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Subscription } from 'rxjs';
import { BudgetingService } from '../../core/budgeting.service';
import { LocaleService } from '../../core/locale.service';
import { AmountPipe } from '../../shared/amount.pipe';
import { ReportBuilderComponent, ReportPeriod } from '../../shared/report-builder/report-builder.component';
import { periodLabel } from '../../shared/report-builder/report-options';

interface PreviewTotals {
  label: string;
  income: number;
  expense: number;
  net: number;
  currency: string;
}

/** Reports: choose a period and a file type and download, with a preview of the totals. */
@Component({
  selector: 'app-reports',
  standalone: true,
  imports: [RouterLink, AmountPipe, ReportBuilderComponent],
  templateUrl: './reports.component.html',
  styleUrl: './reports.component.scss',
})
export class ReportsComponent {
  private api = inject(BudgetingService);
  private locale = inject(LocaleService);

  readonly currency = this.locale.defaultCurrency();
  readonly startYear = new Date().getFullYear();
  readonly startMonth = new Date().getMonth() + 1;

  preview = signal<PreviewTotals | null>(null);
  loading = signal(false);
  private request?: Subscription;
  private lastKey = '';

  onPeriod(p: ReportPeriod): void {
    const key = `${p.scope}-${p.year}-${p.month}`;
    if (key === this.lastKey) return;
    this.lastKey = key;
    this.request?.unsubscribe();
    this.loading.set(true);
    const label = periodLabel(p.scope, p.year, p.month);
    const done = (income: string, expense: string, currency?: string) => {
      const i = Number(income) || 0;
      const e = Number(expense) || 0;
      this.preview.set({ label, income: i, expense: e, net: i - e, currency: currency || this.currency });
      this.loading.set(false);
    };
    const fail = () => {
      this.preview.set(null);
      this.loading.set(false);
    };
    this.request =
      p.scope === 'year'
        ? this.api.yearly(p.year).subscribe({
            next: (y) => done(y.income_total, y.expense_total, y.report_currency),
            error: fail,
          })
        : this.api.dashboard(p.year, p.month).subscribe({
            next: (d) => done(d.income_total, d.expense_total, d.report_currency),
            error: fail,
          });
  }
}
