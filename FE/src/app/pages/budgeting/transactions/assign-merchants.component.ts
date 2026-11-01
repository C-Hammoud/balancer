import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { BudgetingService } from '../../../core/budgeting.service';
import { BudgetCategory, BudgetGroup, Transaction } from '../../../core/models';
import { ToastService } from '../../../core/toast.service';
import {
  SAME_AS_DESCRIPTION,
  applyAssignmentToTransaction,
  isAssignmentDraftReady,
  isUnassignedExpense,
  subcategoriesForGroup,
  usesSameAsDescription,
} from './transaction-assign.helpers';

interface AssignmentDraft {
  txnId: string;
  group_id: string;
  category_id: string;
  saving?: boolean;
}

@Component({
  selector: 'app-assign-merchants',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './assign-merchants.component.html',
  styleUrl: './assign-merchants.component.scss',
})
export class AssignMerchantsComponent implements OnInit {
  private api = inject(BudgetingService);
  private toast = inject(ToastService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  now = new Date();
  month = `${this.now.getFullYear()}-${String(this.now.getMonth() + 1).padStart(2, '0')}`;

  items = signal<Transaction[]>([]);
  groups = signal<BudgetGroup[]>([]);
  categories = signal<BudgetCategory[]>([]);
  loading = signal(true);
  assignmentDrafts = signal<AssignmentDraft[]>([]);
  assigningAll = signal(false);

  readonly sameAsDescription = SAME_AS_DESCRIPTION;

  ngOnInit(): void {
    const qMonth = this.route.snapshot.queryParamMap.get('month');
    if (qMonth) this.month = qMonth;

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

  unassignedTransactions(): Transaction[] {
    return this.items().filter((t) => isUnassignedExpense(t, this.categories()));
  }

  transactionById(id: string): Transaction | undefined {
    return this.items().find((t) => t.id === id);
  }

  subsForGroup(groupId: string): BudgetCategory[] {
    return subcategoriesForGroup(this.categories(), groupId);
  }

  reload(): void {
    this.loading.set(true);
    this.api.transactions(this.month || undefined).subscribe({
      next: (rows) => {
        this.items.set(rows);
        this.loading.set(false);
        this.syncAssignmentDrafts();
      },
      error: (err) => {
        this.items.set([]);
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not load transactions.');
      },
    });
  }

  onMonthChange(): void {
    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: { month: this.month },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
    this.reload();
  }

  private syncAssignmentDrafts(): void {
    const unassigned = this.unassignedTransactions();
    const existing = new Map(this.assignmentDrafts().map((d) => [d.txnId, d]));
    this.assignmentDrafts.set(
      unassigned.map((t) => {
        const prev = existing.get(t.id);
        return prev ?? { txnId: t.id, group_id: '', category_id: '' };
      })
    );
  }

  updateAssignmentDraft(txnId: string, patch: Partial<AssignmentDraft>): void {
    this.assignmentDrafts.update((list) =>
      list.map((d) => {
        if (d.txnId !== txnId) return d;
        const next = { ...d, ...patch };
        if (patch.group_id !== undefined && patch.group_id !== d.group_id) {
          next.category_id = '';
        }
        return next;
      })
    );
  }

  assignmentReadyCount(): number {
    return this.assignmentDrafts().filter((d) => isAssignmentDraftReady(d) && !d.saving).length;
  }

  private addCreatedCategory(cat: BudgetCategory): void {
    this.categories.update((list) => [...list, cat]);
  }

  saveAssignment(draft: AssignmentDraft): void {
    const t = this.transactionById(draft.txnId);
    if (!t) return;
    if (!isAssignmentDraftReady(draft)) {
      this.toast.error('Select a category and subcategory.');
      return;
    }
    this.updateAssignmentDraft(draft.txnId, { saving: true });
    applyAssignmentToTransaction(
      this.api,
      this.categories(),
      t,
      draft.group_id,
      draft.category_id,
      (cat) => this.addCreatedCategory(cat)
    ).subscribe({
      next: () => {
        this.toast.success(
          usesSameAsDescription(draft.category_id)
            ? 'Merchant assigned using the bank description.'
            : 'Merchant assigned.'
        );
        this.reload();
      },
      error: (err) => {
        this.updateAssignmentDraft(draft.txnId, { saving: false });
        this.toast.fromHttpError(err, 'Could not assign merchant.');
      },
    });
  }

  saveAllAssignments(): void {
    const ready = this.assignmentDrafts().filter((d) => isAssignmentDraftReady(d) && !d.saving);
    if (!ready.length) {
      this.toast.error('Select category and subcategory for at least one transaction.');
      return;
    }
    this.assigningAll.set(true);
    let completed = 0;
    let succeeded = 0;
    const total = ready.length;

    const finish = () => {
      this.assigningAll.set(false);
      if (succeeded === total) {
        this.toast.success(`Assigned ${total} transaction(s).`);
      } else {
        this.toast.error(`Assigned ${succeeded} of ${total} transaction(s).`);
      }
      this.reload();
    };

    for (const draft of ready) {
      const t = this.transactionById(draft.txnId);
      if (!t) {
        completed += 1;
        if (completed === total) finish();
        continue;
      }
      this.updateAssignmentDraft(draft.txnId, { saving: true });
      applyAssignmentToTransaction(
        this.api,
        this.categories(),
        t,
        draft.group_id,
        draft.category_id,
        (cat) => this.addCreatedCategory(cat)
      ).subscribe({
        next: () => {
          succeeded += 1;
          completed += 1;
          if (completed === total) finish();
        },
        error: () => {
          this.updateAssignmentDraft(draft.txnId, { saving: false });
          completed += 1;
          if (completed === total) finish();
        },
      });
    }
  }
}
