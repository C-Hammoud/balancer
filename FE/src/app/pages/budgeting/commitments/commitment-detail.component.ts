import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { BudgetingService } from '../../../core/budgeting.service';
import { Commitment, CommitmentScheduleLine } from '../../../core/models';
import { ToastService } from '../../../core/toast.service';

@Component({
  selector: 'app-commitment-detail',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink],
  templateUrl: './commitment-detail.component.html',
  styleUrl: './commitment-detail.component.scss',
})
export class CommitmentDetailComponent implements OnInit {
  private api = inject(BudgetingService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private fb = inject(FormBuilder);
  private toast = inject(ToastService);

  commitment = signal<Commitment | null>(null);
  schedule = signal<CommitmentScheduleLine[]>([]);
  loading = signal(true);
  filter: 'upcoming' | 'all' | 'paid' = 'upcoming';
  payingId = signal<string | null>(null);

  reminderForm = this.fb.nonNullable.group({
    reminder_enabled: [true],
    reminder_days_before: [3, [Validators.required, Validators.min(0), Validators.max(90)]],
  });

  payForm = this.fb.nonNullable.group({
    payment_date: [new Date().toISOString().slice(0, 10), Validators.required],
  });

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) {
      this.router.navigate(['/budgeting/commitments']);
      return;
    }
    this.load(id);
  }

  load(id: string): void {
    this.loading.set(true);
    this.api.commitment(id).subscribe({
      next: (detail) => {
        this.commitment.set(detail);
        this.schedule.set(detail.schedule || []);
        this.reminderForm.setValue({
          reminder_enabled: detail.reminder_enabled ?? true,
          reminder_days_before: detail.reminder_days_before ?? 3,
        });
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not load commitment.');
        this.router.navigate(['/budgeting/commitments']);
      },
    });
  }

  filteredSchedule(): CommitmentScheduleLine[] {
    const rows = this.schedule();
    if (this.filter === 'paid') return rows.filter((r) => r.status === 'paid');
    if (this.filter === 'upcoming') return rows.filter((r) => r.status === 'outstanding');
    return rows;
  }

  paymentDate(line: CommitmentScheduleLine): string | null {
    return line.payment_date || line.paid_date || null;
  }

  startPay(line: CommitmentScheduleLine): void {
    this.payingId.set(line.id);
    this.payForm.setValue({ payment_date: new Date().toISOString().slice(0, 10) });
  }

  cancelPay(): void {
    this.payingId.set(null);
  }

  confirmPay(line: CommitmentScheduleLine): void {
    const c = this.commitment();
    if (!c || this.payForm.invalid) return;
    const paymentDate = this.payForm.getRawValue().payment_date;
    this.api.markCommitmentPaid(c.id, line.id, paymentDate).subscribe({
      next: () => {
        this.toast.success(`Payment #${line.sequence} recorded.`);
        this.payingId.set(null);
        this.load(c.id);
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not mark payment.'),
    });
  }

  undoPaid(line: CommitmentScheduleLine): void {
    const c = this.commitment();
    if (!c) return;
    this.api.unmarkCommitmentPaid(c.id, line.id).subscribe({
      next: () => {
        this.toast.success(`Payment #${line.sequence} set back to outstanding.`);
        this.load(c.id);
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not update payment.'),
    });
  }

  onDueDateChange(line: CommitmentScheduleLine, event: Event): void {
    const c = this.commitment();
    const value = (event.target as HTMLInputElement).value;
    if (!c || !value || value === line.due_date) return;
    this.api.updateCommitmentScheduleLine(c.id, line.id, { due_date: value }).subscribe({
      next: () => {
        this.toast.success('Due date updated.');
        this.load(c.id);
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not update due date.'),
    });
  }

  onPaymentDateChange(line: CommitmentScheduleLine, event: Event): void {
    const c = this.commitment();
    const value = (event.target as HTMLInputElement).value;
    if (!c || !value) return;
    this.api.updateCommitmentScheduleLine(c.id, line.id, { payment_date: value, status: 'paid' }).subscribe({
      next: () => {
        this.toast.success('Payment date updated.');
        this.load(c.id);
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not update payment date.'),
    });
  }

  saveReminders(): void {
    const c = this.commitment();
    if (!c || this.reminderForm.invalid) {
      this.toast.error('Check reminder settings.');
      return;
    }
    this.api.updateCommitment(c.id, this.reminderForm.getRawValue()).subscribe({
      next: () => {
        this.toast.success('Reminder settings saved.');
        this.load(c.id);
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not save reminders.'),
    });
  }

  regenerate(): void {
    const c = this.commitment();
    if (!c) return;
    if (!confirm('Rebuild the unpaid installments from the current terms? Paid installments and their transactions are kept.')) return;
    this.api.regenerateCommitmentSchedule(c.id).subscribe({
      next: () => {
        this.toast.success('Schedule rebuilt. Paid installments were kept.');
        this.load(c.id);
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not regenerate schedule.'),
    });
  }

  progressPct(): number {
    const c = this.commitment();
    const total = c?.payments_total || 0;
    if (!total) return 0;
    return Math.min(100, Math.round(((c?.payments_completed || 0) / total) * 100));
  }
}
