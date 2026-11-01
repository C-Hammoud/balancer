import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { SupportService } from '../../core/support.service';
import { SupportTicket, TicketCategory } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { TICKET_CATEGORY_LABEL, TICKET_STATUS_LABEL, shortDate, statusClass } from '../admin/labels';

/** Help & support: report a problem and see your requests. */
@Component({
  selector: 'app-support',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink],
  template: `
    <section class="hero">
      <div>
        <h1>Help &amp; support</h1>
        <p>Tell us what went wrong. We reply here and by email.</p>
      </div>
    </section>

    <form class="panel form-grid" [formGroup]="form" (ngSubmit)="submit()">
      <h2>Report a problem</h2>
      <label>
        What is it about?
        <select formControlName="category">
          @for (c of categories; track c.value) {
            <option [value]="c.value">{{ c.label }}</option>
          }
        </select>
      </label>
      <label>Title <input formControlName="subject" maxlength="200" placeholder="e.g. Cannot import my bank statement" /></label>
      <label>
        Describe the problem
        <textarea formControlName="message" rows="5" placeholder="What did you do, what did you expect, and what happened?"></textarea>
      </label>
      <div class="toolbar">
        <button class="btn primary" type="submit" [disabled]="sending()">{{ sending() ? 'Sending…' : 'Send to support' }}</button>
      </div>
    </form>

    <section class="panel">
      <h2>Your requests</h2>
      @for (t of tickets(); track t.id) {
        <p>
          <a [routerLink]="['/support', t.id]">#{{ t.id }} {{ t.subject }}</a>
          <span [class]="'pill ' + statusClass(t.status)">{{ userStatus(t.status) }}</span>
          <small class="muted">updated {{ date(t.updated_at) }}</small>
        </p>
      } @empty {
        <p class="empty">You have not contacted support yet.</p>
      }
    </section>
  `,
  styleUrl: '../admin/admin-shared.scss',
})
export class SupportComponent implements OnInit {
  private support = inject(SupportService);
  private toast = inject(ToastService);
  private router = inject(Router);
  private fb = inject(FormBuilder);

  readonly categories = Object.entries(TICKET_CATEGORY_LABEL).map(([value, label]) => ({ value, label }));
  readonly statusClass = statusClass;
  tickets = signal<SupportTicket[]>([]);
  sending = signal(false);

  form = this.fb.nonNullable.group({
    category: ['account' as TicketCategory],
    subject: ['', Validators.required],
    message: ['', Validators.required],
  });

  ngOnInit(): void {
    this.support.tickets().subscribe({ next: (t) => this.tickets.set(t), error: () => this.tickets.set([]) });
  }

  submit(): void {
    if (this.form.invalid) {
      this.toast.error('Add a title and describe the problem.');
      return;
    }
    this.sending.set(true);
    this.support.create(this.form.getRawValue()).subscribe({
      next: (t) => {
        this.sending.set(false);
        this.toast.success('Sent. Support will reply here and by email.');
        this.router.navigate(['/support', t.id]);
      },
      error: (err) => {
        this.sending.set(false);
        this.toast.fromHttpError(err, 'Could not send your request.');
      },
    });
  }

  /** Wording from the user's side. */
  userStatus(status: string): string {
    if (status === 'waiting_user') return 'Support replied';
    if (status === 'resolved') return 'Fixed? Please confirm';
    if (status === 'open') return 'Waiting for support';
    return TICKET_STATUS_LABEL[status];
  }

  date(iso: string): string {
    return shortDate(iso);
  }
}
