import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { BudgetingService } from '../../../core/budgeting.service';
import { BudgetCategory, BudgetGroup, BudgetRow } from '../../../core/models';
import { ToastService } from '../../../core/toast.service';

interface SubDraft {
  category_id: string;
  category_name: string;
  forecast: string;
}

@Component({
  selector: 'app-monthly-forecasts',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './monthly-forecasts.component.html',
  styleUrl: './monthly-forecasts.component.scss',
})
export class MonthlyForecastsComponent implements OnInit {
  private api = inject(BudgetingService);
  private toast = inject(ToastService);

  now = new Date();
  year = this.now.getFullYear();
  month = this.now.getMonth() + 1;
  years = Array.from({ length: 5 }, (_, i) => this.year - 2 + i);
  months = [
    { v: 1, n: 'Jan' }, { v: 2, n: 'Feb' }, { v: 3, n: 'Mar' }, { v: 4, n: 'Apr' },
    { v: 5, n: 'May' }, { v: 6, n: 'Jun' }, { v: 7, n: 'Jul' }, { v: 8, n: 'Aug' },
    { v: 9, n: 'Sep' }, { v: 10, n: 'Oct' }, { v: 11, n: 'Nov' }, { v: 12, n: 'Dec' },
  ];

  rows = signal<BudgetRow[]>([]);
  groups = signal<BudgetGroup[]>([]);
  categories = signal<BudgetCategory[]>([]);
  groupForecasts: Record<string, string> = {};
  subForecasts: Record<string, string> = {};
  loading = signal(true);

  newGroupId = '';
  newGroupForecast = '';
  showSubStep = signal(false);
  subDrafts = signal<SubDraft[]>([]);
  savingSubs = signal(false);
  collapsedGroups = signal<Set<string>>(new Set());
  private collapseInitialized = false;

  ngOnInit(): void {
    this.api.categories().subscribe({
      next: (c) => {
        this.groups.set([...c.groups].sort((a, b) => a.order - b.order || a.name.localeCompare(b.name)));
        this.categories.set(c.categories.filter((x) => x.include_in_reports));
      },
      error: () => {
        this.groups.set([]);
        this.categories.set([]);
      },
    });
    this.reload();
  }

  subsForGroup(groupId: string): BudgetCategory[] {
    return this.categories()
      .filter((c) => c.group_id === groupId)
      .sort((a, b) => a.order - b.order || a.name.localeCompare(b.name));
  }

  availableGroups(): BudgetGroup[] {
    const budgeted = new Set(this.rows().map((r) => r.group_id).filter(Boolean));
    return this.groups().filter((g) => !budgeted.has(g.id));
  }

  reload(clearSubStep = true): void {
    this.loading.set(true);
    if (clearSubStep) {
      this.showSubStep.set(false);
    }
    this.api.budgets(this.year, this.month).subscribe({
      next: (res) => {
        this.rows.set(res.rows);
        this.groupForecasts = {};
        this.subForecasts = {};
        for (const r of res.rows) {
          if (r.group_id) {
            const explicit = r.forecast_explicit;
            this.groupForecasts[r.group_id] =
              explicit != null && explicit !== '' ? String(explicit) : '';
          }
          for (const s of r.sub_budgets || []) {
            this.subForecasts[s.category_id] = String(s.forecast);
          }
        }
        if (!this.collapseInitialized) {
          const collapsed = new Set<string>();
          for (const r of res.rows) {
            if (r.group_id && (r.sub_budgets?.length ?? 0) > 0) {
              collapsed.add(r.group_id);
            }
          }
          this.collapsedGroups.set(collapsed);
          this.collapseInitialized = true;
        }
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not load monthly forecasts.');
      },
    });
  }

  saveGroup(groupId: string): void {
    const raw = (this.groupForecasts[groupId] ?? '').trim();
    const value = raw === '' ? '0' : raw;
    this.api.updateGroupBudget(this.year, this.month, groupId, value).subscribe({
      next: () => {
        this.toast.success('Category budget saved.');
        this.reload();
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not save budget.'),
    });
  }

  saveSub(categoryId: string): void {
    const val = (this.subForecasts[categoryId] || '').trim();
    this.api.updateBudget(this.year, this.month, categoryId, val || '0').subscribe({
      next: () => {
        this.toast.success('Subcategory budget saved.');
        this.reload();
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not save subcategory budget.'),
    });
  }

  onNewGroupChange(): void {
    this.showSubStep.set(false);
    this.subDrafts.set([]);
  }

  saveNewGroupBudget(): void {
    if (!this.newGroupId) {
      this.toast.error('Select a category first.');
      return;
    }
    const raw = (this.newGroupForecast ?? '').trim();
    if (!raw || Number(raw) <= 0) {
      this.toast.error('Enter a maximum utilization forecast greater than zero.');
      return;
    }
    this.api.updateGroupBudget(this.year, this.month, this.newGroupId, raw).subscribe({
      next: () => {
        this.toast.success('Category forecast saved.');
        const subs = this.subsForGroup(this.newGroupId);
        this.subDrafts.set(
          subs.map((c) => ({
            category_id: c.id,
            category_name: c.name,
            forecast: this.subForecasts[c.id] || '',
          }))
        );
        this.showSubStep.set(true);
        this.reload(false);
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not save category forecast.'),
    });
  }

  skipSubBudgets(): void {
    this.newGroupId = '';
    this.newGroupForecast = '';
    this.showSubStep.set(false);
    this.subDrafts.set([]);
  }

  saveOptionalSubBudgets(): void {
    const drafts = this.subDrafts().filter((s) => (s.forecast || '').trim() !== '');
    if (!drafts.length) {
      this.skipSubBudgets();
      this.toast.success('Category budget saved without subcategory splits.');
      return;
    }
    this.savingSubs.set(true);
    let done = 0;
    for (const s of drafts) {
      this.api.updateBudget(this.year, this.month, s.category_id, s.forecast).subscribe({
        next: () => {
          done += 1;
          if (done === drafts.length) {
            this.savingSubs.set(false);
            this.toast.success('Subcategory budgets saved.');
            this.skipSubBudgets();
            this.reload();
          }
        },
        error: (err) => {
          this.savingSubs.set(false);
          this.toast.fromHttpError(err, `Could not save ${s.category_name}.`);
        },
      });
    }
  }

  effectiveForecast(row: BudgetRow): string {
    const explicit = (this.groupForecasts[row.group_id!] ?? '').trim();
    if (explicit !== '') return explicit;
    return row.forecast_from_subs || row.forecast || '0';
  }

  subSum(row: BudgetRow): string {
    return row.forecast_from_subs || '0';
  }

  hasSubs(row: BudgetRow): boolean {
    return (row.sub_budgets?.length ?? 0) > 0;
  }

  isExpanded(groupId: string): boolean {
    return !this.collapsedGroups().has(groupId);
  }

  toggleGroup(groupId: string): void {
    this.collapsedGroups.update((set) => {
      const next = new Set(set);
      if (next.has(groupId)) {
        next.delete(groupId);
      } else {
        next.add(groupId);
      }
      return next;
    });
  }

  expandAll(): void {
    this.collapsedGroups.set(new Set());
  }

  collapseAll(): void {
    const collapsed = new Set<string>();
    for (const r of this.rows()) {
      if (r.group_id && this.hasSubs(r)) {
        collapsed.add(r.group_id);
      }
    }
    this.collapsedGroups.set(collapsed);
  }

  openSubEditor(groupId: string): void {
    this.collapsedGroups.update((set) => {
      const next = new Set(set);
      next.delete(groupId);
      return next;
    });
    this.newGroupId = groupId;
    this.newGroupForecast = this.groupForecasts[groupId] || '';
    this.subDrafts.set(
      this.subsForGroup(groupId).map((c) => ({
        category_id: c.id,
        category_name: c.name,
        forecast: this.subForecasts[c.id] || '',
      }))
    );
    this.showSubStep.set(true);
  }

  updateSubDraft(index: number, forecast: string): void {
    this.subDrafts.update((list) =>
      list.map((row, i) => (i === index ? { ...row, forecast } : row))
    );
  }
}
