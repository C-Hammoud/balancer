import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { BudgetingService } from '../../../core/budgeting.service';
import { BudgetCategory, BudgetGroup, MerchantLink } from '../../../core/models';
import { ToastService } from '../../../core/toast.service';

@Component({
  selector: 'app-merchant-links',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './merchant-links.component.html',
  styleUrl: './merchant-links.component.scss',
})
export class MerchantLinksComponent implements OnInit {
  private api = inject(BudgetingService);
  private fb = inject(FormBuilder);
  private toast = inject(ToastService);

  items = signal<MerchantLink[]>([]);
  groups = signal<BudgetGroup[]>([]);
  categories = signal<BudgetCategory[]>([]);
  loading = signal(true);

  form = this.fb.nonNullable.group({
    keyword: ['', Validators.required],
    group_id: ['', Validators.required],
    category_id: ['', Validators.required],
  });

  ngOnInit(): void {
    this.api.categories().subscribe({
      next: (c) => {
        this.groups.set([...c.groups].sort((a, b) => a.order - b.order || a.name.localeCompare(b.name)));
        this.categories.set(c.categories);
      },
      error: () => {
        this.groups.set([]);
        this.categories.set([]);
      },
    });
    this.reload();
  }

  subsForGroup(groupId: string): BudgetCategory[] {
    if (!groupId) return [];
    return this.categories()
      .filter((c) => c.group_id === groupId)
      .sort((a, b) => a.order - b.order || a.name.localeCompare(b.name));
  }

  onGroupChange(): void {
    this.form.patchValue({ category_id: '' });
  }

  reload(): void {
    this.loading.set(true);
    this.api.merchantLinks().subscribe({
      next: (rows) => {
        this.items.set(rows);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not load merchant links.');
      },
    });
  }

  linkLabel(l: MerchantLink): string {
    if (l.group_name && l.category_name) {
      return `${l.group_name} — ${l.category_name}`;
    }
    const sub = this.categories().find((c) => c.id === l.category_id);
    if (sub) {
      return `${sub.group_name || this.groups().find((g) => g.id === sub.group_id)?.name || ''} — ${sub.name}`;
    }
    return l.category_id;
  }

  submit(): void {
    if (this.form.invalid) {
      this.toast.error('Please fill in keyword, category, and subcategory.');
      return;
    }
    const raw = this.form.getRawValue();
    this.api.createMerchantLink(raw.keyword, raw.category_id).subscribe({
      next: () => {
        this.toast.success('Merchant link saved successfully.');
        this.form.reset({ keyword: '', group_id: '', category_id: '' });
        this.reload();
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not add link.'),
    });
  }

  remove(id: string): void {
    if (!confirm('Delete this link?')) return;
    this.api.deleteMerchantLink(id).subscribe({
      next: () => {
        this.toast.success('Link deleted.');
        this.reload();
      },
      error: (err) => this.toast.fromHttpError(err, 'Delete failed.'),
    });
  }
}
