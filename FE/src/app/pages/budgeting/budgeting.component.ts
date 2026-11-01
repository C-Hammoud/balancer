import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { BudgetingService } from '../../core/budgeting.service';
import { BudgetDashboard, UNMAPPED_CATEGORY_ID } from '../../core/models';
import { ToastService } from '../../core/toast.service';

@Component({
  selector: 'app-budgeting-overview',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './budgeting.component.html',
  styleUrl: './budgeting.component.scss',
})
export class BudgetingComponent implements OnInit {
  private api = inject(BudgetingService);
  private toast = inject(ToastService);

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

  dash = signal<BudgetDashboard | null>(null);
  loading = signal(true);

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.api.dashboard(this.year, this.month).subscribe({
      next: (d) => {
        this.dash.set(d);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not load budgeting overview.');
      },
    });
  }

  utilWidth(util: string | null | undefined): number {
    const n = util ? Number(util) : 0;
    return Math.min(Math.max(n, 0), 100);
  }
}
