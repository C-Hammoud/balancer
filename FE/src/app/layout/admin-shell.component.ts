import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs/operators';
import { AdminService } from '../core/admin.service';
import { AuthService } from '../core/auth.service';

interface AdminNavItem {
  label: string;
  path: string;
  exact?: boolean;
  /** Key of the overview count shown as a badge. */
  badge?: 'tickets';
}

/** Layout of the admin console: its own side menu instead of the finance app's navigation. */
@Component({
  selector: 'app-admin-shell',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './admin-shell.component.html',
  styleUrl: './admin-shell.component.scss',
})
export class AdminShellComponent implements OnInit {
  private auth = inject(AuthService);
  private admin = inject(AdminService);
  private router = inject(Router);
  private destroyRef = inject(DestroyRef);

  user = this.auth.user;
  /** Tickets waiting for this admin or for anyone (the pool). */
  ticketBadge = signal(0);

  readonly items: AdminNavItem[] = [
    { label: 'Overview', path: '/admin', exact: true },
    { label: 'Users', path: '/admin/users' },
    { label: 'Support tickets', path: '/admin/tickets', badge: 'tickets' },
    { label: 'Support settings', path: '/admin/support-settings' },
    { label: 'Audit log', path: '/admin/audit-log' },
  ];

  ngOnInit(): void {
    this.loadCounts();
    // Keep the badge current as the admin works through tickets.
    this.router.events
      .pipe(
        filter((e) => e instanceof NavigationEnd),
        takeUntilDestroyed(this.destroyRef)
      )
      .subscribe(() => this.loadCounts());
  }

  private loadCounts(): void {
    this.admin.overview().subscribe({
      next: (o) => this.ticketBadge.set((o.my_open_tickets || 0) + (o.tickets_pool || 0)),
      error: () => this.ticketBadge.set(0),
    });
  }

  logout(): void {
    this.auth.logout();
  }
}
