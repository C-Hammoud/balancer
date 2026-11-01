import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { BudgetingService } from '../../../core/budgeting.service';
import { PersonalBudget, PersonalBudgetDashboard, PersonalBudgetNotification, PersonalBudgetStatus } from '../../../core/models';
import { ToastService } from '../../../core/toast.service';
import { LocaleService } from '../../../core/locale.service';

@Component({
  selector: 'app-budgets',
  standalone: true,
  imports: [CommonModule, FormsModule, ReactiveFormsModule, RouterLink],
  templateUrl: './budgets.component.html',
  styleUrl: './budgets.component.scss',
})
export class BudgetsComponent implements OnInit {
  private api = inject(BudgetingService);
  private fb = inject(FormBuilder);
  private toast = inject(ToastService);
  private locale = inject(LocaleService);
  private router = inject(Router);

  readonly currencyOptions = this.locale.currencies;
  readonly statusOptions: { value: PersonalBudgetStatus | ''; label: string }[] = [
    { value: '', label: 'All statuses' },
    { value: 'draft', label: 'Draft' },
    { value: 'active', label: 'Active' },
    { value: 'completed', label: 'Completed' },
    { value: 'archived', label: 'Archived' },
  ];
  readonly sortOptions = [
    { value: 'created_desc', label: 'Newest first' },
    { value: 'created_asc', label: 'Oldest first' },
    { value: 'name', label: 'Name' },
    { value: 'amount', label: 'Budget amount' },
    { value: 'spent', label: 'Spending' },
  ];

  dashboard = signal<PersonalBudgetDashboard | null>(null);
  budgets = signal<PersonalBudget[]>([]);
  sharedWithMe = signal<PersonalBudget[]>([]);
  notifications = signal<PersonalBudgetNotification[]>([]);
  loading = signal(true);
  showForm = signal(false);
  saving = signal(false);

  search = '';
  statusFilter = '';
  sort = 'created_desc';
  periodStart = '';
  periodEnd = '';

  form = this.fb.nonNullable.group({
    name: ['', Validators.required],
    description: [''],
    currency: [this.locale.defaultCurrency(), Validators.required],
    start_date: ['', Validators.required],
    end_date: ['', Validators.required],
    total_amount: ['', Validators.required],
    status: ['draft' as PersonalBudgetStatus, Validators.required],
    project_tag: [''],
    notes: [''],
  });

  ngOnInit(): void {
    this.form.controls.currency.setValue(this.locale.defaultCurrency());
    this.reload();
    this.loadNotifications();
  }

  reload(): void {
    this.loading.set(true);
    this.api.personalBudgetDashboard().subscribe({
      next: (dash) => {
        this.dashboard.set(dash);
        this.budgets.set(dash.budgets);
        this.sharedWithMe.set(dash.shared_with_me || []);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not load budgets.');
      },
    });
  }

  loadNotifications(): void {
    this.api.personalBudgetNotifications().subscribe({
      next: (res) => this.notifications.set((res.notifications || []).filter((n) => !n.read)),
      error: () => this.notifications.set([]),
    });
  }

  dismissNotification(n: PersonalBudgetNotification): void {
    this.api.markPersonalBudgetNotificationRead(n.id).subscribe({
      next: () => {
        this.notifications.update((list) => list.filter((x) => x.id !== n.id));
        this.router.navigate(['/budgeting/budgets', n.budget_id]);
      },
    });
  }

  roleLabel(role: string | undefined): string {
    if (role === 'viewer') return 'Viewer';
    if (role === 'editor') return 'Editor';
    if (role === 'owner') return 'Owner';
    return role || '';
  }

  applyFilters(): void {
    this.loading.set(true);
    this.api
      .personalBudgets({
        search: this.search,
        status: this.statusFilter,
        sort: this.sort,
        period_start: this.periodStart || undefined,
        period_end: this.periodEnd || undefined,
      })
      .subscribe({
        next: (res) => {
          this.budgets.set(res.budgets);
          this.sharedWithMe.set(res.shared_with_me || []);
          this.loading.set(false);
        },
        error: (err) => {
          this.loading.set(false);
          this.toast.fromHttpError(err, 'Could not filter budgets.');
        },
      });
  }

  toggleForm(): void {
    const opening = !this.showForm();
    this.showForm.set(opening);
    if (opening) {
      this.form.reset({
        name: '',
        description: '',
        currency: this.locale.defaultCurrency(),
        start_date: '',
        end_date: '',
        total_amount: '',
        status: 'draft',
        project_tag: '',
        notes: '',
      });
    }
  }

  open(b: PersonalBudget): void {
    this.router.navigate(['/budgeting/budgets', b.id]);
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.toast.error('Please fill in the required fields.');
      return;
    }
    this.saving.set(true);
    this.api.createPersonalBudget(this.form.getRawValue()).subscribe({
      next: (created) => {
        this.saving.set(false);
        this.toast.success('Budget created.');
        this.showForm.set(false);
        this.router.navigate(['/budgeting/budgets', created.id]);
      },
      error: (err) => {
        this.saving.set(false);
        this.toast.fromHttpError(err, 'Could not create budget.');
      },
    });
  }

  statusLabel(status: string): string {
    return this.statusOptions.find((s) => s.value === status)?.label || status;
  }

  periodLabel(b: PersonalBudget): string {
    if (b.start_date && b.end_date) return `${b.start_date} – ${b.end_date}`;
    if (b.start_date) return `From ${b.start_date}`;
    if (b.end_date) return `Until ${b.end_date}`;
    return '—';
  }

  pctWidth(b: PersonalBudget): number {
    return Math.min(100, Math.max(0, b.percent_used || 0));
  }
}
