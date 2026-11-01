import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { BudgetingService } from '../../../core/budgeting.service';
import { FinancialStanding } from '../../../core/models';
import { ToastService } from '../../../core/toast.service';

@Component({
  selector: 'app-financial-standing',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './financial-standing.component.html',
  styleUrl: './financial-standing.component.scss',
})
export class FinancialStandingComponent implements OnInit {
  private api = inject(BudgetingService);
  private fb = inject(FormBuilder);
  private toast = inject(ToastService);

  items = signal<FinancialStanding[]>([]);
  loading = signal(true);
  showForm = signal(false);

  form = this.fb.nonNullable.group({
    snapshot_date: [new Date().toISOString().slice(0, 10), Validators.required],
    total_assets: ['0'],
    current_assets: ['0'],
    fixed_assets: ['0'],
    total_liabilities: ['0'],
    short_term_liabilities: ['0'],
    long_term_liabilities: ['0'],
    notes: [''],
  });

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.api.financialStanding().subscribe({
      next: (rows) => {
        this.items.set(rows);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not load financial standing.');
      },
    });
  }

  netWorth(s: FinancialStanding): number {
    return Number(s.total_assets || 0) - Number(s.total_liabilities || 0);
  }

  submit(): void {
    if (this.form.invalid) {
      this.toast.error('Please fill in the required fields.');
      return;
    }
    this.api.createFinancialStanding(this.form.getRawValue()).subscribe({
      next: () => {
        this.toast.success('Snapshot saved successfully.');
        this.showForm.set(false);
        this.reload();
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not save snapshot.'),
    });
  }
}
