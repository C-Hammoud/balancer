import { Component, HostListener, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs/operators';
import { AuthService } from '../core/auth.service';
import { BudgetingService } from '../core/budgeting.service';
import { FinanceDataRefreshService } from '../core/finance-data-refresh.service';
import { CommitmentDuePromptComponent } from '../shared/commitment-due-prompt/commitment-due-prompt.component';
import { NotificationBellComponent } from '../shared/notification-bell/notification-bell.component';

interface NavItem {
  label: string;
  path: string;
  exact?: boolean;
  badge?: boolean;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [
    CommonModule,
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    CommitmentDuePromptComponent,
    NotificationBellComponent,
  ],
  templateUrl: './shell.component.html',
  styleUrl: './shell.component.scss',
})
export class ShellComponent implements OnInit, OnDestroy {
  private auth = inject(AuthService);
  private budgeting = inject(BudgetingService);
  private refresh = inject(FinanceDataRefreshService);
  private router = inject(Router);

  user = this.auth.user;
  alertCount = signal(0);
  menuOpen = signal(false);
  openGroup = signal<string | null>(null);

  primary: NavItem[] = [
    { label: 'Dashboard', path: '/dashboard', exact: true },
    { label: 'Transactions', path: '/budgeting/transactions' },
  ];

  groups: NavGroup[] = [
    {
      label: 'Budget',
      items: [
        { label: 'Overview', path: '/budgeting', exact: true },
        { label: 'Plan', path: '/budgeting/plan' },
        { label: 'Utilization', path: '/budgeting/utilization' },
        { label: 'Budgets', path: '/budgeting/budgets' },
        { label: 'Monthly forecasts', path: '/budgeting/monthly-forecasts' },
        { label: 'Savings', path: '/budgeting/savings' },
        { label: 'Commitments', path: '/budgeting/commitments' },
        { label: 'Net worth', path: '/budgeting/financial-standing' },
        { label: 'Risk', path: '/budgeting/risk' },
      ],
    },
    {
      label: 'Setup',
      items: [
        { label: 'Categories', path: '/budgeting/config/type-maps' },
        { label: 'Accounts', path: '/budgeting/config/accounts' },
        { label: 'Planned items', path: '/budgeting/config/planned-items' },
        { label: 'Merchants', path: '/budgeting/config/merchant-links' },
        { label: 'Thresholds', path: '/budgeting/config/thresholds' },
      ],
    },
  ];

  /** Shown only to support staff (the admin API refuses everyone else anyway). */
  private readonly adminGroup: NavGroup = {
    label: 'Admin',
    items: [
      { label: 'Overview', path: '/admin', exact: true },
      { label: 'Users', path: '/admin/users' },
      { label: 'Support tickets', path: '/admin/tickets' },
      { label: 'Support settings', path: '/admin/support-settings' },
      { label: 'Audit log', path: '/admin/audit-log' },
    ],
  };

  isStaff = computed(() => !!(this.user()?.is_staff || this.user()?.is_superuser));
  navGroups = computed(() => (this.isStaff() ? [...this.groups, this.adminGroup] : this.groups));

  ngOnInit(): void {
    // Always refresh the profile: roles (admin) and settings may have changed since sign-in.
    this.auth.loadMe().subscribe({ error: () => undefined });
    this.budgeting.alertCount().subscribe({
      next: (r) => this.alertCount.set(r.count),
      error: () => this.alertCount.set(0),
    });
    this.refresh.changed$.subscribe(() => this.reloadAlertCount());
    this.router.events.pipe(filter((e) => e instanceof NavigationEnd)).subscribe(() => {
      this.menuOpen.set(false);
      this.openGroup.set(null);
      this.syncBodyScrollLock();
    });
  }

  ngOnDestroy(): void {
    document.body.classList.remove('drawer-open');
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.menuOpen.set(false);
    this.openGroup.set(null);
    this.syncBodyScrollLock();
  }

  toggleMenu(): void {
    this.menuOpen.update((v) => !v);
    this.syncBodyScrollLock();
  }

  closeMenu(): void {
    this.menuOpen.set(false);
    this.syncBodyScrollLock();
  }

  private syncBodyScrollLock(): void {
    document.body.classList.toggle('drawer-open', this.menuOpen());
  }

  toggleGroup(label: string): void {
    this.openGroup.update((g) => (g === label ? null : label));
  }

  reloadAlertCount(): void {
    this.budgeting.alertCount().subscribe({
      next: (r) => this.alertCount.set(r.count),
      error: () => this.alertCount.set(0),
    });
  }

  logout(): void {
    this.auth.logout();
  }
}
