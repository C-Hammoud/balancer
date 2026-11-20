import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { forkJoin, map, of, switchMap } from 'rxjs';
import { BudgetingService } from '../../../core/budgeting.service';
import { FinanceDataRefreshService } from '../../../core/finance-data-refresh.service';
import { Transaction } from '../../../core/models';
import { AmountPipe } from '../../../shared/amount.pipe';

const SHOWN = 8;

function monthKey(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

function newestFirst(a: Transaction, b: Transaction): number {
  return (b.date || '').localeCompare(a.date || '') || (b.time || '').localeCompare(a.time || '');
}

/** Dashboard widget: the latest transactions (this month, topped up from last month). */
@Component({
  selector: 'app-recent-transactions-widget',
  standalone: true,
  imports: [RouterLink, AmountPipe],
  styleUrl: './widget.scss',
  template: `
    <section class="widget" aria-labelledby="recent-title">
      <header class="widget-head">
        <h2 id="recent-title">Recent transactions</h2>
        <a routerLink="/budgeting/transactions">All transactions</a>
      </header>
      @if (loading()) {
        <p class="empty">Loading…</p>
      } @else if (error()) {
        <p class="empty">Could not load transactions.</p>
      } @else if (!items().length) {
        <p class="empty">No transactions yet. <a routerLink="/budgeting/transactions">Add one</a></p>
      } @else {
        <ul class="rows">
          @for (t of items(); track t.id) {
            <li>
              <span class="main">
                <strong>{{ t.description || 'Unassigned' }}</strong>
                <span class="sub">{{ t.date }} · {{ categoryLabel(t) }}</span>
              </span>
              <span class="amount" [class.pos]="t.direction === 'income'">
                {{ sign(t) }}{{ magnitude(t) | amount }} {{ t.currency || 'USD' }}
              </span>
            </li>
          }
        </ul>
      }
    </section>
  `,
})
export class RecentTransactionsWidgetComponent implements OnInit {
  private api = inject(BudgetingService);
  private refresh = inject(FinanceDataRefreshService);
  private destroyRef = inject(DestroyRef);

  items = signal<Transaction[]>([]);
  loading = signal(true);
  error = signal(false);
  /** Subcategory id → parent category name. */
  private groupBySub = new Map<string, string>();

  ngOnInit(): void {
    this.api.categories().subscribe({
      next: (c) => {
        const groups = new Map(c.groups.map((g) => [g.id, g.name]));
        this.groupBySub = new Map(c.categories.map((s) => [s.id, groups.get(s.group_id) || s.group_name || '']));
        this.items.update((rows) => [...rows]); // re-render labels
      },
      error: () => undefined,
    });
    this.load();
    this.refresh.changed$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.load());
  }

  load(): void {
    const now = new Date();
    const thisMonth = monthKey(now);
    const lastMonth = monthKey(new Date(now.getFullYear(), now.getMonth() - 1, 1));
    this.api
      .transactions(thisMonth)
      .pipe(
        switchMap((rows) =>
          rows.length >= SHOWN
            ? of(rows)
            : forkJoin([of(rows), this.api.transactions(lastMonth)]).pipe(map(([a, b]) => [...a, ...b]))
        )
      )
      .subscribe({
        next: (rows) => {
          this.items.set([...rows].sort(newestFirst).slice(0, SHOWN));
          this.error.set(false);
          this.loading.set(false);
        },
        error: () => {
          this.error.set(true);
          this.loading.set(false);
        },
      });
  }

  categoryLabel(t: Transaction): string {
    if (t.direction === 'income') return 'Income';
    if (t.direction === 'transfer') return 'Transfer';
    if (t.commitment_id) return 'Commitment payment';
    return (t.category_id && this.groupBySub.get(t.category_id)) || 'Unassigned';
  }

  /** Amounts may be stored signed; the sign is shown separately. */
  magnitude(t: Transaction): number {
    return Math.abs(Number(t.amount) || 0);
  }

  sign(t: Transaction): string {
    if (t.direction === 'income') return '+';
    if (t.direction === 'transfer') return '';
    return '−';
  }
}
