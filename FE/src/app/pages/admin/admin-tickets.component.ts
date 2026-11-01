import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AdminService } from '../../core/admin.service';
import { AdminOverview, Paged, SupportTicket } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { TICKET_CATEGORY_LABEL, TICKET_STATUS_LABEL, shortDate, statusClass } from './labels';

type View = 'mine' | 'pool' | 'all';

@Component({
  selector: 'app-admin-tickets',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  template: `
    <section class="hero">
      <div>
        <h1>Support tickets</h1>
        <p>New tickets are assigned automatically (see <a routerLink="/admin/support-settings">Support settings</a>).
          The assigned admin answers or marks the ticket resolved; the user confirms to close it.</p>
      </div>
    </section>

    <nav class="tabs">
      <button type="button" [class.active]="view === 'mine'" (click)="setView('mine')">
        My tickets @if (counts(); as c) { <span class="count">{{ c.my_open_tickets }}</span> }
      </button>
      <button type="button" [class.active]="view === 'pool'" (click)="setView('pool')">
        Pool @if (counts(); as c) { <span class="count" [class.alert]="c.tickets_pool">{{ c.tickets_pool }}</span> }
      </button>
      <button type="button" [class.active]="view === 'all'" (click)="setView('all')">All tickets</button>
    </nav>

    <form class="filters" (ngSubmit)="search(1)">
      <label>Search <input name="q" [(ngModel)]="q" placeholder="subject, username or email" /></label>
      @if (view !== 'pool') {
        <label>
          Status
          <select name="status" [(ngModel)]="status" (ngModelChange)="search(1)">
            <option value="">Any</option>
            <option value="open">Open</option>
            <option value="waiting_user">Waiting for user</option>
            <option value="resolved">Resolved, awaiting confirmation</option>
            <option value="closed">Closed</option>
          </select>
        </label>
      }
      <button class="btn primary" type="submit">Search</button>
    </form>

    <div class="panel table-wrap">
      <table>
        <thead><tr><th>Ticket</th><th>User</th><th>Status</th><th>Assigned</th><th>Updated</th><th></th></tr></thead>
        <tbody>
          @for (t of page()?.results ?? []; track t.id) {
            <tr class="clickable" (click)="open(t)">
              <td>
                <strong>#{{ t.id }} {{ t.subject }}</strong>
                @if (t.priority === 'high') { <span class="pill high">high</span> }
                <small>{{ category[t.category] }}</small>
              </td>
              <td>{{ t.user?.username }}<small>{{ t.user?.email }}</small></td>
              <td><span [class]="'pill ' + statusClass(t.status)">{{ statusLabel[t.status] }}</span></td>
              <td>
                @if (t.assigned_to) { {{ t.assigned_to.username }} } @else { <span class="pill warn">Unassigned</span> }
              </td>
              <td>{{ date(t.updated_at) }}</td>
              <td>
                @if (!t.assigned_to && t.status !== 'closed') {
                  <button type="button" class="btn primary" (click)="claim(t, $event)">Take it</button>
                }
              </td>
            </tr>
          } @empty {
            <tr><td colspan="6" class="empty">{{ loading() ? 'Loading…' : emptyText() }}</td></tr>
          }
        </tbody>
      </table>
      @if (page(); as p) {
        <div class="pager">
          <span>{{ p.count }} ticket(s)</span>
          <button class="btn ghost" type="button" [disabled]="p.page <= 1" (click)="search(p.page - 1)">Previous</button>
          <span>Page {{ p.page }}</span>
          <button class="btn ghost" type="button" [disabled]="p.page * p.page_size >= p.count" (click)="search(p.page + 1)">
            Next
          </button>
        </div>
      }
    </div>
  `,
  styleUrl: './admin-shared.scss',
  styles: [
    `.tabs { display: flex; gap: 0.25rem; margin-bottom: 0.75rem; border-bottom: 1px solid var(--line); }
     .tabs button { border: 0; background: none; padding: 0.6rem 0.9rem; font: inherit; cursor: pointer; color: var(--muted);
       border-bottom: 2px solid transparent; }
     .tabs button.active { color: var(--ink); font-weight: 600; border-bottom-color: var(--accent); }
     .count { margin-left: 0.3rem; font-size: 0.78rem; background: #eef2f1; border-radius: 999px; padding: 0.05rem 0.45rem; }
     .count.alert { background: #fde8e4; color: #8a2f1d; }`,
  ],
})
export class AdminTicketsComponent implements OnInit {
  private admin = inject(AdminService);
  private toast = inject(ToastService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);

  readonly statusLabel = TICKET_STATUS_LABEL;
  readonly category = TICKET_CATEGORY_LABEL;
  readonly statusClass = statusClass;
  view: View = 'mine';
  q = '';
  status = '';
  page = signal<Paged<SupportTicket> | null>(null);
  counts = signal<AdminOverview | null>(null);
  loading = signal(false);

  ngOnInit(): void {
    const qp = this.route.snapshot.queryParamMap;
    const view = qp.get('view');
    this.view = view === 'pool' || view === 'all' ? view : 'mine';
    this.q = qp.get('q') ?? '';
    this.status = qp.get('status') ?? '';
    this.search(1);
  }

  setView(view: View): void {
    this.view = view;
    this.status = '';
    this.search(1);
  }

  search(page: number): void {
    this.loading.set(true);
    this.router.navigate([], {
      queryParams: { view: this.view, q: this.q || null, status: this.status || null },
      replaceUrl: true,
    });
    this.admin.overview().subscribe({ next: (c) => this.counts.set(c), error: () => undefined });
    this.admin.tickets({ view: this.view, q: this.q, status: this.view === 'pool' ? '' : this.status, page }).subscribe({
      next: (p) => {
        this.page.set(p);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not load tickets.');
      },
    });
  }

  claim(t: SupportTicket, event: Event): void {
    event.stopPropagation();
    this.admin.claimTicket(t.id).subscribe({
      next: () => {
        this.toast.success(`Ticket #${t.id} is now yours.`);
        this.router.navigate(['/admin/tickets', t.id]);
      },
      error: (err) => {
        this.toast.fromHttpError(err, 'Could not take this ticket.');
        this.search(1);
      },
    });
  }

  emptyText(): string {
    if (this.view === 'pool') return 'The pool is empty: every ticket has an admin.';
    if (this.view === 'mine') return 'No tickets assigned to you.';
    return 'No tickets.';
  }

  open(t: SupportTicket): void {
    this.router.navigate(['/admin/tickets', t.id]);
  }

  date(iso: string | null): string {
    return shortDate(iso);
  }
}
