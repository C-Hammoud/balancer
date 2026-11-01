import { Component, HostListener, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { BudgetingService } from '../../../core/budgeting.service';
import { Account, AccountBalance, AccountType } from '../../../core/models';
import { RiskService } from '../../../core/risk.service';
import { ToastService } from '../../../core/toast.service';

const ACCOUNT_TYPES: { value: AccountType; label: string }[] = [
  { value: 'bank', label: 'Bank' },
  { value: 'credit_card', label: 'Credit card' },
  { value: 'wallet', label: 'Wallet' },
  { value: 'other', label: 'Other' },
];

@Component({
  selector: 'app-income-sources',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './income-sources.component.html',
  styleUrl: './income-sources.component.scss',
})
export class IncomeSourcesComponent implements OnInit {
  private api = inject(BudgetingService);
  private risk = inject(RiskService);
  private fb = inject(FormBuilder);
  private toast = inject(ToastService);

  readonly accountTypes = ACCOUNT_TYPES;

  items = signal<Account[]>([]);
  loading = signal(true);
  modalOpen = signal(false);
  modalMode = signal<'add' | 'edit'>('add');
  editingId = signal<string | null>(null);

  form = this.fb.nonNullable.group({
    name: ['', Validators.required],
    account_type: ['bank' as AccountType],
    order: [0],
    is_active: [true],
    is_default_for_expenses: [false],
  });

  /** Balance per account from the server (all transactions, per currency + converted total). */
  balances = signal<Record<string, AccountBalance>>({});
  balanceCurrency = signal('');

  ngOnInit(): void {
    this.reload();
  }

  private loadBalances(): void {
    this.risk.accountBalances().subscribe({
      next: (r) => {
        this.balanceCurrency.set(r.currency);
        this.balances.set(Object.fromEntries(r.accounts.map((a) => [a.account_id, a])));
      },
      error: () => this.balances.set({}),
    });
  }

  /** "USD 120.00 · LBP -5,000.00" when an account holds several currencies. */
  currencyBreakdown(b: AccountBalance | undefined): string {
    if (!b) return '';
    const entries = Object.entries(b.balances);
    if (entries.length < 2) return '';
    return entries.map(([cur, v]) => `${cur} ${Number(v).toLocaleString()}`).join(' · ');
  }

  isNegative(b: AccountBalance | undefined): boolean {
    return !!b && Number(b.total) < 0;
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.modalOpen()) this.closeModal();
  }

  accountTypeLabel(value: AccountType | string): string {
    return ACCOUNT_TYPES.find((t) => t.value === value)?.label || value;
  }

  reload(): void {
    this.loading.set(true);
    this.loadBalances();
    this.api.accounts().subscribe({
      next: (rows) => {
        this.items.set(rows);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not load accounts.');
      },
    });
  }

  private resetForm(order = 0): void {
    this.form.reset({
      name: '',
      account_type: 'bank',
      order,
      is_active: true,
      is_default_for_expenses: false,
    });
  }

  openAdd(): void {
    this.modalMode.set('add');
    this.editingId.set(null);
    this.resetForm(this.items().length);
    this.modalOpen.set(true);
  }

  openEdit(s: Account): void {
    this.modalMode.set('edit');
    this.editingId.set(s.id);
    this.form.setValue({
      name: s.name,
      account_type: s.account_type || 'bank',
      order: s.order,
      is_active: s.is_active,
      is_default_for_expenses: !!s.is_default_for_expenses,
    });
    this.modalOpen.set(true);
  }

  closeModal(): void {
    this.modalOpen.set(false);
    this.editingId.set(null);
    this.resetForm();
  }

  submit(): void {
    if (this.form.invalid) {
      this.toast.error('Enter an account name.');
      return;
    }
    const raw = this.form.getRawValue();
    const id = this.editingId();
    const req = id ? this.api.updateAccount(id, raw) : this.api.createAccount(raw);
    req.subscribe({
      next: () => {
        this.toast.success(id ? 'Account updated.' : 'Account added.');
        this.closeModal();
        this.reload();
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not save account.'),
    });
  }

  remove(s: Account): void {
    if (!confirm(`Delete account “${s.name}”?`)) return;
    this.api.deleteAccount(s.id).subscribe({
      next: () => {
        this.toast.success('Account deleted.');
        this.reload();
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not delete account.'),
    });
  }

  removeFromModal(): void {
    const id = this.editingId();
    if (!id) return;
    const account = this.items().find((s) => s.id === id);
    if (!account) return;
    if (!confirm(`Delete account “${account.name}”?`)) return;
    this.api.deleteAccount(id).subscribe({
      next: () => {
        this.toast.success('Account deleted.');
        this.closeModal();
        this.reload();
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not delete account.'),
    });
  }
}
