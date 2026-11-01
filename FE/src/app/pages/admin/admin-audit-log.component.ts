import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { AdminService } from '../../core/admin.service';
import { AuditLogRow, Paged } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { AUDIT_ACTION_LABEL, shortDate } from './labels';

@Component({
  selector: 'app-admin-audit-log',
  standalone: true,
  imports: [CommonModule, RouterLink],
  template: `
    <section class="hero">
      <div>
        <h1>Audit log</h1>
        <p>
          Every time support staff open a user or act on an account or ticket.
          @if (userId) { Showing one user. <a routerLink="/admin/audit-log">Show all</a> }
        </p>
      </div>
    </section>
    <div class="panel table-wrap">
      <table>
        <thead><tr><th>When</th><th>Staff member</th><th>Action</th><th>User</th><th>Details</th></tr></thead>
        <tbody>
          @for (r of page()?.results ?? []; track r.id) {
            <tr>
              <td>{{ date(r.created_at) }}</td>
              <td>{{ r.actor?.username || 'Automatic' }}</td>
              <td>{{ label(r.action) }}</td>
              <td>
                @if (r.target_user) {
                  <a [routerLink]="['/admin/users', r.target_user.id]">{{ r.target_user.username }}</a>
                } @else { — }
              </td>
              <td>
                @if (r.ticket_id) { <a [routerLink]="['/admin/tickets', r.ticket_id]">Ticket #{{ r.ticket_id }}</a> }
                <small>{{ details(r) }}</small>
              </td>
            </tr>
          } @empty {
            <tr><td colspan="5" class="empty">Nothing recorded yet.</td></tr>
          }
        </tbody>
      </table>
      @if (page(); as p) {
        <div class="pager">
          <span>{{ p.count }} entries</span>
          <button class="btn ghost" type="button" [disabled]="p.page <= 1" (click)="load(p.page - 1)">Previous</button>
          <span>Page {{ p.page }}</span>
          <button class="btn ghost" type="button" [disabled]="p.page * p.page_size >= p.count" (click)="load(p.page + 1)">
            Next
          </button>
        </div>
      }
    </div>
  `,
  styleUrl: './admin-shared.scss',
})
export class AdminAuditLogComponent implements OnInit {
  private admin = inject(AdminService);
  private toast = inject(ToastService);
  private route = inject(ActivatedRoute);

  page = signal<Paged<AuditLogRow> | null>(null);
  userId = '';

  ngOnInit(): void {
    this.route.queryParamMap.subscribe((qp) => {
      this.userId = qp.get('user') ?? '';
      this.load(1);
    });
  }

  load(page: number): void {
    this.admin.auditLog({ user: this.userId, page }).subscribe({
      next: (p) => this.page.set(p),
      error: (err) => this.toast.fromHttpError(err, 'Could not load the audit log.'),
    });
  }

  label(action: string): string {
    return AUDIT_ACTION_LABEL[action] ?? action;
  }

  details(r: AuditLogRow): string {
    return Object.entries(r.detail || {})
      .map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v}`)
      .join(' · ');
  }

  date(iso: string): string {
    return shortDate(iso);
  }
}
