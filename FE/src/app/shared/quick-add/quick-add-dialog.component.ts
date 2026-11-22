import { Component, ElementRef, HostListener, effect, inject, signal, untracked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { BudgetingService } from '../../core/budgeting.service';
import { FinanceDataRefreshService } from '../../core/finance-data-refresh.service';
import { LocaleService } from '../../core/locale.service';
import { ToastService } from '../../core/toast.service';
import { BudgetCategory } from '../../core/models';
import { formatAmount } from '../amount.pipe';
import {
  QuickDirection,
  QuickRow,
  QuickRowDefaults,
  SAME_AS_DESCRIPTION,
  duplicateQuickRow,
  newQuickRow,
  quickRowError,
  quickRowErrorsFromResponse,
  quickRowHasData,
  quickTotals,
  toQuickInput,
  usesDescriptionAsMerchant,
} from './quick-add.helpers';
import { QuickAddOptions, QuickAddService, defaultAccountId, merchantsOf } from './quick-add.service';

const MAX_ROWS = 50;

/**
 * "Add transactions" screen opened by the + button (and the dashboard widget's "Add several…"):
 * one or more expenses / incomes, saved together in one call.
 */
@Component({
  selector: 'app-quick-add-dialog',
  standalone: true,
  imports: [FormsModule, RouterLink],
  templateUrl: './quick-add-dialog.component.html',
  styleUrl: './quick-add-dialog.component.scss',
})
export class QuickAddDialogComponent {
  readonly quick = inject(QuickAddService);
  private api = inject(BudgetingService);
  private refresh = inject(FinanceDataRefreshService);
  private locale = inject(LocaleService);
  private toast = inject(ToastService);
  private host = inject(ElementRef<HTMLElement>);

  readonly sameAsDescription = SAME_AS_DESCRIPTION;
  readonly maxRows = MAX_ROWS;
  readonly currencies = this.locale.currencies;

  options = signal<QuickAddOptions>({ groups: [], categories: [], accounts: [] });
  loading = signal(false);
  saving = signal(false);
  /** Rows being typed; edited in place by the inputs. */
  rows: QuickRow[] = [];
  /** Show the "what is missing" messages (after the first save attempt). */
  showErrors = false;
  /** Messages from the server, by row key. */
  serverErrors = new Map<number, string>();

  constructor() {
    effect(() => {
      if (this.quick.isOpen()) untracked(() => this.start());
    });
  }

  private defaults(): QuickRowDefaults {
    return {
      date: this.locale.todayIso(),
      currency: this.locale.defaultCurrency(),
      accountId: defaultAccountId(this.options().accounts),
    };
  }

  /** Fresh screen: one row (prefilled from the widget when it opened us). */
  private start(): void {
    this.showErrors = false;
    this.serverErrors = new Map();
    this.saving.set(false);
    const initial = this.quick.initial() ?? undefined;
    this.rows = [newQuickRow(this.defaults(), null, initial)];
    this.loading.set(true);
    this.quick.options().subscribe((opts) => {
      this.options.set(opts);
      this.loading.set(false);
      // The default account is only known now.
      const acc = defaultAccountId(opts.accounts);
      for (const r of this.rows) {
        if (!r.accountId && !initial?.accountId) r.accountId = acc;
      }
      this.focusAmount(this.rows[0]?.key);
    });
  }

  merchantsFor(groupId: string): BudgetCategory[] {
    return merchantsOf(this.options().categories, groupId);
  }

  setDirection(row: QuickRow, direction: QuickDirection): void {
    row.direction = direction;
    this.serverErrors.delete(row.key);
  }

  onGroupChange(row: QuickRow): void {
    row.merchantId = SAME_AS_DESCRIPTION;
  }

  usesDescription(row: QuickRow): boolean {
    return usesDescriptionAsMerchant(row);
  }

  descriptionLabel(row: QuickRow): string {
    if (row.direction === 'income') return 'What is it';
    return this.usesDescription(row) ? 'Description (merchant)' : 'Description';
  }

  descriptionPlaceholder(row: QuickRow): string {
    if (row.direction === 'income') return 'e.g. Salary';
    return this.usesDescription(row) ? 'e.g. Starbucks' : 'Optional — the merchant name is used';
  }

  descriptionRequired(row: QuickRow): boolean {
    return row.direction === 'income' || this.usesDescription(row);
  }

  addRow(): void {
    if (this.rows.length >= MAX_ROWS) return;
    const row = newQuickRow(this.defaults(), this.rows[this.rows.length - 1]);
    this.rows = [...this.rows, row];
    this.focusAmount(row.key);
  }

  duplicate(index: number): void {
    if (this.rows.length >= MAX_ROWS) return;
    const copy = duplicateQuickRow(this.rows[index]);
    this.rows = [...this.rows.slice(0, index + 1), copy, ...this.rows.slice(index + 1)];
    this.focusAmount(copy.key);
  }

  remove(index: number): void {
    if (this.rows.length <= 1) return;
    this.serverErrors.delete(this.rows[index].key);
    this.rows = this.rows.filter((_, i) => i !== index);
  }

  errorFor(row: QuickRow): string {
    const server = this.serverErrors.get(row.key);
    if (server) return server;
    if (!this.showErrors || !quickRowHasData(row)) return '';
    return quickRowError(row);
  }

  /** Rows with something typed in them; empty rows are ignored when saving. */
  private filledRows(): QuickRow[] {
    return this.rows.filter(quickRowHasData);
  }

  saveLabel(): string {
    const n = this.filledRows().length;
    return n > 1 ? `Save ${n} transactions` : 'Save transaction';
  }

  totalsText(): string {
    return quickTotals(this.rows)
      .map((t) => {
        const kind = t.direction === 'income' ? (t.count === 1 ? 'income' : 'incomes') : t.count === 1 ? 'expense' : 'expenses';
        return `${t.count} ${kind} · ${formatAmount(t.total)} ${t.currency}`;
      })
      .join('   ');
  }

  save(): void {
    if (this.saving()) return;
    this.serverErrors = new Map();
    const toSave = this.filledRows();
    if (!toSave.length) {
      this.toast.error('Enter at least one transaction.');
      this.focusAmount(this.rows[0]?.key);
      return;
    }
    this.showErrors = true;
    const firstBad = toSave.find((r) => quickRowError(r));
    if (firstBad) {
      this.toast.error('Some rows are missing details.');
      this.focusAmount(firstBad.key);
      return;
    }
    const time = this.locale.currentTime();
    this.saving.set(true);
    this.api.createTransactions(toSave.map((r) => toQuickInput(r, time))).subscribe({
      next: (res) => {
        this.saving.set(false);
        this.toast.success(res.created === 1 ? 'Transaction saved.' : `${res.created} transactions saved.`);
        this.refresh.notify();
        this.quick.close();
      },
      error: (err: HttpErrorResponse) => {
        this.saving.set(false);
        const byIndex = quickRowErrorsFromResponse(err?.error);
        if (byIndex.size) {
          byIndex.forEach((msg, i) => {
            if (toSave[i]) this.serverErrors.set(toSave[i].key, msg);
          });
          this.toast.error('Nothing was saved: fix the rows marked in red.');
        } else {
          this.toast.fromHttpError(err, 'Could not save the transactions.');
        }
      },
    });
  }

  /** Closing with typed rows asks first. */
  requestClose(): void {
    if (this.saving()) return;
    if (this.filledRows().length && !confirm('Discard the transactions you entered?')) return;
    this.quick.close();
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.quick.isOpen()) this.requestClose();
  }

  /** Ctrl/⌘ + Enter saves. */
  onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      this.save();
    }
  }

  private focusAmount(key: number | undefined): void {
    if (key == null) return;
    setTimeout(() => {
      const el = (this.host.nativeElement as HTMLElement).querySelector<HTMLInputElement>(`[data-qa-amount="${key}"]`);
      el?.focus();
    });
  }
}
