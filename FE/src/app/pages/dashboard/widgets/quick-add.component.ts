import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { BudgetingService } from '../../../core/budgeting.service';
import { FinanceDataRefreshService } from '../../../core/finance-data-refresh.service';
import { LocaleService } from '../../../core/locale.service';
import { ToastService } from '../../../core/toast.service';
import { BudgetCategory } from '../../../core/models';
import {
  QuickDirection,
  QuickRow,
  QuickRowDefaults,
  SAME_AS_DESCRIPTION,
  newQuickRow,
  quickRowError,
  quickRowErrorsFromResponse,
  toQuickInput,
  usesDescriptionAsMerchant,
} from '../../../shared/quick-add/quick-add.helpers';
import {
  QuickAddOptions,
  QuickAddService,
  defaultAccountId,
  merchantsOf,
} from '../../../shared/quick-add/quick-add.service';

/** Dashboard widget: add one expense or income right here; "Add several…" opens the full screen. */
@Component({
  selector: 'app-quick-add-widget',
  standalone: true,
  imports: [FormsModule],
  styleUrls: ['./widget.scss', './quick-add.component.scss'],
  templateUrl: './quick-add.component.html',
})
export class QuickAddWidgetComponent implements OnInit {
  private api = inject(BudgetingService);
  private quick = inject(QuickAddService);
  private refresh = inject(FinanceDataRefreshService);
  private locale = inject(LocaleService);
  private toast = inject(ToastService);
  private destroyRef = inject(DestroyRef);

  readonly sameAsDescription = SAME_AS_DESCRIPTION;
  readonly currencies = this.locale.currencies;

  options = signal<QuickAddOptions>({ groups: [], categories: [], accounts: [] });
  saving = signal(false);
  error = signal('');
  row: QuickRow = newQuickRow(this.defaults());

  ngOnInit(): void {
    this.loadOptions(true);
    // New merchants or accounts saved elsewhere show up here too.
    this.refresh.changed$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.loadOptions(false));
  }

  private loadOptions(first: boolean): void {
    this.quick.options().subscribe((opts) => {
      this.options.set(opts);
      if (first && !this.row.accountId) this.row.accountId = defaultAccountId(opts.accounts);
    });
  }

  private defaults(): QuickRowDefaults {
    return {
      date: this.locale.todayIso(),
      currency: this.locale.defaultCurrency(),
      accountId: defaultAccountId(this.options().accounts),
    };
  }

  merchantsFor(groupId: string): BudgetCategory[] {
    return merchantsOf(this.options().categories, groupId);
  }

  setDirection(direction: QuickDirection): void {
    this.row.direction = direction;
    this.error.set('');
  }

  onGroupChange(): void {
    this.row.merchantId = SAME_AS_DESCRIPTION;
  }

  descriptionPlaceholder(): string {
    if (this.row.direction === 'income') return 'What is it? e.g. Salary';
    return usesDescriptionAsMerchant(this.row) ? 'Description / merchant, e.g. Starbucks' : 'Description (optional)';
  }

  add(): void {
    if (this.saving()) return;
    const problem = quickRowError(this.row);
    if (problem) {
      this.error.set(problem);
      return;
    }
    this.error.set('');
    this.saving.set(true);
    this.api.createTransactions([toQuickInput(this.row, this.locale.currentTime())]).subscribe({
      next: () => {
        this.saving.set(false);
        this.toast.success(this.row.direction === 'income' ? 'Income saved.' : 'Expense saved.');
        // Keep type, category, account, currency and date for the next one.
        this.row = { ...this.row, amount: '', description: '', note: '', merchantId: SAME_AS_DESCRIPTION };
        this.refresh.notify();
      },
      error: (err: HttpErrorResponse) => {
        this.saving.set(false);
        const msg = quickRowErrorsFromResponse(err?.error).get(0);
        if (msg) this.error.set(msg);
        else this.toast.fromHttpError(err, 'Could not save the transaction.');
      },
    });
  }

  /** Full screen, starting with what is typed here. */
  addSeveral(): void {
    const { key: _key, ...draft } = this.row;
    this.quick.open(draft);
    this.row = { ...this.row, amount: '', description: '', note: '' };
    this.error.set('');
  }
}
