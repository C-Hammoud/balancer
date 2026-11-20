import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AmountPipe } from '../../../shared/amount.pipe';
import { FormBuilder, ReactiveFormsModule, Validators, FormsModule } from '@angular/forms';
import { BudgetingService } from '../../../core/budgeting.service';
import { LocaleService } from '../../../core/locale.service';
import { SavingsRow } from '../../../core/models';
import { ToastService } from '../../../core/toast.service';

@Component({
  selector: 'app-savings',
  standalone: true,
  imports: [CommonModule, FormsModule, ReactiveFormsModule, AmountPipe],
  templateUrl: './savings.component.html',
  styleUrl: './savings.component.scss',
})
export class SavingsComponent implements OnInit {
  private api = inject(BudgetingService);
  private fb = inject(FormBuilder);
  private toast = inject(ToastService);
  private locale = inject(LocaleService);

  readonly currencyOptions = this.locale.currencies;

  items = signal<SavingsRow[]>([]);
  loading = signal(true);
  editing = signal(false);

  form = this.fb.nonNullable.group({
    year: [new Date().getFullYear(), Validators.required],
    month: [new Date().getMonth() + 1, Validators.required],
    currency: [this.locale.defaultCurrency(), Validators.required],
    target: ['0', Validators.required],
    actual: [''],
    goal_status: ['pending', Validators.required],
  });

  ngOnInit(): void {
    this.locale.loadMeta().subscribe();
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.api.savings().subscribe({
      next: (rows) => {
        this.items.set(rows);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not load savings.');
      },
    });
  }

  add(): void {
    const now = new Date();
    this.form.reset({
      year: now.getFullYear(),
      month: now.getMonth() + 1,
      currency: this.locale.defaultCurrency(),
      target: '0',
      actual: '',
      goal_status: 'pending',
    });
    this.editing.set(true);
  }

  edit(row: SavingsRow): void {
    this.form.reset({
      year: row.year,
      month: row.month,
      currency: row.currency || this.locale.defaultCurrency(),
      target: String(Number(row.target)),
      // Only a typed actual is editable; the calculated one is recalculated in the chosen currency.
      actual: row.actual_is_manual && row.actual != null ? String(Number(row.actual)) : '',
      goal_status: row.goal_status || 'pending',
    });
    this.editing.set(true);
  }

  submit(): void {
    if (this.form.invalid) {
      this.toast.error('Please fill in the required fields.');
      return;
    }
    const raw = this.form.getRawValue();
    this.api
      .updateSavings(raw.year, raw.month, {
        currency: raw.currency,
        target: raw.target,
        actual: raw.actual === '' ? null : raw.actual,
        goal_status: raw.goal_status,
      })
      .subscribe({
        next: () => {
          this.toast.success('Savings saved.');
          this.editing.set(false);
          this.reload();
        },
        error: (err) => this.toast.fromHttpError(err, 'Could not save savings.'),
      });
  }

  progress(row: SavingsRow): number {
    return Math.max(0, Math.min(Number(row.progress_pct) || 0, 100));
  }
}
