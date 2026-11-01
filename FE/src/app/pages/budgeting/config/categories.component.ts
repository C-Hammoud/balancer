import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { BudgetingService } from '../../../core/budgeting.service';
import { BudgetCategory, BudgetGroup, CategoryGroupResponse } from '../../../core/models';
import { ToastService } from '../../../core/toast.service';

@Component({
  selector: 'app-categories-config',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink],
  templateUrl: './categories.component.html',
  styleUrl: './categories.component.scss',
})
export class CategoriesConfigComponent implements OnInit {
  private api = inject(BudgetingService);
  private fb = inject(FormBuilder);
  private toast = inject(ToastService);

  data = signal<CategoryGroupResponse | null>(null);
  loading = signal(true);
  editingGroupId = signal<string | null>(null);
  editingCatId = signal<string | null>(null);

  groupForm = this.fb.nonNullable.group({
    name: ['', Validators.required],
    order: [0],
  });

  categoryForm = this.fb.nonNullable.group({
    name: ['', Validators.required],
    group_id: ['', Validators.required],
    include_in_reports: [true],
    order: [0],
  });

  ngOnInit(): void {
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.api.categories().subscribe({
      next: (d) => {
        const groups = [...d.groups].sort((a, b) => a.order - b.order || a.name.localeCompare(b.name));
        const categories = [...d.categories].sort((a, b) => a.order - b.order || a.name.localeCompare(b.name));
        this.data.set({ groups, categories });
        this.loading.set(false);
        if (!this.categoryForm.value.group_id && groups.length) {
          this.categoryForm.patchValue({ group_id: groups[0].id });
        }
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not load categories.');
      },
    });
  }

  catsForGroup(groupId: string): BudgetCategory[] {
    return (this.data()?.categories || []).filter((c) => c.group_id === groupId);
  }

  startEditGroup(g: BudgetGroup): void {
    this.editingGroupId.set(g.id);
    this.groupForm.setValue({ name: g.name, order: g.order });
  }

  cancelEditGroup(): void {
    this.editingGroupId.set(null);
    this.groupForm.reset({ name: '', order: 0 });
  }

  saveGroup(): void {
    if (this.groupForm.invalid) {
      this.toast.error('Enter a category name.');
      return;
    }
    const raw = this.groupForm.getRawValue();
    const editId = this.editingGroupId();
    const req = editId
      ? this.api.updateGroup(editId, raw)
      : this.api.createGroup(raw);
    req.subscribe({
      next: () => {
        this.toast.success(editId ? 'Category updated.' : 'Category added.');
        this.cancelEditGroup();
        this.reload();
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not save category.'),
    });
  }

  removeGroup(g: BudgetGroup): void {
    const count = this.catsForGroup(g.id).length;
    if (count > 0) {
      this.toast.error(`Move or delete ${count} subcategory(ies) first.`);
      return;
    }
    if (!confirm(`Delete category “${g.name}”?`)) return;
    this.api.deleteGroup(g.id).subscribe({
      next: () => {
        this.toast.success('Category deleted.');
        this.reload();
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not delete category.'),
    });
  }

  startEditCategory(c: BudgetCategory): void {
    this.editingCatId.set(c.id);
    this.categoryForm.setValue({
      name: c.name,
      group_id: c.group_id,
      include_in_reports: c.include_in_reports,
      order: c.order,
    });
  }

  cancelEditCategory(): void {
    this.editingCatId.set(null);
    const firstGroup = this.data()?.groups[0]?.id || '';
    this.categoryForm.reset({
      name: '',
      group_id: firstGroup,
      include_in_reports: true,
      order: 0,
    });
  }

  saveCategory(): void {
    if (this.categoryForm.invalid) {
      this.toast.error('Enter a subcategory name and parent category.');
      return;
    }
    const raw = this.categoryForm.getRawValue();
    const editId = this.editingCatId();
    const req = editId
      ? this.api.updateCategory(editId, raw)
      : this.api.createCategory(raw);
    req.subscribe({
      next: () => {
        this.toast.success(editId ? 'Subcategory updated.' : 'Subcategory added.');
        this.cancelEditCategory();
        this.reload();
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not save subcategory.'),
    });
  }

  removeCategory(c: BudgetCategory): void {
    if (!confirm(`Delete subcategory “${c.name}”? Type maps pointing here will be cleared.`)) return;
    this.api.deleteCategory(c.id).subscribe({
      next: () => {
        this.toast.success('Subcategory deleted.');
        this.reload();
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not delete subcategory.'),
    });
  }
}
