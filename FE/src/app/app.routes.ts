import { Routes } from '@angular/router';
import { authGuard, guestGuard, staffGuard } from './core/auth.guard';
import { ShellComponent } from './layout/shell.component';
import { BudgetingShellComponent } from './pages/budgeting/budgeting-shell.component';

export const routes: Routes = [
  {
    path: 'login',
    canActivate: [guestGuard],
    loadComponent: () => import('./pages/login/login.component').then((m) => m.LoginComponent),
  },
  {
    path: 'register',
    canActivate: [guestGuard],
    loadComponent: () => import('./pages/register/register.component').then((m) => m.RegisterComponent),
  },
  {
    path: 'forgot-password',
    canActivate: [guestGuard],
    loadComponent: () =>
      import('./pages/forgot-password/forgot-password.component').then((m) => m.ForgotPasswordComponent),
  },
  {
    path: 'reset-password',
    canActivate: [guestGuard],
    loadComponent: () =>
      import('./pages/reset-password/reset-password.component').then((m) => m.ResetPasswordComponent),
  },
  {
    path: 'verify-email',
    loadComponent: () =>
      import('./pages/verify-email/verify-email.component').then((m) => m.VerifyEmailComponent),
  },
  {
    path: 'check-email',
    loadComponent: () =>
      import('./pages/check-email/check-email.component').then((m) => m.CheckEmailComponent),
  },
  {
    path: '',
    component: ShellComponent,
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      {
        path: 'dashboard',
        loadComponent: () =>
          import('./pages/dashboard/dashboard.component').then((m) => m.DashboardComponent),
      },
      {
        path: 'profile',
        loadComponent: () =>
          import('./pages/profile/profile.component').then((m) => m.ProfileComponent),
      },
      {
        path: 'expenses',
        redirectTo: 'budgeting/transactions',
        pathMatch: 'full',
      },
      {
        path: 'expenses/add',
        redirectTo: 'budgeting/transactions',
        pathMatch: 'full',
      },
      {
        path: 'budgeting',
        component: BudgetingShellComponent,
        children: [
          {
            path: '',
            loadComponent: () =>
              import('./pages/budgeting/budgeting.component').then((m) => m.BudgetingComponent),
          },
          {
            path: 'utilization',
            loadComponent: () =>
              import('./pages/budgeting/utilization/utilization.component').then(
                (m) => m.UtilizationComponent
              ),
          },
          {
            path: 'transactions/assign',
            loadComponent: () =>
              import('./pages/budgeting/transactions/assign-merchants.component').then(
                (m) => m.AssignMerchantsComponent
              ),
          },
          {
            path: 'transactions',
            loadComponent: () =>
              import('./pages/budgeting/transactions/transactions.component').then(
                (m) => m.BudgetTransactionsComponent
              ),
          },
          {
            path: 'budgets',
            loadComponent: () =>
              import('./pages/budgeting/budgets/budgets.component').then((m) => m.BudgetsComponent),
          },
          {
            path: 'budgets/:id',
            loadComponent: () =>
              import('./pages/budgeting/budgets/budget-detail.component').then((m) => m.BudgetDetailComponent),
          },
          {
            path: 'monthly-forecasts',
            loadComponent: () =>
              import('./pages/budgeting/monthly-forecasts/monthly-forecasts.component').then(
                (m) => m.MonthlyForecastsComponent
              ),
          },
          {
            path: 'savings',
            loadComponent: () =>
              import('./pages/budgeting/savings/savings.component').then((m) => m.SavingsComponent),
          },
          {
            path: 'commitments',
            loadComponent: () =>
              import('./pages/budgeting/commitments/commitments.component').then(
                (m) => m.CommitmentsComponent
              ),
          },
          {
            path: 'commitments/:id',
            loadComponent: () =>
              import('./pages/budgeting/commitments/commitment-detail.component').then(
                (m) => m.CommitmentDetailComponent
              ),
          },
          {
            path: 'financial-standing',
            loadComponent: () =>
              import('./pages/budgeting/financial-standing/financial-standing.component').then(
                (m) => m.FinancialStandingComponent
              ),
          },
          {
            path: 'alerts',
            loadComponent: () =>
              import('./pages/alerts/alerts.component').then((m) => m.AlertsComponent),
          },
          {
            path: 'plan',
            loadComponent: () =>
              import('./pages/budgeting/plan/plan.component').then((m) => m.PlanComponent),
          },
          {
            path: 'config/thresholds',
            loadComponent: () =>
              import('./pages/budgeting/config/thresholds.component').then(
                (m) => m.ThresholdsComponent
              ),
          },
          {
            path: 'config/type-maps',
            loadComponent: () =>
              import('./pages/budgeting/config/type-maps.component').then((m) => m.TypeMapsComponent),
          },
          {
            path: 'config/categories',
            redirectTo: 'config/type-maps',
            pathMatch: 'full',
          },
          {
            path: 'config/accounts',
            loadComponent: () =>
              import('./pages/budgeting/config/income-sources.component').then(
                (m) => m.IncomeSourcesComponent
              ),
          },
          {
            path: 'config/income-sources',
            redirectTo: 'config/accounts',
            pathMatch: 'full',
          },
          {
            path: 'risk',
            loadComponent: () => import('./pages/risk/risk.component').then((m) => m.RiskComponent),
          },
          {
            path: 'config/planned-items',
            loadComponent: () =>
              import('./pages/budgeting/config/planned-items.component').then((m) => m.PlannedItemsComponent),
          },
          {
            path: 'config/merchant-links',
            loadComponent: () =>
              import('./pages/budgeting/config/merchant-links.component').then(
                (m) => m.MerchantLinksComponent
              ),
          },
        ],
      },
      { path: 'alerts', redirectTo: 'budgeting/alerts', pathMatch: 'full' },
      {
        path: 'support',
        loadComponent: () => import('./pages/support/support.component').then((m) => m.SupportComponent),
      },
      {
        path: 'support/:id',
        loadComponent: () =>
          import('./pages/support/support-ticket.component').then((m) => m.SupportTicketComponent),
      },
      {
        // Support staff only (the API checks the role too).
        path: 'admin',
        canActivate: [staffGuard],
        children: [
          {
            path: '',
            pathMatch: 'full',
            loadComponent: () =>
              import('./pages/admin/admin-overview.component').then((m) => m.AdminOverviewComponent),
          },
          {
            path: 'users',
            loadComponent: () => import('./pages/admin/admin-users.component').then((m) => m.AdminUsersComponent),
          },
          {
            path: 'users/:id',
            loadComponent: () =>
              import('./pages/admin/admin-user-detail.component').then((m) => m.AdminUserDetailComponent),
          },
          {
            path: 'tickets',
            loadComponent: () => import('./pages/admin/admin-tickets.component').then((m) => m.AdminTicketsComponent),
          },
          {
            path: 'tickets/:id',
            loadComponent: () =>
              import('./pages/admin/admin-ticket-detail.component').then((m) => m.AdminTicketDetailComponent),
          },
          {
            path: 'support-settings',
            loadComponent: () =>
              import('./pages/admin/admin-support-settings.component').then((m) => m.AdminSupportSettingsComponent),
          },
          {
            path: 'audit-log',
            loadComponent: () =>
              import('./pages/admin/admin-audit-log.component').then((m) => m.AdminAuditLogComponent),
          },
        ],
      },
    ],
  },
  { path: '**', redirectTo: 'dashboard' },
];
