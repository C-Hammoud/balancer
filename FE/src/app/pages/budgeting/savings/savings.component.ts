import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators, FormsModule } from '@angular/forms';
import { BudgetingService } from '../../../core/budgeting.service';
import { SavingsRow } from '../../../core/models';
import { ToastService } from '../../../core/toast.service';

@Component({
  selector: 'app-savings',
  standalone: true,
  imports: [CommonModule, FormsModule, ReactiveFormsModule],
  templateUrl: './savings.component.html',
  styleUrl: './savings.component.scss',
})
export class SavingsComponent implements OnInit {
  private api = inject(BudgetingService);
  private fb = inject(FormBuilder);
  private toast = inject(ToastService);

  items = signal<SavingsRow[]>([]);
  loading = signal(true);
  editing = signal<SavingsRow | null>(null);

  form = this.fb.nonNullable.group({
    year: [new Date().getFullYear(), Validators.required],
    month: [new Date().getMonth() + 1, Validators.required],
    target: ['0', Validators.required],
    actual: [''],
    goal_status: ['pending', Validators.required],
  });

  ngOnInit(): void {
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

  edit(row: SavingsRow): void {
    this.editing.set(row);
    this.form.patchValue({
      year: row.year,
      month: row.month,
      target: String(row.target),
      actual: row.actual != null ? String(row.actual) : '',
      goal_status: row.goal_status || 'pending',
    });
  }

  submit(): void {
    if (this.form.invalid) {
      this.toast.error('Please fill in the required fields.');
      return;
    }
    const raw = this.form.getRawValue();
    this.api
      .updateSavings(raw.year, raw.month, {
        target: raw.target,
        actual: (raw.actual || null) as any,
        goal_status: raw.goal_status,
      })
      .subscribe({
        next: () => {
          this.toast.success('Savings saved successfully.');
          this.editing.set(null);
          this.reload();
        },
        error: (err) => this.toast.fromHttpError(err, 'Could not save savings.'),
      });
  }
}
