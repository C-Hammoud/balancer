import { Component, DestroyRef, OnChanges, OnInit, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { AccountBalance, AccountType } from '../../../core/models';
import { RiskService } from '../../../core/risk.service';
import { FinanceDataRefreshService } from '../../../core/finance-data-refresh.service';
import { AmountPipe, formatAmount } from '../../../shared/amount.pipe';

const TYPE_LABELS: Record<AccountType, string> = {
  bank: 'Bank',
  credit_card: 'Credit card',
  wallet: 'Wallet',
  other: 'Other',
};

/** Dashboard widget: every account's balance, and the total, in the main currency. */
@Component({
  selector: 'app-account-balances-widget',
  standalone: true,
  imports: [RouterLink, AmountPipe],
  styleUrl: './widget.scss',
  template: `
    <section class="widget" aria-labelledby="balances-title">
      <header class="widget-head">
        <h2 id="balances-title">Account balances</h2>
        <a routerLink="/budgeting/config/accounts">Accounts</a>
      </header>
      @if (loading()) {
        <p class="empty">Loading…</p>
      } @else if (error()) {
        <p class="empty">Could not load balances.</p>
      } @else if (!accounts().length) {
        <p class="empty">No accounts yet. <a routerLink="/budgeting/config/accounts">Add one</a></p>
      } @else {
        <ul class="rows">
          @for (a of accounts(); track a.account_id) {
            <li>
              <span class="main">
                <strong>{{ a.name }}</strong>
                <span class="sub">{{ typeLabel(a) }}@if (breakdown(a); as b) { · {{ b }} }</span>
              </span>
              <span class="amount" [class.neg]="+a.total < 0">{{ a.total | amount }} {{ currency() }}</span>
            </li>
          }
        </ul>
        <div class="total">
          <strong>Total</strong>
          <strong [class.neg]="total() < 0">{{ total() | amount }} {{ currency() }}</strong>
        </div>
      }
    </section>
  `,
})
export class AccountBalancesWidgetComponent implements OnInit, OnChanges {
  private risk = inject(RiskService);
  private refresh = inject(FinanceDataRefreshService);
  private destroyRef = inject(DestroyRef);

  /** Main (report) currency the totals are converted to. */
  reportCurrency = input('');

  accounts = signal<AccountBalance[]>([]);
  currency = signal('');
  total = signal(0);
  loading = signal(true);
  error = signal(false);
  private started = false;

  ngOnInit(): void {
    this.started = true;
    this.load();
    this.refresh.changed$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.load());
  }

  ngOnChanges(): void {
    if (this.started) this.load();
  }

  load(): void {
    this.risk.accountBalances(this.reportCurrency() || undefined).subscribe({
      next: (res) => {
        const active = res.accounts.filter((a) => a.is_active);
        this.accounts.set(active);
        this.currency.set(res.currency);
        this.total.set(active.reduce((sum, a) => sum + (Number(a.total) || 0), 0));
        this.error.set(false);
        this.loading.set(false);
      },
      error: () => {
        this.error.set(true);
        this.loading.set(false);
      },
    });
  }

  typeLabel(a: AccountBalance): string {
    return TYPE_LABELS[a.account_type] ?? 'Account';
  }

  /** "SAR 1,200.00 · USD 50.00" when the account holds more than one currency. */
  breakdown(a: AccountBalance): string {
    const entries = Object.entries(a.balances || {});
    if (entries.length < 2) return '';
    return entries.map(([cur, v]) => `${cur} ${formatAmount(v)}`).join(' · ');
  }
}
