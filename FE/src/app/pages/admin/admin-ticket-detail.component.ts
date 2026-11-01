import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { AdminService } from '../../core/admin.service';
import { AuthService } from '../../core/auth.service';
import { SupportTicket, UserRef } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { CLOSE_REASON_LABEL, TICKET_CATEGORY_LABEL, TICKET_STATUS_LABEL, shortDate, statusClass } from './labels';

@Component({
  selector: 'app-admin-ticket-detail',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  template: `
    <p><a routerLink="/admin/tickets">← Tickets</a></p>
    @if (ticket(); as t) {
      <section class="hero">
        <div>
          <h1>#{{ t.id }} {{ t.subject }}</h1>
          <p>
            {{ category[t.category] }} · from
            @if (t.user) { <a [routerLink]="['/admin/users', t.user.id]">{{ t.user.username }}</a> ({{ t.user.email }}) }
          </p>
        </div>
        <span [class]="'pill ' + statusClass(t.status)">{{ statusLabel[t.status] }}</span>
      </section>

      <section class="panel">
        <dl class="facts">
          <dt>Assigned to</dt>
          <dd>
            @if (t.assigned_to) { {{ t.assigned_to.username }} <small class="muted">since {{ date(t.assigned_at) }}</small> }
            @else { <span class="pill warn">Unassigned (pool)</span> }
          </dd>
          <dt>Opened</dt><dd>{{ date(t.created_at) }}</dd>
          @if (t.resolved_at) { <dt>Marked resolved</dt><dd>{{ date(t.resolved_at) }}</dd> }
          @if (t.closed_at) { <dt>Closed</dt><dd>{{ date(t.closed_at) }} — {{ closeReason[t.close_reason] || '' }}</dd> }
        </dl>
        <div class="filters" style="margin: 0.75rem 0 0">
          @if (!t.assigned_to && t.status !== 'closed') {
            <button type="button" class="btn primary" (click)="claim()">Take it</button>
          }
          @if (canAct()) {
            <label>
              Priority
              <select [ngModel]="t.priority" (ngModelChange)="update({ priority: $event })">
                <option value="normal">Normal</option>
                <option value="high">High</option>
              </select>
            </label>
          }
          @if (isSuperuser()) {
            <label>
              Reassign to
              <select [ngModel]="t.assigned_to?.id ?? ''" (ngModelChange)="update({ assigned_to: $event === '' ? null : +$event })">
                <option value="">Nobody (pool)</option>
                @for (s of staff(); track s.id) {
                  <option [value]="s.id">{{ s.username }}</option>
                }
              </select>
            </label>
          }
        </div>
      </section>

      <section class="thread">
        @for (m of t.messages ?? []; track m.id) {
          <article class="msg" [class.staff]="m.from_staff && !m.system" [class.system]="m.system">
            <header>
              <strong>{{ m.system ? 'System' : m.from_staff ? m.author + ' (support)' : m.author }}</strong>
              <span>{{ date(m.created_at) }}</span>
            </header>
            <p>{{ m.body }}</p>
          </article>
        }
      </section>

      @if (t.status === 'closed') {
        <p class="panel muted">This ticket is closed. If the user replies, it reopens and comes back to the assigned admin.</p>
      } @else if (canAct()) {
        <form class="panel reply" (ngSubmit)="send(false)">
          <label for="reply"><strong>Message to the user</strong> <small class="muted">(emailed and shown in their app)</small></label>
          <textarea id="reply" name="reply" [(ngModel)]="reply"
                    placeholder="Ask a question, or explain what you fixed and mark it resolved"></textarea>
          <div class="toolbar">
            <button class="btn ghost" type="submit" [disabled]="sending() || !reply.trim()">Send reply</button>
            <button class="btn primary" type="button" [disabled]="sending() || !reply.trim()" (click)="send(true)">
              Send &amp; mark resolved
            </button>
          </div>
          <small class="muted">"Mark resolved" asks the user to confirm the fix. When they confirm, the ticket closes and you
            both get a confirmation email.</small>
        </form>
      } @else {
        <p class="panel muted">
          {{ t.assigned_to ? 'Assigned to ' + t.assigned_to.username + ' — read only.' : 'Take this ticket to answer it.' }}
        </p>
      }
    } @else {
      <p class="muted">Loading…</p>
    }
  `,
  styleUrl: './admin-shared.scss',
  styles: [`.msg.system { background: transparent; border-style: dashed; font-size: 0.88rem; margin: 0 auto; }`],
})
export class AdminTicketDetailComponent implements OnInit {
  private admin = inject(AdminService);
  private auth = inject(AuthService);
  private toast = inject(ToastService);
  private route = inject(ActivatedRoute);

  readonly statusLabel = TICKET_STATUS_LABEL;
  readonly category = TICKET_CATEGORY_LABEL;
  readonly closeReason = CLOSE_REASON_LABEL;
  readonly statusClass = statusClass;
  ticket = signal<SupportTicket | null>(null);
  staff = signal<UserRef[]>([]);
  sending = signal(false);
  reply = '';
  id = '';

  isSuperuser = computed(() => !!this.auth.user()?.is_superuser);
  /** Same rule as the API: the assigned admin or a superuser. */
  canAct = computed(() => {
    const t = this.ticket();
    const me = this.auth.user();
    return !!t && !!me && (me.is_superuser || t.assigned_to?.id === me.id);
  });

  ngOnInit(): void {
    this.id = this.route.snapshot.paramMap.get('id') ?? '';
    this.load();
    this.admin.staff().subscribe({ next: (s) => this.staff.set(s), error: () => undefined });
  }

  private load(): void {
    this.admin.ticket(this.id).subscribe({
      next: (t) => this.ticket.set(t),
      error: (err) => this.toast.fromHttpError(err, 'Could not load this ticket.'),
    });
  }

  claim(): void {
    this.admin.claimTicket(this.id).subscribe({
      next: (t) => {
        this.ticket.set(t);
        this.toast.success('This ticket is now yours.');
      },
      error: (err) => {
        this.toast.fromHttpError(err, 'Could not take this ticket.');
        this.load();
      },
    });
  }

  update(change: Partial<{ priority: string; assigned_to: number | null }>): void {
    this.admin.updateTicket(this.id, change).subscribe({
      next: (t) => {
        this.ticket.set(t);
        this.toast.success('Ticket updated.');
      },
      error: (err) => {
        this.toast.fromHttpError(err, 'Could not update the ticket.');
        this.load();
      },
    });
  }

  send(resolve: boolean): void {
    const body = this.reply.trim();
    if (!body) return;
    this.sending.set(true);
    const req = resolve ? this.admin.resolveTicket(this.id, body) : this.admin.replyTicket(this.id, body);
    req.subscribe({
      next: (t) => {
        this.ticket.set(t);
        this.reply = '';
        this.sending.set(false);
        this.toast.success(resolve ? 'Marked resolved. The user is asked to confirm.' : 'Reply sent to the user.');
      },
      error: (err) => {
        this.sending.set(false);
        this.toast.fromHttpError(err, 'Could not send.');
      },
    });
  }

  date(iso: string | null | undefined): string {
    return shortDate(iso);
  }
}
