import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { SupportService } from '../../core/support.service';
import { SupportTicket } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { TICKET_CATEGORY_LABEL, shortDate } from '../admin/labels';

/** One support request: the conversation, the "is it fixed?" answer and a reply box. */
@Component({
  selector: 'app-support-ticket',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  template: `
    <p><a routerLink="/support">← Help &amp; support</a></p>
    @if (ticket(); as t) {
      <section class="hero">
        <div>
          <h1>{{ t.subject }}</h1>
          <p>{{ category[t.category] }} · request #{{ t.id }} · opened {{ date(t.created_at) }}</p>
        </div>
        @if (t.status === 'closed') { <span class="pill muted">Closed</span> }
      </section>

      @if (t.status === 'resolved') {
        <section class="panel confirm" [class.highlight]="!!suggested()">
          <h2>Support marked this as fixed. Is it working now?</h2>
          @if (askComment()) {
            <label class="form-grid">
              What is still not working? (optional)
              <textarea name="comment" [(ngModel)]="comment" rows="3"></textarea>
            </label>
          }
          <div class="toolbar">
            <button class="btn primary" type="button" [disabled]="busy()" (click)="confirm(true)">Yes, it's fixed</button>
            @if (askComment()) {
              <button class="btn ghost" type="button" [disabled]="busy()" (click)="confirm(false)">Send: still not fixed</button>
            } @else {
              <button class="btn ghost" type="button" [disabled]="busy()" (click)="askComment.set(true)">Still not fixed</button>
            }
          </div>
        </section>
      }

      @if (t.status === 'closed') {
        <section class="panel">
          <strong>This request is closed.</strong>
          {{ t.close_reason === 'auto' ? 'We closed it because we did not hear back from you.' : 'Thank you for confirming the fix.' }}
          Reply below if you still need help — it will reopen.
        </section>
      }

      <section class="thread">
        @for (m of t.messages ?? []; track m.id) {
          <article class="msg" [class.staff]="m.from_staff && !m.system" [class.system]="m.system">
            <header>
              <strong>{{ m.system ? 'Update' : m.from_staff ? 'Support' : 'You' }}</strong><span>{{ date(m.created_at) }}</span>
            </header>
            <p>{{ m.body }}</p>
          </article>
        }
      </section>

      @if (t.status !== 'resolved') {
        <form class="panel reply" (ngSubmit)="send()">
          <label for="reply">
            <strong>{{ t.status === 'closed' ? 'Still need help? Reply to reopen this request' : 'Reply' }}</strong>
          </label>
          <textarea id="reply" name="reply" [(ngModel)]="reply"></textarea>
          <div class="toolbar">
            <button class="btn primary" type="submit" [disabled]="busy() || !reply.trim()">
              {{ busy() ? 'Sending…' : 'Send' }}
            </button>
          </div>
        </form>
      }
    } @else {
      <p class="muted">Loading…</p>
    }
  `,
  styleUrl: '../admin/admin-shared.scss',
  styles: [
    `.confirm { border-left: 4px solid var(--accent); }
     .confirm.highlight { box-shadow: 0 0 0 3px rgba(26, 92, 94, 0.15); }
     .confirm h2 { margin-bottom: 0.6rem !important; }
     .msg.system { background: transparent; border-style: dashed; font-size: 0.88rem; margin: 0 auto; }`,
  ],
})
export class SupportTicketComponent implements OnInit {
  private support = inject(SupportService);
  private toast = inject(ToastService);
  private route = inject(ActivatedRoute);

  readonly category = TICKET_CATEGORY_LABEL;
  ticket = signal<SupportTicket | null>(null);
  busy = signal(false);
  askComment = signal(false);
  /** From the email buttons (?confirm=yes|no): highlight the question; the user still clicks to answer. */
  suggested = signal<'yes' | 'no' | null>(null);
  reply = '';
  comment = '';

  ngOnInit(): void {
    const confirm = this.route.snapshot.queryParamMap.get('confirm');
    if (confirm === 'yes' || confirm === 'no') {
      this.suggested.set(confirm);
      this.askComment.set(confirm === 'no');
    }
    // The route is reused when a notification links to another request: follow the param.
    this.route.paramMap.subscribe((pm) => {
      const id = pm.get('id') ?? '';
      this.support.ticket(id).subscribe({
        next: (t) => this.ticket.set(t),
        error: (err) => this.toast.fromHttpError(err, 'Could not load this request.'),
      });
    });
  }

  confirm(fixed: boolean): void {
    const t = this.ticket();
    if (!t) return;
    this.busy.set(true);
    this.support.confirm(t.id, fixed, this.comment.trim()).subscribe({
      next: (updated) => {
        this.ticket.set(updated);
        this.busy.set(false);
        this.askComment.set(false);
        this.comment = '';
        this.toast.success(fixed ? 'Thank you! The request is closed.' : 'Sent back to support.');
      },
      error: (err) => {
        this.busy.set(false);
        this.toast.fromHttpError(err, 'Could not send your answer.');
      },
    });
  }

  send(): void {
    const t = this.ticket();
    const body = this.reply.trim();
    if (!t || !body) return;
    this.busy.set(true);
    this.support.reply(t.id, body).subscribe({
      next: (updated) => {
        this.ticket.set(updated);
        this.reply = '';
        this.busy.set(false);
      },
      error: (err) => {
        this.busy.set(false);
        this.toast.fromHttpError(err, 'Could not send your reply.');
      },
    });
  }

  date(iso: string | null): string {
    return shortDate(iso);
  }
}
