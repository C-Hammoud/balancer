import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { BudgetingService } from '../../../core/budgeting.service';
import { UtilizationReport, UtilizationRow, UNMAPPED_CATEGORY_ID } from '../../../core/models';
import { ToastService } from '../../../core/toast.service';
import { LocaleService } from '../../../core/locale.service';

@Component({
  selector: 'app-utilization',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './utilization.component.html',
  styleUrl: './utilization.component.scss',
})
export class UtilizationComponent implements OnInit {
  private api = inject(BudgetingService);
  private toast = inject(ToastService);
  private locale = inject(LocaleService);

  readonly unmappedId = UNMAPPED_CATEGORY_ID;
  reportCurrency = this.locale.reportCurrency();

  now = new Date();
  year = this.now.getFullYear();
  month = this.now.getMonth() + 1;
  years = Array.from({ length: 5 }, (_, i) => this.year - 2 + i);
  months = [
    { v: 1, n: 'Jan' }, { v: 2, n: 'Feb' }, { v: 3, n: 'Mar' }, { v: 4, n: 'Apr' },
    { v: 5, n: 'May' }, { v: 6, n: 'Jun' }, { v: 7, n: 'Jul' }, { v: 8, n: 'Aug' },
    { v: 9, n: 'Sep' }, { v: 10, n: 'Oct' }, { v: 11, n: 'Nov' }, { v: 12, n: 'Dec' },
  ];
  filter: 'all' | 'warn' | 'critical' | 'over' | 'ok' = 'all';

  report = signal<UtilizationReport | null>(null);
  loading = signal(true);

  ngOnInit(): void {
    this.reportCurrency = this.locale.defaultCurrency();
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.api.utilization(this.year, this.month).subscribe({
      next: (r) => {
        this.report.set(r);
        if (r.report_currency) {
          this.reportCurrency = r.report_currency;
        }
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not load utilization report.');
      },
    });
  }

  rows(): UtilizationRow[] {
    const all = this.report()?.rows || [];
    if (this.filter === 'all') return all;
    return all.filter((r) => r.status === this.filter);
  }

  fmt(val: string | number | null | undefined): string {
    const cur = this.report()?.report_currency || this.reportCurrency;
    if (val == null || val === '') return `— ${cur}`;
    return `${val} ${cur}`;
  }

  utilWidth(util: string | null | undefined): number {
    const n = util ? Number(util) : 0;
    return Math.min(Math.max(n, 0), 100);
  }
}
