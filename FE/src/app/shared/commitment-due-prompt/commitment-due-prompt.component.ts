import { Component, HostListener, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { BudgetingService } from '../../core/budgeting.service';
import { FinanceDataRefreshService } from '../../core/finance-data-refresh.service';
import { BudgetAlert } from '../../core/models';
import { ToastService } from '../../core/toast.service';

const DISMISS_KEY = 'commitment_due_dismissed';

@Component({
  selector: 'app-commitment-due-prompt',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './commitment-due-prompt.component.html',
  styleUrl: './commitment-due-prompt.component.scss',
})
export class CommitmentDuePromptComponent implements OnInit {
  private api = inject(BudgetingService);
  private refresh = inject(FinanceDataRefreshService);
  private toast = inject(ToastService);

  current = signal<BudgetAlert | null>(null);
  queue = signal<BudgetAlert[]>([]);
  categories = signal<{ id: string; name: string; group_name: string }[]>([]);
  categoryId = '';
  saving = signal(false);

  ngOnInit(): void {
    this.api.categories().subscribe({
      next: (c) => this.categories.set(c.categories),
      error: () => this.categories.set([]),
    });
    this.loadDuePrompts();
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.current()) this.dismissCurrent();
  }

  private loadDuePrompts(): void {
    this.api.alerts('open', false).subscribe({
      next: (rows) => {
        const prompts = this.filterDuePrompts(rows);
        this.queue.set(prompts);
        this.showNext();
      },
      error: () => {
        this.queue.set([]);
        this.current.set(null);
      },
    });
  }

  private filterDuePrompts(alerts: BudgetAlert[]): BudgetAlert[] {
    const today = new Date().toISOString().slice(0, 10);
    const dismissed = this.getDismissedIds();
    return alerts
      .filter(
        (a) =>
          (a.alert_type === 'commitment_due' ||
            (a.category_id || '').startsWith('commitment:')) &&
          !a.is_resolved &&
          !dismissed.has(a.id) &&
          !!a.due_date &&
          a.due_date.slice(0, 10) <= today
      )
      .sort((a, b) => (a.due_date || '').localeCompare(b.due_date || ''));
  }

  private getDismissedIds(): Set<string> {
    try {
      const raw = sessionStorage.getItem(DISMISS_KEY);
      if (!raw) return new Set();
      const parsed = JSON.parse(raw) as { date: string; ids: string[] };
      const today = new Date().toISOString().slice(0, 10);
      if (parsed.date !== today) return new Set();
      return new Set(parsed.ids || []);
    } catch {
      return new Set();
    }
  }

  private dismissForToday(alertId: string): void {
    const today = new Date().toISOString().slice(0, 10);
    const ids = this.getDismissedIds();
    ids.add(alertId);
    sessionStorage.setItem(DISMISS_KEY, JSON.stringify({ date: today, ids: [...ids] }));
  }

  private closeCurrent(): void {
    this.current.set(null);
    this.categoryId = '';
    this.saving.set(false);
  }

  private showNext(): void {
    const next = this.queue()[0] ?? null;
    this.current.set(next);
    this.categoryId = '';
  }

  private finishAlert(alertId: string): void {
    this.dismissForToday(alertId);
    this.queue.update((q) => q.filter((a) => a.id !== alertId));
    this.closeCurrent();
    this.refresh.notify();
    setTimeout(() => this.showNext(), 0);
  }

  commitmentLabel(a: BudgetAlert): string {
    return a.commitment_name || a.title.replace(/^(Due soon|Overdue):\s*/i, '') || 'Commitment';
  }

  dismissCurrent(): void {
    const alert = this.current();
    if (!alert || this.saving()) return;
    this.dismissForToday(alert.id);
    this.queue.update((q) => q.filter((a) => a.id !== alert.id));
    this.closeCurrent();
    setTimeout(() => this.showNext(), 0);
  }

  skip(): void {
    const alert = this.current();
    if (!alert || this.saving()) return;
    this.saving.set(true);
    this.api.skipCommitmentDue(alert.id).subscribe({
      next: () => {
        this.toast.success('Skipped — payment not added to transactions.');
        this.finishAlert(alert.id);
      },
      error: (err) => {
        this.saving.set(false);
        this.toast.fromHttpError(err, 'Could not update alert.');
      },
    });
  }

  confirmAdd(): void {
    const alert = this.current();
    if (!alert || this.saving()) return;
    if (!this.categoryId) {
      this.toast.error('Pick a budget category to include in utilization.');
      return;
    }
    this.saving.set(true);
    this.api.recordCommitmentDue(alert.id, this.categoryId).subscribe({
      next: () => {
        this.toast.success('Payment recorded. It appears under Expenses and Transactions.');
        this.finishAlert(alert.id);
      },
      error: (err) => {
        this.saving.set(false);
        if (err?.status === 409) {
          this.toast.success('Payment was already recorded.');
          this.finishAlert(alert.id);
          return;
        }
        this.toast.fromHttpError(err, 'Could not record payment.');
      },
    });
  }
}
