import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { BudgetingService } from '../../../core/budgeting.service';
import { FinanceDataRefreshService } from '../../../core/finance-data-refresh.service';
import { AmountPipe } from '../../../shared/amount.pipe';
import { UpcomingPayment, upcomingDue } from '../dashboard.helpers';

const WINDOW_DAYS = 30;

/** Dashboard widget: commitment installments due in the next 30 days, overdue ones first. */
@Component({
  selector: 'app-upcoming-payments-widget',
  standalone: true,
  imports: [RouterLink, AmountPipe],
  styleUrl: './widget.scss',
  template: `
    <section class="widget" aria-labelledby="upcoming-title">
      <header class="widget-head">
        <h2 id="upcoming-title">Upcoming payments</h2>
        <a routerLink="/budgeting/commitments">Commitments</a>
      </header>
      @if (loading()) {
        <p class="empty">Loading…</p>
      } @else if (error()) {
        <p class="empty">Could not load commitments.</p>
      } @else if (!payments().length) {
        <p class="empty">Nothing due in the next {{ windowDays }} days.</p>
      } @else {
        <ul class="rows">
          @for (p of payments(); track p.commitment.id) {
            <li>
              <span class="main">
                <a [routerLink]="['/budgeting/commitments', p.commitment.id]"><strong>{{ p.commitment.name }}</strong></a>
                <span class="sub">Due {{ p.dueDate }}</span>
              </span>
              <span class="amount">
                <span>{{ p.commitment.next_due_amount | amount }} {{ p.commitment.currency || 'USD' }}</span>
                @if (p.daysUntil < 0) {
                  <span class="pill danger">Overdue {{ -p.daysUntil }} day(s)</span>
                } @else if (p.daysUntil === 0) {
                  <span class="pill warn">Due today</span>
                } @else {
                  <span class="pill" [class.warn]="p.daysUntil <= 3">In {{ p.daysUntil }} day(s)</span>
                }
              </span>
            </li>
          }
        </ul>
      }
    </section>
  `,
})
export class UpcomingPaymentsWidgetComponent implements OnInit {
  private api = inject(BudgetingService);
  private refresh = inject(FinanceDataRefreshService);
  private destroyRef = inject(DestroyRef);

  readonly windowDays = WINDOW_DAYS;
  payments = signal<UpcomingPayment[]>([]);
  loading = signal(true);
  error = signal(false);

  ngOnInit(): void {
    this.load();
    this.refresh.changed$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.load());
  }

  load(): void {
    this.api.commitments().subscribe({
      next: (rows) => {
        this.payments.set(upcomingDue(rows, new Date(), WINDOW_DAYS));
        this.error.set(false);
        this.loading.set(false);
      },
      error: () => {
        this.error.set(true);
        this.loading.set(false);
      },
    });
  }
}
