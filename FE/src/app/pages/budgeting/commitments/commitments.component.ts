import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { BudgetingService } from '../../../core/budgeting.service';
import { Commitment } from '../../../core/models';
import { ToastService } from '../../../core/toast.service';
import { LocaleService } from '../../../core/locale.service';

@Component({
  selector: 'app-commitments',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink],
  templateUrl: './commitments.component.html',
  styleUrl: './commitments.component.scss',
})
export class CommitmentsComponent implements OnInit {
  private api = inject(BudgetingService);
  private fb = inject(FormBuilder);
  private toast = inject(ToastService);
  private locale = inject(LocaleService);
  private router = inject(Router);

  readonly currencyOptions = this.locale.currencies;

  items = signal<Commitment[]>([]);
  loading = signal(true);
  showForm = signal(false);

  form = this.fb.nonNullable.group({
    name: ['', Validators.required],
    amount: ['', Validators.required],
    currency: [this.locale.defaultCurrency(), Validators.required],
    start_date: [this.locale.todayIso(), Validators.required],
    term_months: [12, Validators.required],
    frequency: ['monthly', Validators.required],
    payment_amount: ['', Validators.required],
    balloon: ['0'],
    reminder_enabled: [true],
    reminder_days_before: [3, [Validators.required, Validators.min(0), Validators.max(90)]],
  });

  ngOnInit(): void {
    this.form.controls.currency.setValue(this.locale.defaultCurrency());
    this.reload();
  }

  toggleForm(): void {
    const opening = !this.showForm();
    this.showForm.set(opening);
    if (opening) {
      this.form.controls.currency.setValue(this.locale.defaultCurrency());
    }
  }

  reload(): void {
    this.loading.set(true);
    this.api.commitments().subscribe({
      next: (rows) => {
        this.items.set(rows);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not load commitments.');
      },
    });
  }

  open(c: Commitment): void {
    this.router.navigate(['/budgeting/commitments', c.id]);
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.toast.error('Please fill in the required fields.');
      return;
    }
    this.api.createCommitment(this.form.getRawValue()).subscribe({
      next: (res) => {
        this.toast.success('Commitment saved with payment schedule.');
        this.router.navigate(['/budgeting/commitments', res.id]);
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not add commitment.'),
    });
  }

  remove(c: Commitment, event: Event): void {
    event.stopPropagation();
    if (!confirm(`Delete commitment “${c.name}” and its schedule?`)) return;
    this.api.deleteCommitment(c.id).subscribe({
      next: () => {
        this.toast.success('Commitment deleted.');
        this.reload();
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not delete commitment.'),
    });
  }

  progressPct(c: Commitment): number {
    const total = c.payments_total || 0;
    if (!total) return 0;
    return Math.min(100, Math.round(((c.payments_completed || 0) / total) * 100));
  }
}
