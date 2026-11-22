import { Component, HostListener, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs/operators';
import { AuthService } from '../core/auth.service';
import { BudgetingService } from '../core/budgeting.service';
import { FinanceDataRefreshService } from '../core/finance-data-refresh.service';
import { PwaInstallService } from '../core/pwa-install.service';
import { CommitmentDuePromptComponent } from '../shared/commitment-due-prompt/commitment-due-prompt.component';
import { NotificationBellComponent } from '../shared/notification-bell/notification-bell.component';
import { QuickAddDialogComponent } from '../shared/quick-add/quick-add-dialog.component';
import { QuickAddService } from '../shared/quick-add/quick-add.service';

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
    QuickAddDialogComponent,
  ],
  templateUrl: './shell.component.html',
  styleUrl: './shell.component.scss',
})
export class ShellComponent implements OnInit, OnDestroy {
  private auth = inject(AuthService);
  private budgeting = inject(BudgetingService);
  private refresh = inject(FinanceDataRefreshService);
  private router = inject(Router);
  private pwa = inject(PwaInstallService);
  /** The + button opens the quick-add screen on every page. */
  readonly quickAdd = inject(QuickAddService);

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
        { label: 'Monthly budget', path: '/budgeting/monthly-budget' },
        { label: 'Utilization', path: '/budgeting/utilization' },
        { label: 'Projects', path: '/budgeting/projects' },
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

  /** Support staff get an "Admin" link to the admin console (the admin API refuses everyone else anyway). */
  isStaff = computed(() => !!(this.user()?.is_staff || this.user()?.is_superuser));
  navGroups = computed(() => this.groups);

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
    this.showIosInstall.set(false);
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

  // ---- Install as an app (PWA) ----

  /** Android / desktop Chrome & Edge offer an install prompt; iPhone gets instructions. */
  showInstall = computed(() => this.pwa.canInstall() || this.pwa.iosInstructions());
  showIosInstall = signal(false);

  installApp(): void {
    this.closeMenu();
    if (this.pwa.canInstall()) {
      void this.pwa.install();
    } else if (this.pwa.iosInstructions()) {
      this.showIosInstall.set(true);
    }
  }
}
