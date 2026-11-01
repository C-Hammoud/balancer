import { Component, HostListener, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { BudgetingService } from '../../../core/budgeting.service';
import { BudgetCategory, BudgetGroup, CategoryGroupResponse } from '../../../core/models';
import { ToastService } from '../../../core/toast.service';

const PREVIEW_SUBS = 4;

@Component({
  selector: 'app-type-maps',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink],
  templateUrl: './type-maps.component.html',
  styleUrl: './type-maps.component.scss',
})
export class TypeMapsComponent implements OnInit {
  private api = inject(BudgetingService);
  private fb = inject(FormBuilder);
  private toast = inject(ToastService);
  private route = inject(ActivatedRoute);

  groups = signal<BudgetGroup[]>([]);
  categories = signal<BudgetCategory[]>([]);
  loading = signal(true);
  fromUnmapped = signal(false);

  modalOpen = signal(false);
  modalMode = signal<'add' | 'edit'>('add');
  editingGroup = signal<BudgetGroup | null>(null);
  editingSubs = signal<BudgetCategory[]>([]);
  editingSubId = signal<string | null>(null);

  groupForm = this.fb.nonNullable.group({
    name: ['', Validators.required],
    order: [0],
  });

  subForm = this.fb.nonNullable.group({
    name: ['', Validators.required],
    include_in_reports: [true],
    order: [0],
  });

  readonly previewCount = PREVIEW_SUBS;

  ngOnInit(): void {
    this.fromUnmapped.set(this.route.snapshot.queryParamMap.get('from') === 'unmapped');
    this.reload();
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.modalOpen()) this.closeModal();
  }

  reload(keepEditId?: string | null): void {
    this.loading.set(true);
    this.api.categories().subscribe({
      next: (c: CategoryGroupResponse) => {
        const groups = [...c.groups].sort((a, b) => a.order - b.order || a.name.localeCompare(b.name));
        const categories = [...c.categories].sort(
          (a, b) => a.order - b.order || a.name.localeCompare(b.name)
        );
        this.groups.set(groups);
        this.categories.set(categories);
        this.loading.set(false);

        if (keepEditId) {
          const g = groups.find((x) => x.id === keepEditId) || null;
          if (g) {
            this.editingGroup.set(g);
            this.editingSubs.set(categories.filter((x) => x.group_id === g.id));
            this.groupForm.setValue({ name: g.name, order: g.order });
          }
        }
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not load categories.');
      },
    });
  }

  catsForGroup(groupId: string): BudgetCategory[] {
    return this.categories().filter((c) => c.group_id === groupId);
  }

  previewSubs(groupId: string): BudgetCategory[] {
    return this.catsForGroup(groupId).slice(0, PREVIEW_SUBS);
  }

  extraSubCount(groupId: string): number {
    return Math.max(0, this.catsForGroup(groupId).length - PREVIEW_SUBS);
  }

  openAdd(): void {
    this.modalMode.set('add');
    this.editingGroup.set(null);
    this.editingSubs.set([]);
    this.editingSubId.set(null);
    this.groupForm.reset({ name: '', order: this.groups().length });
    this.subForm.reset({ name: '', include_in_reports: true, order: 0 });
    this.modalOpen.set(true);
  }

  openEdit(g: BudgetGroup): void {
    this.modalMode.set('edit');
    this.editingGroup.set(g);
    this.editingSubs.set(this.catsForGroup(g.id));
    this.editingSubId.set(null);
    this.groupForm.setValue({ name: g.name, order: g.order });
    this.subForm.reset({ name: '', include_in_reports: true, order: this.catsForGroup(g.id).length });
    this.modalOpen.set(true);
  }

  closeModal(): void {
    this.modalOpen.set(false);
    this.editingGroup.set(null);
    this.editingSubs.set([]);
    this.editingSubId.set(null);
  }

  saveCategory(): void {
    if (this.groupForm.invalid) {
      this.toast.error('Enter a category name.');
      return;
    }
    const raw = this.groupForm.getRawValue();
    const mode = this.modalMode();
    const editing = this.editingGroup();

    if (mode === 'add') {
      this.api.createGroup(raw).subscribe({
        next: (g) => {
          this.toast.success('Category added.');
          this.modalMode.set('edit');
          this.editingGroup.set(g);
          this.reload(g.id);
        },
        error: (err) => this.toast.fromHttpError(err, 'Could not add category.'),
      });
      return;
    }

    if (!editing) return;
    this.api.updateGroup(editing.id, raw).subscribe({
      next: () => {
        this.toast.success('Category updated.');
        this.reload(editing.id);
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not update category.'),
    });
  }

  deleteCategory(): void {
    const g = this.editingGroup();
    if (!g) return;
    const count = this.catsForGroup(g.id).length;
    if (count > 0) {
      this.toast.error(`Delete or move ${count} subcategory(ies) first.`);
      return;
    }
    if (!confirm(`Delete category “${g.name}”?`)) return;
    this.api.deleteGroup(g.id).subscribe({
      next: () => {
        this.toast.success('Category deleted.');
        this.closeModal();
        this.reload();
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not delete category.'),
    });
  }

  startEditSub(c: BudgetCategory): void {
    this.editingSubId.set(c.id);
    this.subForm.setValue({
      name: c.name,
      include_in_reports: c.include_in_reports,
      order: c.order,
    });
  }

  cancelEditSub(): void {
    this.editingSubId.set(null);
    const g = this.editingGroup();
    this.subForm.reset({
      name: '',
      include_in_reports: true,
      order: g ? this.catsForGroup(g.id).length : 0,
    });
  }

  saveSub(): void {
    const g = this.editingGroup();
    if (!g) {
      this.toast.error('Save the category first.');
      return;
    }
    if (this.subForm.invalid) {
      this.toast.error('Enter a subcategory name.');
      return;
    }
    const raw = this.subForm.getRawValue();
    const editId = this.editingSubId();
    const req = editId
      ? this.api.updateCategory(editId, { ...raw, group_id: g.id })
      : this.api.createCategory({ ...raw, group_id: g.id });

    req.subscribe({
      next: () => {
        this.toast.success(editId ? 'Subcategory updated.' : 'Subcategory added.');
        this.cancelEditSub();
        this.reload(g.id);
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not save subcategory.'),
    });
  }

  removeSub(c: BudgetCategory): void {
    const g = this.editingGroup();
    if (!g) return;
    if (!confirm(`Delete subcategory “${c.name}”?`)) return;
    this.api.deleteCategory(c.id).subscribe({
      next: () => {
        this.toast.success('Subcategory deleted.');
        this.reload(g.id);
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not delete subcategory.'),
    });
  }
}
