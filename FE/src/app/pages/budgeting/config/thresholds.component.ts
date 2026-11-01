import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { BudgetingService } from '../../../core/budgeting.service';
import { CategoryGroupResponse, ThresholdRow } from '../../../core/models';
import { ToastService } from '../../../core/toast.service';

@Component({
  selector: 'app-thresholds',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './thresholds.component.html',
  styleUrl: './thresholds.component.scss',
})
export class ThresholdsComponent implements OnInit {
  private api = inject(BudgetingService);
  private fb = inject(FormBuilder);
  private toast = inject(ToastService);

  items = signal<ThresholdRow[]>([]);
  categories = signal<CategoryGroupResponse['categories']>([]);
  loading = signal(true);

  form = this.fb.nonNullable.group({
    category_id: [''],
    warn_pct: [80, Validators.required],
    critical_pct: [100, Validators.required],
    email_enabled: [true],
  });

  ngOnInit(): void {
    this.api.categories().subscribe({
      next: (c) => this.categories.set(c.categories),
      error: () => this.categories.set([]),
    });
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.api.thresholds().subscribe({
      next: (rows) => {
        this.items.set(rows);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not load thresholds.');
      },
    });
  }

  submit(): void {
    if (this.form.invalid) {
      this.toast.error('Please fill in the required fields.');
      return;
    }
    const raw = this.form.getRawValue();
    this.api
      .saveThreshold({
        category_id: raw.category_id || null,
        warn_pct: raw.warn_pct,
        critical_pct: raw.critical_pct,
        email_enabled: raw.email_enabled,
      })
      .subscribe({
        next: () => {
          this.toast.success('Threshold saved successfully.');
          this.reload();
        },
        error: (err) => this.toast.fromHttpError(err, 'Could not save threshold.'),
      });
  }

  remove(id: string): void {
    if (!confirm('Delete this threshold?')) return;
    this.api.deleteThreshold(id).subscribe({
      next: () => {
        this.toast.success('Threshold deleted.');
        this.reload();
      },
      error: (err) => this.toast.fromHttpError(err, 'Delete failed.'),
    });
  }
}
