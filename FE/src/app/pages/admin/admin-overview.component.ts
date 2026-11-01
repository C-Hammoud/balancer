import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { AdminService } from '../../core/admin.service';
import { AdminOverview } from '../../core/models';
import { ToastService } from '../../core/toast.service';

@Component({
  selector: 'app-admin-overview',
  standalone: true,
  imports: [CommonModule, RouterLink],
  template: `
    <section class="hero">
      <div>
        <h1>Admin</h1>
        <p>Users, support tickets and account problems. Every view and action is recorded in the audit log.</p>
      </div>
    </section>
    @if (data(); as d) {
      <div class="tiles">
        <a class="tile" routerLink="/admin/users"><span>Users</span><strong>{{ d.users_total }}</strong></a>
        <a class="tile" routerLink="/admin/users"><span>New in the last 7 days</span><strong>{{ d.users_new_7d }}</strong></a>
        <a class="tile" [class.alert]="d.my_open_tickets" routerLink="/admin/tickets" [queryParams]="{ view: 'mine' }">
          <span>My open tickets</span><strong>{{ d.my_open_tickets }}</strong>
        </a>
        <a class="tile" [class.alert]="d.tickets_pool" routerLink="/admin/tickets" [queryParams]="{ view: 'pool' }">
          <span>Tickets in the pool</span><strong>{{ d.tickets_pool }}</strong>
        </a>
        <a class="tile" routerLink="/admin/tickets" [queryParams]="{ view: 'all', status: 'open' }">
          <span>Open tickets (all admins)</span><strong>{{ d.tickets_open }}</strong>
        </a>
        <a class="tile" routerLink="/admin/tickets" [queryParams]="{ view: 'all', status: 'resolved' }">
          <span>Resolved, awaiting user</span><strong>{{ d.tickets_resolved }}</strong>
        </a>
        <a class="tile" [class.alert]="d.email_unverified" routerLink="/admin/users" [queryParams]="{ flag: 'email_unverified' }">
          <span>Unverified after 24 h</span><strong>{{ d.email_unverified }}</strong>
        </a>
        <a class="tile" routerLink="/admin/users" [queryParams]="{ flag: 'setup_stuck' }">
          <span>Setup not finished</span><strong>{{ d.setup_stuck }}</strong>
        </a>
        <a class="tile" [class.alert]="d.emails_failed_7d" routerLink="/admin/users" [queryParams]="{ flag: 'email_failed' }">
          <span>Failed emails (7 days)</span><strong>{{ d.emails_failed_7d }}</strong>
        </a>
        <a class="tile" routerLink="/admin/users" [queryParams]="{ status: 'inactive' }">
          <span>Deactivated</span><strong>{{ d.deactivated }}</strong>
        </a>
      </div>
    } @else {
      <p class="muted">Loading…</p>
    }
  `,
  styleUrl: './admin-shared.scss',
})
export class AdminOverviewComponent implements OnInit {
  private admin = inject(AdminService);
  private toast = inject(ToastService);
  data = signal<AdminOverview | null>(null);

  ngOnInit(): void {
    this.admin.overview().subscribe({
      next: (d) => this.data.set(d),
      error: (err) => this.toast.fromHttpError(err, 'Could not load the admin overview.'),
    });
  }
}
