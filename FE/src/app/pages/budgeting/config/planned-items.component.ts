import { Component, HostListener, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { BudgetingService } from '../../../core/budgeting.service';
import { RiskService } from '../../../core/risk.service';
import { ToastService } from '../../../core/toast.service';
import { Account, PlannedItem, PlannedItemFrequency, PlannedItemKind } from '../../../core/models';

const FREQUENCIES: { value: PlannedItemFrequency; label: string }[] = [
  { value: 'once', label: 'Once' },
  { value: 'weekly', label: 'Weekly' },
  { value: 'biweekly', label: 'Every two weeks' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'yearly', label: 'Yearly' },
];

/** Expected future money in or out (rent, subscriptions, a one-off bill) used by the risk check. */
@Component({
  selector: 'app-planned-items',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './planned-items.component.html',
  styleUrl: './planned-items.component.scss',
})
export class PlannedItemsComponent implements OnInit {
  private risk = inject(RiskService);
  private budgeting = inject(BudgetingService);
  private fb = inject(FormBuilder);
  private toast = inject(ToastService);

  readonly frequencies = FREQUENCIES;

  items = signal<PlannedItem[]>([]);
  accounts = signal<Account[]>([]);
  totals = signal({ currency: '', income: '0', expense: '0' });
  loading = signal(true);
  editingId = signal<string | null>(null);

  form = this.fb.nonNullable.group({
    name: ['', Validators.required],
    kind: ['expense' as PlannedItemKind],
    amount: ['', Validators.required],
    currency: ['USD'],
    frequency: ['monthly' as PlannedItemFrequency],
    start_date: [new Date().toISOString().slice(0, 10), Validators.required],
    end_date: [''],
    account_id: [''],
    is_essential: [false],
    is_active: [true],
  });

  ngOnInit(): void {
    this.budgeting.accounts(true).subscribe({ next: (a) => this.accounts.set(a), error: () => undefined });
    this.reload();
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.editingId()) this.cancelEdit();
  }

  reload(): void {
    this.loading.set(true);
    this.risk.plannedItems().subscribe({
      next: (r) => {
        this.items.set(r.items);
        this.totals.set({ currency: r.currency, income: r.monthly_income, expense: r.monthly_expense });
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not load planned items.');
      },
    });
  }

  frequencyLabel(value: string): string {
    return FREQUENCIES.find((f) => f.value === value)?.label ?? value;
  }

  accountName(id: string): string {
    return this.accounts().find((a) => a.id === id)?.name ?? '';
  }

  edit(item: PlannedItem): void {
    this.editingId.set(item.id);
    this.form.setValue({
      name: item.name,
      kind: item.kind,
      amount: item.amount,
      currency: item.currency,
      frequency: item.frequency,
      start_date: item.start_date,
      end_date: item.end_date ?? '',
      account_id: item.account_id,
      is_essential: item.is_essential,
      is_active: item.is_active,
    });
  }

  cancelEdit(): void {
    this.editingId.set(null);
    this.form.reset();
  }

  submit(): void {
    if (this.form.invalid) {
      this.toast.error('Enter a name, an amount and a start date.');
      return;
    }
    const raw = this.form.getRawValue();
    const payload = { ...raw, end_date: raw.end_date || null };
    const id = this.editingId();
    const req = id ? this.risk.updatePlannedItem(id, payload) : this.risk.createPlannedItem(payload);
    req.subscribe({
      next: () => {
        this.toast.success(id ? 'Planned item updated.' : 'Planned item added.');
        this.cancelEdit();
        this.reload();
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not save the planned item.'),
    });
  }

  toggleActive(item: PlannedItem): void {
    this.risk.updatePlannedItem(item.id, { is_active: !item.is_active }).subscribe({
      next: () => this.reload(),
      error: (err) => this.toast.fromHttpError(err, 'Could not update the planned item.'),
    });
  }

  remove(item: PlannedItem): void {
    if (!confirm(`Delete “${item.name}”?`)) return;
    this.risk.deletePlannedItem(item.id).subscribe({
      next: () => {
        this.toast.success('Planned item deleted.');
        if (this.editingId() === item.id) this.cancelEdit();
        this.reload();
      },
      error: (err) => this.toast.fromHttpError(err, 'Delete failed.'),
    });
  }
}
