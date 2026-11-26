import { Component, EventEmitter, Input, OnChanges, Output, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { forkJoin, Observable } from 'rxjs';
import { BudgetingService } from '../../../core/budgeting.service';
import { FinanceDataRefreshService } from '../../../core/finance-data-refresh.service';
import { BudgetRow } from '../../../core/models';
import { ToastService } from '../../../core/toast.service';
import { AmountPipe } from '../../../shared/amount.pipe';
import { StackCollapseDirective } from '../../../shared/stack-collapse.directive';

/**
 * The month's budgets: one editable amount per category group (optionally split into
 * subcategories), with what was spent and what is left. Used inside the Monthly budget page.
 */
@Component({
  selector: 'app-budget-table',
  standalone: true,
  imports: [StackCollapseDirective, CommonModule, FormsModule, AmountPipe],
  templateUrl: './budget-table.component.html',
  styleUrl: './budget-table.component.scss',
})
export class BudgetTableComponent implements OnChanges {
  private api = inject(BudgetingService);
  private toast = inject(ToastService);
  private refresh = inject(FinanceDataRefreshService);

  @Input({ required: true }) year!: number;
  @Input({ required: true }) month!: number;
  @Input() currency = '';
  /** Emits the rows after every load, so the page knows whether the month has budgets. */
  @Output() loaded = new EventEmitter<BudgetRow[]>();
  /** Emits after amounts were saved. */
  @Output() saved = new EventEmitter<void>();

  rows = signal<BudgetRow[]>([]);
  loading = signal(true);
  saving = signal(false);
  expanded = signal<Set<string>>(new Set());

  // Editable amounts: group_id -> amount and category_id -> amount ('' = not set)
  groupDraft: Record<string, string> = {};
  subDraft: Record<string, string> = {};
  private groupSaved: Record<string, string> = {};
  private subSaved: Record<string, string> = {};

  ngOnChanges(): void {
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.api.budgets(this.year, this.month).subscribe({
      next: (res) => {
        const rows = res.rows.filter((r) => r.group_id);
        this.groupSaved = {};
        this.subSaved = {};
        for (const r of rows) {
          this.groupSaved[r.group_id!] = this.clean(r.forecast_explicit);
          for (const s of r.sub_budgets || []) this.subSaved[s.category_id] = this.clean(s.forecast);
        }
        this.discard();
        this.rows.set(rows);
        this.loading.set(false);
        this.loaded.emit(rows);
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not load this month’s budgets.');
      },
    });
  }

  private clean(v: string | number | null | undefined): string {
    const n = Number(v);
    return v != null && v !== '' && n > 0 ? String(n) : '';
  }

  discard(): void {
    this.groupDraft = { ...this.groupSaved };
    this.subDraft = { ...this.subSaved };
  }

  private changedKeys(draft: Record<string, string>, saved: Record<string, string>): string[] {
    return Object.keys(draft).filter((k) => (Number(draft[k]) || 0) !== (Number(saved[k]) || 0));
  }

  isDirty(): boolean {
    return (
      this.changedKeys(this.groupDraft, this.groupSaved).length > 0 ||
      this.changedKeys(this.subDraft, this.subSaved).length > 0
    );
  }

  save(): void {
    const all = { ...this.groupDraft, ...this.subDraft };
    if (Object.values(all).some((v) => v !== '' && v != null && (isNaN(Number(v)) || Number(v) < 0))) {
      this.toast.error('Amounts must be zero or more.');
      return;
    }
    const calls: Observable<unknown>[] = [
      ...this.changedKeys(this.groupDraft, this.groupSaved).map((gid) =>
        this.api.updateGroupBudget(this.year, this.month, gid, this.groupDraft[gid] || '0')
      ),
      ...this.changedKeys(this.subDraft, this.subSaved).map((cid) =>
        this.api.updateBudget(this.year, this.month, cid, this.subDraft[cid] || '0')
      ),
    ];
    if (!calls.length) return;
    this.saving.set(true);
    forkJoin(calls).subscribe({
      next: () => {
        this.saving.set(false);
        this.toast.success('Budget saved.');
        this.refresh.notify();
        this.saved.emit();
        this.reload();
      },
      error: (err) => {
        this.saving.set(false);
        this.toast.fromHttpError(err, 'Could not save the budget.');
      },
    });
  }

  // ---- Live figures (follow the drafts while typing) ----

  subTotal(row: BudgetRow): number {
    return (row.sub_budgets || []).reduce((sum, s) => sum + (Number(this.subDraft[s.category_id]) || 0), 0);
  }

  /** Group budget: its own amount, else the sum of its subcategory amounts. */
  budgetOf(row: BudgetRow): number {
    const own = Number(this.groupDraft[row.group_id!]) || 0;
    return own > 0 ? own : this.subTotal(row);
  }

  spentOf(row: BudgetRow): number {
    return Number(row.actual) || 0;
  }

  leftOf(row: BudgetRow): number {
    return this.budgetOf(row) - this.spentOf(row);
  }

  pct(row: BudgetRow): number {
    const b = this.budgetOf(row);
    return b > 0 ? (this.spentOf(row) / b) * 100 : 0;
  }

  tone(row: BudgetRow): string {
    const b = this.budgetOf(row);
    if (b <= 0) return this.spentOf(row) > 0 ? 'unset' : 'empty';
    const p = this.pct(row);
    return p > 100 ? 'over' : p >= 85 ? 'warn' : 'ok';
  }

  totalBudget(): number {
    return this.rows().reduce((sum, r) => sum + this.budgetOf(r), 0);
  }

  totalSpent(): number {
    return this.rows().reduce((sum, r) => sum + this.spentOf(r), 0);
  }

  // ---- Subcategory rows ----

  hasSubs(row: BudgetRow): boolean {
    return (row.sub_budgets?.length ?? 0) > 0;
  }

  isExpanded(groupId: string): boolean {
    return this.expanded().has(groupId);
  }

  toggle(groupId: string): void {
    this.expanded.update((set) => {
      const next = new Set(set);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  }
}
