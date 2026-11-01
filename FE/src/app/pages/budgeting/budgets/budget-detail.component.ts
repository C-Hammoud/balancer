import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { BudgetingService } from '../../../core/budgeting.service';
import {
  BudgetCategory,
  BudgetGroup,
  PersonalBudgetAccessList,
  PersonalBudgetDetail,
  PersonalBudgetCategory,
  PersonalBudgetStatus,
  PersonalBudgetTransaction,
  PersonalBudgetUserRef,
} from '../../../core/models';
import { ToastService } from '../../../core/toast.service';
import { LocaleService } from '../../../core/locale.service';

interface SubDraft {
  category_id: string;
  category_name: string;
  allocated_amount: string;
}

@Component({
  selector: 'app-budget-detail',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, FormsModule, RouterLink],
  templateUrl: './budget-detail.component.html',
  styleUrl: './budget-detail.component.scss',
})
export class BudgetDetailComponent implements OnInit {
  private api = inject(BudgetingService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private fb = inject(FormBuilder);
  private toast = inject(ToastService);
  private locale = inject(LocaleService);

  readonly currencyOptions = this.locale.currencies;

  budget = signal<PersonalBudgetDetail | null>(null);
  loading = signal(true);
  saving = signal(false);
  showEdit = signal(false);
  showClone = signal(false);
  showCategoryForm = signal(false);
  cloning = signal(false);
  showShare = signal(false);
  access = signal<PersonalBudgetAccessList | null>(null);
  lookupResult = signal<{ found: boolean; can_invite?: boolean; user?: PersonalBudgetUserRef; detail?: string } | null>(null);
  sharing = signal(false);

  groups = signal<BudgetGroup[]>([]);
  globalCategories = signal<BudgetCategory[]>([]);
  newGroupId = '';
  newGroupForecast = '';
  showSubStep = signal(false);
  subDrafts = signal<SubDraft[]>([]);
  savingSubs = signal(false);
  collapsedGroups = signal<Set<string>>(new Set());

  shareForm = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    role: ['viewer' as 'viewer' | 'editor', Validators.required],
  });

  editForm = this.fb.nonNullable.group({
    name: ['', Validators.required],
    description: [''],
    currency: ['USD', Validators.required],
    start_date: ['', Validators.required],
    end_date: ['', Validators.required],
    total_amount: ['', Validators.required],
    status: ['active' as PersonalBudgetStatus, Validators.required],
    project_tag: [''],
    notes: [''],
  });

  cloneForm = this.fb.nonNullable.group({
    name: ['', Validators.required],
    start_date: ['', Validators.required],
    end_date: ['', Validators.required],
    status: ['draft' as PersonalBudgetStatus, Validators.required],
  });

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id');
    if (!id) {
      this.router.navigate(['/budgeting/budgets']);
      return;
    }
    this.api.categories().subscribe({
      next: (c) => {
        this.groups.set([...c.groups].sort((a, b) => a.order - b.order || a.name.localeCompare(b.name)));
        this.globalCategories.set(c.categories.filter((x) => x.include_in_reports));
      },
      error: () => {
        this.groups.set([]);
        this.globalCategories.set([]);
      },
    });
    this.load(id);
  }

  load(id: string): void {
    this.loading.set(true);
    this.api.personalBudget(id).subscribe({
      next: (detail) => {
        this.budget.set(detail);
        this.editForm.patchValue({
          name: detail.name,
          description: detail.description || '',
          currency: detail.currency,
          start_date: detail.start_date || '',
          end_date: detail.end_date || '',
          total_amount: detail.total_amount,
          status: detail.status,
          project_tag: detail.project_tag || '',
          notes: detail.notes || '',
        });
        this.cloneForm.patchValue({
          name: `${detail.name} (copy)`,
          start_date: detail.start_date || '',
          end_date: detail.end_date || '',
          status: 'draft',
        });
        this.loading.set(false);
        if (detail.can_share) {
          this.loadAccess(id);
        }
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not load budget.');
        this.router.navigate(['/budgeting/budgets']);
      },
    });
  }

  pctUsed(): number {
    const b = this.budget();
    return b ? Math.min(100, Math.max(0, b.percent_used || 0)) : 0;
  }

  statusLabel(status: string): string {
    const labels: Record<string, string> = {
      draft: 'Draft',
      active: 'Active',
      completed: 'Completed',
      archived: 'Archived',
    };
    return labels[status] || status;
  }

  categoryName(catId: string): string {
    const cats = this.budget()?.categories || [];
    for (const c of cats) {
      if (c.id === catId) return c.name;
      for (const s of c.sub_categories || []) {
        if (s.id === catId) return s.name;
      }
    }
    return '—';
  }

  canEdit(): boolean {
    const b = this.budget();
    if (!b) return false;
    if (b.can_edit != null) return b.can_edit;
    return b.access_role === 'owner' || b.access_role === 'editor';
  }

  canShare(): boolean {
    const b = this.budget();
    if (!b) return false;
    if (b.can_share != null) return b.can_share;
    return b.access_role === 'owner';
  }

  availableGroups(): BudgetGroup[] {
    const used = new Set(
      (this.budget()?.categories || [])
        .filter((c) => c.id !== '_uncategorized_' && c.group_id)
        .map((c) => c.group_id!)
    );
    return this.groups().filter((g) => !used.has(g.id));
  }

  subsForGroup(groupId: string): BudgetCategory[] {
    return this.globalCategories()
      .filter((c) => c.group_id === groupId)
      .sort((a, b) => a.order - b.order || a.name.localeCompare(b.name));
  }

  hasSubs(cat: PersonalBudgetCategory): boolean {
    return (cat.sub_categories?.length ?? 0) > 0;
  }

  isExpanded(catId: string): boolean {
    return !this.collapsedGroups().has(catId);
  }

  toggleGroup(catId: string): void {
    this.collapsedGroups.update((set) => {
      const next = new Set(set);
      if (next.has(catId)) next.delete(catId);
      else next.add(catId);
      return next;
    });
  }

  onNewGroupChange(): void {
    this.showSubStep.set(false);
    this.subDrafts.set([]);
    this.newGroupForecast = '';
  }

  openCategoryWizard(): void {
    this.showCategoryForm.set(true);
    this.newGroupId = '';
    this.newGroupForecast = '';
    this.showSubStep.set(false);
    this.subDrafts.set([]);
  }

  cancelCategoryWizard(): void {
    this.showCategoryForm.set(false);
    this.newGroupId = '';
    this.newGroupForecast = '';
    this.showSubStep.set(false);
    this.subDrafts.set([]);
  }

  saveNewGroupBudget(): void {
    const b = this.budget();
    if (!b) return;
    if (!this.newGroupId) {
      this.toast.error('Select a category first.');
      return;
    }
    const raw = (this.newGroupForecast ?? '').trim();
    if (!raw || Number(raw) <= 0) {
      this.toast.error('Enter a maximum utilization amount greater than zero.');
      return;
    }
    const subs = this.subsForGroup(this.newGroupId);
    this.subDrafts.set(
      subs.map((c) => ({
        category_id: c.id,
        category_name: c.name,
        allocated_amount: '',
      }))
    );
    this.showSubStep.set(true);
  }

  skipSubBudgets(): void {
    this.submitCategoryWithSubs([]);
  }

  saveOptionalSubBudgets(): void {
    const drafts = this.subDrafts().filter((s) => (s.allocated_amount || '').trim() !== '');
    this.submitCategoryWithSubs(drafts);
  }

  private submitCategoryWithSubs(drafts: SubDraft[]): void {
    const b = this.budget();
    if (!b || !this.newGroupId) return;
    const raw = (this.newGroupForecast ?? '').trim();
    if (!raw || Number(raw) <= 0) {
      this.toast.error('Enter a maximum utilization amount greater than zero.');
      return;
    }
    this.savingSubs.set(true);
    this.api
      .createPersonalBudgetCategory(b.id, {
        group_id: this.newGroupId,
        allocated_amount: raw,
        subcategories: drafts.map((d) => ({
          category_id: d.category_id,
          allocated_amount: d.allocated_amount,
        })),
      })
      .subscribe({
        next: (updated) => {
          this.savingSubs.set(false);
          this.budget.set(updated);
          this.cancelCategoryWizard();
          this.toast.success(
            drafts.length ? 'Category and subcategory budgets saved.' : 'Category budget saved.'
          );
        },
        error: (err) => {
          this.savingSubs.set(false);
          this.toast.fromHttpError(err, 'Could not add category.');
        },
      });
  }

  updateSubDraft(index: number, amount: string): void {
    this.subDrafts.update((list) =>
      list.map((row, i) => (i === index ? { ...row, allocated_amount: amount } : row))
    );
  }

  loadAccess(budgetId: string): void {
    this.api.personalBudgetMembers(budgetId).subscribe({
      next: (data) => this.access.set(data),
      error: () => this.access.set(null),
    });
  }

  toggleShare(): void {
    const opening = !this.showShare();
    this.showShare.set(opening);
    this.lookupResult.set(null);
    if (opening) {
      this.shareForm.reset({ email: '', role: 'viewer' });
    }
  }

  lookupEmail(): void {
    const email = this.shareForm.controls.email.value.trim();
    if (!email) return;
    this.api.lookupPersonalBudgetUser(email).subscribe({
      next: (res) => this.lookupResult.set(res),
      error: () => this.lookupResult.set({ found: false }),
    });
  }

  submitShare(): void {
    const b = this.budget();
    if (!b || this.shareForm.invalid) {
      this.shareForm.markAllAsTouched();
      return;
    }
    this.sharing.set(true);
    this.api.sharePersonalBudget(b.id, this.shareForm.getRawValue()).subscribe({
      next: (access) => {
        this.sharing.set(false);
        this.access.set(access);
        this.showShare.set(false);
        this.lookupResult.set(null);
        if (access.result === 'invited') {
          this.toast.success(
            access.email_sent === false
              ? 'Invitation saved, but the email could not be sent. Check mail settings.'
              : `Invitation email sent to ${access.invited_email || 'recipient'}.`
          );
        } else {
          this.toast.success('Budget shared. They will get an in-app and email notification.');
        }
      },
      error: (err) => {
        this.sharing.set(false);
        this.toast.fromHttpError(err, 'Could not share budget.');
      },
    });
  }

  changeMemberRole(memberId: string, role: string): void {
    const b = this.budget();
    if (!b) return;
    this.api.updatePersonalBudgetMember(b.id, memberId, role as 'viewer' | 'editor').subscribe({
      next: (access: PersonalBudgetAccessList) => {
        this.access.set(access);
        this.toast.success('Permission updated.');
      },
      error: (err: unknown) => this.toast.fromHttpError(err, 'Could not update permission.'),
    });
  }

  removeMember(memberId: string): void {
    const b = this.budget();
    if (!b) return;
    this.api.removePersonalBudgetMember(b.id, memberId).subscribe({
      next: (access) => {
        this.access.set(access);
        this.toast.success('Access removed.');
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not remove access.'),
    });
  }

  cancelInvite(inviteId: string): void {
    const b = this.budget();
    if (!b) return;
    this.api.cancelPersonalBudgetInvite(b.id, inviteId).subscribe({
      next: (access) => {
        this.access.set(access);
        this.toast.success('Invitation cancelled.');
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not cancel invitation.'),
    });
  }

  roleLabel(role: string): string {
    return role === 'editor' ? 'Editor' : 'Viewer';
  }

  saveEdit(): void {
    const b = this.budget();
    if (!b || this.editForm.invalid) {
      this.editForm.markAllAsTouched();
      return;
    }
    this.saving.set(true);
    this.api.updatePersonalBudget(b.id, this.editForm.getRawValue()).subscribe({
      next: (updated) => {
        this.saving.set(false);
        this.budget.set({ ...this.budget()!, ...updated });
        this.showEdit.set(false);
        this.toast.success('Budget updated.');
      },
      error: (err) => {
        this.saving.set(false);
        this.toast.fromHttpError(err, 'Could not update budget.');
      },
    });
  }

  /** Owner only: make this budget a sub-budget of the monthly plan, or take it out again. */
  togglePlan(): void {
    const b = this.budget();
    if (!b) return;
    const adding = !b.in_plan;
    const n = b.transactions_count ?? 0;
    const question = adding
      ? `Add "${b.name}" to your plan? Its money is set aside in your monthly plan` +
        (n ? `, and its ${n} tagged expense(s) will count only here, not in your category budgets.` : '.')
      : `Remove "${b.name}" from your plan? Its expenses will count in your category budgets again.`;
    if (!confirm(question)) return;
    this.api.updatePersonalBudget(b.id, { in_plan: adding }).subscribe({
      next: (updated) => {
        this.budget.set({ ...this.budget()!, ...updated });
        this.toast.success(adding ? 'Added to your plan.' : 'Removed from your plan.');
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not update the plan.'),
    });
  }

  archiveBudget(): void {
    const b = this.budget();
    if (!b) return;
    this.api.updatePersonalBudget(b.id, { status: 'archived' }).subscribe({
      next: (updated) => {
        this.budget.set({ ...this.budget()!, ...updated });
        this.toast.success('Budget archived.');
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not archive budget.'),
    });
  }

  cloneBudget(): void {
    const b = this.budget();
    if (!b || this.cloneForm.invalid) {
      this.cloneForm.markAllAsTouched();
      return;
    }
    this.cloning.set(true);
    this.api.clonePersonalBudget(b.id, this.cloneForm.getRawValue()).subscribe({
      next: (cloned) => {
        this.cloning.set(false);
        this.toast.success('Budget cloned.');
        this.router.navigate(['/budgeting/budgets', cloned.id]);
      },
      error: (err) => {
        this.cloning.set(false);
        this.toast.fromHttpError(err, 'Could not clone budget.');
      },
    });
  }

  deleteCategory(cat: PersonalBudgetCategory): void {
    const b = this.budget();
    if (!b || cat.id === '_uncategorized_') return;
    this.api.deletePersonalBudgetCategory(b.id, cat.id).subscribe({
      next: (updated) => {
        this.budget.set(updated);
        this.toast.success('Category removed.');
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not remove category.'),
    });
  }

  transactions(): PersonalBudgetTransaction[] {
    return this.budget()?.transactions || [];
  }
}
