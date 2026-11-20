import { Component, HostListener, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AmountPipe } from '../../../shared/amount.pipe';
import { FormBuilder, ReactiveFormsModule, Validators, FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { Subscription, switchMap } from 'rxjs';
import { BudgetingService } from '../../../core/budgeting.service';
import { FinanceDataRefreshService } from '../../../core/finance-data-refresh.service';
import {
  SAME_AS_DESCRIPTION,
  applyAssignmentToTransaction,
  expenseDescriptionAndNote,
  expenseFieldsForAssignment,
  isAssignmentDraftReady,
  isUnassignedExpense,
  preserveDescriptionInNote,
  resolveSubcategoryId,
  transactionAccountId,
  usesSameAsDescription,
} from './transaction-assign.helpers';
import {
  Account,
  BudgetCategory,
  BudgetGroup,
  Commitment,
  ImportDateFormat,
  PersonalBudget,
  MerchantLink,
  Transaction,
  TransactionBulkChanges,
  TransactionBulkResult,
  TransactionMonth,
  TransactionStatus,
  TransactionImportOptions,
  UnmatchedMerchant,
} from '../../../core/models';
import { ToastService } from '../../../core/toast.service';
import { LocaleService } from '../../../core/locale.service';

interface PendingLink extends UnmatchedMerchant {
  keyword: string;
  category_id: string;
  saved?: boolean;
}

/** What the ticked rows add up to, for one currency. Amounts are in cents to avoid float drift. */
interface SelectionTotal {
  currency: string;
  expenseCount: number;
  expenseCents: number;
  incomeCount: number;
  incomeCents: number;
  transferCount: number;
  transferCents: number;
}

interface AssignmentDraft {
  txnId: string;
  group_id: string;
  category_id: string;
  saving?: boolean;
}

const UNASSIGNED = 'Unassigned';
const IMPORT_PREFS_KEY = 'ft_import_prefs';
const DATE_FORMAT_LABELS: Record<ImportDateFormat, string> = {
  auto: 'Auto-detect',
  dmy: 'Day first (31/12/2026)',
  mdy: 'Month first (12/31/2026)',
  ymd: 'Year first (2026/12/31)',
};
/** Pseudo category values for non-expense transaction types */
const COMMITMENT_CATEGORY = '__commitment__';
const INCOME_CATEGORY = '__income__';
const TRANSFER_CATEGORY = '__transfer__';

@Component({
  selector: 'app-budget-transactions',
  standalone: true,
  imports: [CommonModule, FormsModule, ReactiveFormsModule, RouterLink, AmountPipe],
  templateUrl: './transactions.component.html',
  styleUrl: './transactions.component.scss',
})
export class BudgetTransactionsComponent implements OnInit, OnDestroy {
  private api = inject(BudgetingService);
  private refresh = inject(FinanceDataRefreshService);
  private fb = inject(FormBuilder);
  private toast = inject(ToastService);
  private locale = inject(LocaleService);
  private refreshSub?: Subscription;

  readonly currencyOptions = this.locale.currencies;

  readonly unassigned = UNASSIGNED;
  readonly sameAsDescription = SAME_AS_DESCRIPTION;
  readonly commitmentCategory = COMMITMENT_CATEGORY;
  readonly incomeCategory = INCOME_CATEGORY;
  readonly transferCategory = TRANSFER_CATEGORY;

  now = new Date();
  month = `${this.now.getFullYear()}-${String(this.now.getMonth() + 1).padStart(2, '0')}`;
  items = signal<Transaction[]>([]);
  groups = signal<BudgetGroup[]>([]);
  categories = signal<BudgetCategory[]>([]);
  merchants = signal<MerchantLink[]>([]);
  commitments = signal<Commitment[]>([]);
  accounts = signal<Account[]>([]);
  personalBudgets = signal<PersonalBudget[]>([]);
  loading = signal(true);
  showForm = signal(false);
  uploading = signal(false);
  showImport = signal(false);
  importFile: File | null = null;
  importDateFormat: ImportDateFormat = 'auto';
  importCurrency = '';
  importAccountId = '';
  /** Only for a password-protected PDF; never saved with the import preferences. */
  importPassword = '';
  importPasswordPrompt = signal('');
  readonly dateFormatOptions = (Object.keys(DATE_FORMAT_LABELS) as ImportDateFormat[]).map((code) => ({
    code,
    label: DATE_FORMAT_LABELS[code],
  }));
  editing = signal<Transaction | null>(null);
  saving = signal(false);

  showUnmatchedModal = signal(false);
  showAssignModal = signal(false);
  pendingLinks = signal<PendingLink[]>([]);
  importSummary = signal<{ created: number; skipped: number; matched: number } | null>(null);
  assignmentDrafts = signal<AssignmentDraft[]>([]);
  assigningAll = signal(false);

  /** Rows ticked in the current month's list, acted on together from the bulk bar. */
  selectedIds = signal<ReadonlySet<string>>(new Set());
  bulkBusy = signal(false);
  bulkStatus: '' | TransactionStatus = '';
  bulkAccountId = '';
  bulkGroupId = '';
  bulkMerchantId = '';

  /** Ticked rows added up per currency: expenses, income, transfers, net and average expense. */
  selectionTotals = computed(() => {
    const picked = this.selectedIds();
    const byCurrency = new Map<string, SelectionTotal>();
    for (const t of this.items()) {
      if (!picked.has(t.id)) continue;
      const currency = t.currency || 'USD';
      let row = byCurrency.get(currency);
      if (!row) {
        row = { currency, expenseCount: 0, expenseCents: 0, incomeCount: 0, incomeCents: 0, transferCount: 0, transferCents: 0 };
        byCurrency.set(currency, row);
      }
      const cents = Math.round(Math.abs(Number(t.amount) || 0) * 100);
      if (t.direction === 'income') {
        row.incomeCount += 1;
        row.incomeCents += cents;
      } else if (t.direction === 'transfer') {
        row.transferCount += 1;
        row.transferCents += cents;
      } else {
        row.expenseCount += 1;
        row.expenseCents += cents;
      }
    }
    return [...byCurrency.values()]
      .sort((a, b) => a.currency.localeCompare(b.currency))
      .map((r) => ({
        currency: r.currency,
        expenseCount: r.expenseCount,
        expense: r.expenseCents / 100,
        averageExpense: r.expenseCount ? r.expenseCents / r.expenseCount / 100 : 0,
        incomeCount: r.incomeCount,
        income: r.incomeCents / 100,
        transferCount: r.transferCount,
        transfer: r.transferCents / 100,
        net: (r.incomeCents - r.expenseCents) / 100,
      }));
  });

  /** Months dialog: every month with transactions, some ticked for deletion. */
  showMonths = signal(false);
  months = signal<TransactionMonth[]>([]);
  monthsLoading = signal(false);
  selectedMonths = signal<ReadonlySet<string>>(new Set());

  form = this.fb.nonNullable.group({
    date: ['', Validators.required],
    category_id: ['', Validators.required],
    time: [''],
    merchant: [UNASSIGNED],
    commitment_id: [''],
    amount: ['', Validators.required],
    currency: ['', Validators.required],
    note: [''],
    account_id: ['', Validators.required],
    income_description: [''],
    budget_id: [''],
    /** Transfers: account that receives the money (one-row transfer). */
    to_account_id: [''],
    status: ['settled' as TransactionStatus],
  });

  editForm = this.fb.nonNullable.group({
    date: ['', Validators.required],
    time: [''],
    merchant: [UNASSIGNED, Validators.required],
    amount: ['', Validators.required],
    currency: ['', Validators.required],
    note: [''],
    direction: ['expense', Validators.required],
    category_id: [''],
    account_id: ['', Validators.required],
    income_description: [''],
    budget_id: [''],
    to_account_id: [''],
    status: ['settled' as TransactionStatus],
  });

  ngOnInit(): void {
    this.resetAddForm(false);
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
    this.loadMerchants();
    this.loadAccounts();
    this.loadCommitments();
    this.loadPersonalBudgets();
    this.reload();
    this.refreshSub = this.refresh.changed$.subscribe(() => {
      this.loadCommitments();
      this.reload();
    });
  }

  ngOnDestroy(): void {
    this.refreshSub?.unsubscribe();
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.showImport()) this.closeImport();
    else if (this.showMonths()) this.closeMonths();
    else if (this.showAssignModal()) this.closeAssignModal();
    else if (this.showUnmatchedModal()) this.closeUnmatchedModal();
    else if (this.editing()) this.closeEdit();
  }

  openAssignModal(): void {
    this.syncAssignmentDrafts();
    this.showAssignModal.set(true);
  }

  closeAssignModal(): void {
    this.showAssignModal.set(false);
  }

  loadMerchants(): void {
    this.api.merchantLinks().subscribe({
      next: (rows) => this.merchants.set(rows),
      error: () => this.merchants.set([]),
    });
  }

  loadAccounts(): void {
    this.api.accounts(true).subscribe({
      next: (rows) => {
        this.accounts.set(rows);
        this.applyDefaultExpenseAccountIfNeeded();
      },
      error: () => this.accounts.set([]),
    });
  }

  defaultExpenseAccountId(): string {
    return this.accounts().find((a) => a.is_default_for_expenses && a.is_active)?.id || '';
  }

  private applyDefaultExpenseAccountIfNeeded(): void {
    if (this.form.controls.account_id.value) return;
    if (!this.isExpenseCategory && !this.isCommitment) return;
    const defaultId = this.defaultExpenseAccountId();
    if (defaultId) {
      this.form.patchValue({ account_id: defaultId });
    }
  }

  loadCommitments(): void {
    this.api.commitments().subscribe({
      next: (rows) => this.commitments.set(rows),
      error: () => this.commitments.set([]),
    });
  }

  loadPersonalBudgets(): void {
    this.api.personalBudgets({ sort: 'name' }).subscribe({
      next: (res) => this.personalBudgets.set(res.budgets.filter((b) => b.status !== 'archived')),
      error: () => this.personalBudgets.set([]),
    });
  }

  /** Name of the plan sub-budget with this id (its expenses count only there), else ''. */
  subBudgetName(budgetId: string | null | undefined): string {
    if (!budgetId) return '';
    const b = this.personalBudgets().find((x) => x.id === budgetId);
    return b?.in_plan ? b.name : '';
  }

  payableCommitments(): Commitment[] {
    return this.commitments().filter(
      (c) => !!c.next_due_line_id && c.next_due_amount != null && +c.next_due_amount > 0
    );
  }

  get selectedCategory(): string {
    return this.form.controls.category_id.value;
  }

  get editSelectedGroup(): string {
    return this.editForm.controls.category_id.value;
  }

  get showRestOfForm(): boolean {
    return !!this.selectedCategory;
  }

  get isCommitment(): boolean {
    return this.selectedCategory === COMMITMENT_CATEGORY;
  }

  get isIncome(): boolean {
    return this.selectedCategory === INCOME_CATEGORY;
  }

  get isTransfer(): boolean {
    return this.selectedCategory === TRANSFER_CATEGORY;
  }

  get isExpenseCategory(): boolean {
    const id = this.selectedCategory;
    return !!id && this.groups().some((g) => g.id === id);
  }

  get editIsIncome(): boolean {
    return this.editForm.controls.direction.value === 'income';
  }

  get editIsExpense(): boolean {
    return this.editForm.controls.direction.value === 'expense';
  }

  get formMerchantUnassigned(): boolean {
    const v = this.form.controls.merchant.value;
    return !v || v === UNASSIGNED;
  }

  get formUsesSameAsDescription(): boolean {
    return usesSameAsDescription(this.form.controls.merchant.value);
  }

  get editMerchantUnassigned(): boolean {
    const v = this.editForm.controls.merchant.value;
    return !v || v === UNASSIGNED;
  }

  get editUsesSameAsDescription(): boolean {
    return usesSameAsDescription(this.editForm.controls.merchant.value);
  }

  subcategoriesForGroup(groupId: string): BudgetCategory[] {
    if (!groupId) return [];
    return this.categories()
      .filter((c) => c.group_id === groupId)
      .sort((a, b) => a.order - b.order || a.name.localeCompare(b.name));
  }

  subcategoryName(id: string | null | undefined): string {
    if (!id) return '';
    return this.categories().find((c) => c.id === id)?.name || '';
  }

  groupName(id: string | null | undefined): string {
    if (!id) return '';
    return this.groups().find((g) => g.id === id)?.name || '';
  }

  groupNameForSubcategory(subcategoryId: string | null | undefined): string {
    if (!subcategoryId) return '—';
    const sub = this.categories().find((c) => c.id === subcategoryId);
    if (!sub?.group_id) return '—';
    return this.groupName(sub.group_id) || sub.group_name || '—';
  }

  currentTime(): string {
    return this.locale.currentTime();
  }

  toggleAddForm(): void {
    const opening = !this.showForm();
    this.showForm.set(opening);
    if (opening) {
      this.form.patchValue({ currency: this.locale.defaultCurrency() });
    }
  }

  accountName(id: string): string {
    if (!id) return '';
    const fromId = this.accounts().find((s) => s.id === id)?.name;
    if (fromId) return fromId;
    return '';
  }

  transactionAccountId(t: Transaction): string {
    return t.account_id || t.income_source_id || '';
  }

  transactionAccountLabel(t: Transaction): string {
    const id = this.transactionAccountId(t);
    if (id) return this.accountName(id) || t.source_account || '—';
    return t.source_account || '—';
  }

  onCategoryChange(): void {
    let accountId = this.form.controls.account_id.value;
    if ((this.isExpenseCategory || this.isCommitment) && !accountId) {
      accountId = this.defaultExpenseAccountId();
    }
    this.form.patchValue({
      commitment_id: '',
      account_id: accountId,
      income_description: '',
      amount: '',
      merchant: UNASSIGNED,
      note: '',
      time: this.currentTime(),
    });
    if (this.isCommitment) {
      this.form.controls.commitment_id.setValidators([Validators.required]);
      this.form.controls.merchant.clearValidators();
      this.form.controls.income_description.clearValidators();
    } else if (this.isExpenseCategory) {
      this.form.controls.commitment_id.clearValidators();
      this.form.controls.income_description.clearValidators();
      this.form.controls.merchant.clearValidators();
    } else if (this.isIncome) {
      this.form.controls.commitment_id.clearValidators();
      this.form.controls.merchant.clearValidators();
      this.form.controls.income_description.setValidators([Validators.required]);
    } else {
      this.form.controls.commitment_id.clearValidators();
      this.form.controls.income_description.clearValidators();
      this.form.controls.merchant.clearValidators();
    }
    this.form.controls.commitment_id.updateValueAndValidity();
    this.form.controls.income_description.updateValueAndValidity();
    this.form.controls.merchant.updateValueAndValidity();
    this.syncAddFormNoteValidator();
  }

  onFormMerchantChange(): void {
    this.syncAddFormNoteValidator();
  }

  private syncAddFormNoteValidator(): void {
    if (this.isExpenseCategory && this.formMerchantUnassigned) {
      this.form.controls.note.setValidators([Validators.required]);
    } else {
      this.form.controls.note.clearValidators();
    }
    this.form.controls.note.updateValueAndValidity();
  }

  onEditGroupChange(): void {
    this.editForm.patchValue({ merchant: UNASSIGNED });
  }

  onEditMerchantChange(): void {
    const current = this.editing();
    if (!current || current.direction !== 'expense') return;
    const merchantId = this.editForm.controls.merchant.value;
    if (!merchantId || merchantId === UNASSIGNED) return;
    const merchantName = this.descriptionFromSubcategory(merchantId);
    const currentNote = (this.editForm.controls.note.value || '').trim();
    const originalDesc = (current.description || '').trim();
    const newNote = preserveDescriptionInNote(originalDesc, merchantName, currentNote);
    if (newNote !== currentNote) {
      this.editForm.patchValue({ note: newNote });
    }
  }

  onCommitmentChange(): void {
    const id = this.form.controls.commitment_id.value;
    const c = this.commitments().find((x) => x.id === id);
    if (!c) return;
    this.form.patchValue({
      amount: c.next_due_amount != null ? String(c.next_due_amount) : '',
      date: c.next_due_date || this.form.controls.date.value,
      currency: c.currency || this.locale.defaultCurrency(),
      note: `Commitment payment — ${c.name}`,
    });
  }

  isUnassigned(t: Transaction): boolean {
    if (t.commitment_id) return false;
    if (t.direction === 'income') {
      return !(t.description || '').trim();
    }
    return isUnassignedExpense(t, this.categories());
  }

  unassignedCount(): number {
    return this.unassignedTransactions().length;
  }

  unassignedTransactions(): Transaction[] {
    return this.items().filter((t) => this.isUnassigned(t) && t.direction === 'expense');
  }

  transactionById(id: string): Transaction | undefined {
    return this.items().find((t) => t.id === id);
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
        if (!this.unassignedCount()) this.closeAssignModal();
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
      if (!this.unassignedCount()) this.closeAssignModal();
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

  merchantFromTransaction(t: Transaction): string {
    if (t.category_id && this.subcategoryName(t.category_id)) {
      return t.category_id;
    }
    return UNASSIGNED;
  }

  descriptionFromSubcategory(subcategoryId: string): string {
    if (!subcategoryId || subcategoryId === UNASSIGNED) return UNASSIGNED;
    return this.subcategoryName(subcategoryId) || UNASSIGNED;
  }

  reload(): void {
    this.loading.set(true);
    this.api.transactions(this.month || undefined).subscribe({
      next: (rows) => {
        this.items.set(rows);
        this.loading.set(false);
        this.syncAssignmentDrafts();
        // Keep only ticks on rows that are still listed (another month clears them).
        const listed = new Set(rows.map((t) => t.id));
        this.selectedIds.update((s) => new Set([...s].filter((id) => listed.has(id))));
      },
      error: (err) => {
        this.items.set([]);
        this.selectedIds.set(new Set());
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not load transactions.');
      },
    });
  }

  sourceLabel(t: Transaction): string {
    if (t.commitment_id) {
      const c = this.commitments().find((x) => x.id === t.commitment_id);
      return c ? `Commitment: ${c.name}` : 'Commitment payment';
    }
    if (t.direction === 'income') {
      return 'Income';
    }
    if (t.direction === 'transfer') {
      return 'Transfer';
    }
    return this.groupNameForSubcategory(t.category_id);
  }

  merchantLabel(t: Transaction): string {
    if (t.direction === 'income') {
      return t.description || this.unassigned;
    }
    const merchant = this.subcategoryName(t.category_id);
    if (merchant) return merchant;
    return t.description || this.unassigned;
  }

  submit(): void {
    if (!this.selectedCategory) {
      this.toast.error('Select a category first.');
      return;
    }
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.toast.error('Please fill in the required fields.');
      return;
    }
    const raw = this.form.getRawValue();
    const note = (raw.note || '').trim();

    if (this.isCommitment) {
      const c = this.commitments().find((x) => x.id === raw.commitment_id);
      if (!c?.next_due_line_id) {
        this.toast.error('Select a commitment with an outstanding payment.');
        return;
      }
      if (!raw.account_id) {
        this.toast.error('Select an account.');
        return;
      }
      this.api
        .createTransaction({
          date: raw.date,
          time: raw.time || '',
          description: c.name,
          amount: raw.amount || c.next_due_amount,
          currency: raw.currency || c.currency || this.locale.defaultCurrency(),
          note,
          direction: 'expense',
          category_id: null,
          commitment_id: c.id,
          schedule_line_id: c.next_due_line_id,
          account_id: raw.account_id,
          classification: null,
        })
        .subscribe({
          next: () => {
            this.toast.success('Commitment payment recorded and installment marked paid.');
            this.resetAddForm();
            this.loadCommitments();
            this.reload();
          },
          error: (err) => this.toast.fromHttpError(err, 'Could not record commitment payment.'),
        });
      return;
    }

    if (!raw.account_id) {
      this.toast.error('Select an account.');
      return;
    }
    if (this.isTransfer && !raw.to_account_id) {
      this.toast.error('Select the account the money goes to.');
      return;
    }
    if (this.isTransfer && raw.to_account_id === raw.account_id) {
      this.toast.error('Choose two different accounts.');
      return;
    }

    const direction = this.isIncome ? 'income' : this.isTransfer ? 'transfer' : 'expense';
    const merchantSelected =
      this.isExpenseCategory && raw.merchant && raw.merchant !== UNASSIGNED;
    const subcategoryId = merchantSelected ? raw.merchant : null;

    if (this.isExpenseCategory && !merchantSelected && !note) {
      this.toast.error('Enter a note describing this expense when no merchant is selected.');
      return;
    }
    const incomeDescription = (raw.income_description || '').trim();

    if (this.isIncome && !incomeDescription) {
      this.toast.error('Enter what this income is (e.g. Salary).');
      return;
    }

    this.api
      .createTransaction({
        date: raw.date,
        time: raw.time || '',
        description: this.isExpenseCategory
          ? merchantSelected
            ? this.descriptionFromSubcategory(subcategoryId!)
            : note
          : this.isIncome
            ? incomeDescription
            : `Transfer to ${this.accountName(raw.to_account_id) || 'account'}`,
        amount: raw.amount,
        currency: raw.currency || 'USD',
        note: merchantSelected || this.isTransfer ? note : '',
        direction,
        category_id: subcategoryId,
        account_id: raw.account_id,
        to_account_id: this.isTransfer ? raw.to_account_id : undefined,
        status: raw.status || 'settled',
        classification: null,
        budget_id: this.isExpenseCategory ? raw.budget_id || undefined : undefined,
      })
      .subscribe({
        next: () => {
          this.toast.success('Transaction saved successfully.');
          this.resetAddForm();
          this.reload();
        },
        error: (err) => this.toast.fromHttpError(err, 'Could not add transaction.'),
      });
  }

  resetAddForm(hide = true): void {
    if (hide) this.showForm.set(false);
    this.form.reset({
      date: this.locale.todayIso(),
      category_id: '',
      time: this.currentTime(),
      merchant: UNASSIGNED,
      commitment_id: '',
      amount: '',
      currency: this.locale.defaultCurrency(),
      note: '',
      account_id: '',
      income_description: '',
      budget_id: '',
      to_account_id: '',
      status: 'settled',
    });
    this.form.controls.commitment_id.clearValidators();
    this.form.controls.merchant.clearValidators();
    this.form.controls.income_description.clearValidators();
    this.form.controls.commitment_id.updateValueAndValidity();
    this.form.controls.merchant.updateValueAndValidity();
    this.form.controls.note.clearValidators();
    this.form.controls.note.updateValueAndValidity();
  }

  openEdit(t: Transaction): void {
    this.editing.set(t);
    const sub = t.category_id ? this.categories().find((c) => c.id === t.category_id) : undefined;
    const merchantId = this.merchantFromTransaction(t);
    let note = t.note || '';
    if (t.direction === 'expense' && merchantId !== UNASSIGNED) {
      note = preserveDescriptionInNote(
        t.description || '',
        this.descriptionFromSubcategory(merchantId),
        note
      );
    }
    this.editForm.reset({
      date: t.date,
      time: (t.time || '').slice(0, 5) || this.currentTime(),
      merchant: merchantId,
      amount: t.amount,
      currency: t.currency || 'USD',
      note,
      direction: t.direction || 'expense',
      category_id: sub?.group_id || '',
      account_id: this.transactionAccountId(t),
      income_description: t.direction === 'income' ? t.description || '' : '',
      budget_id: t.budget_id || '',
      to_account_id: t.to_account_id || '',
      status: t.status || 'settled',
    });
    this.syncEditValidators(t.direction || 'expense');
  }

  onEditDirectionChange(): void {
    this.syncEditValidators(this.editForm.controls.direction.value);
  }

  private syncEditValidators(direction: string): void {
    if (direction === 'income') {
      this.editForm.controls.merchant.clearValidators();
      this.editForm.controls.income_description.setValidators([Validators.required]);
      this.editForm.controls.category_id.clearValidators();
    } else if (direction === 'expense') {
      this.editForm.controls.income_description.clearValidators();
      this.editForm.controls.merchant.setValidators([Validators.required]);
    } else {
      this.editForm.controls.income_description.clearValidators();
      this.editForm.controls.merchant.clearValidators();
    }
    this.editForm.controls.merchant.updateValueAndValidity();
    this.editForm.controls.income_description.updateValueAndValidity();
  }

  closeEdit(): void {
    this.editing.set(null);
  }

  saveEdit(): void {
    const current = this.editing();
    if (!current) return;
    if (this.editForm.invalid) {
      this.editForm.markAllAsTouched();
      this.toast.error('Please fill in the required fields.');
      return;
    }
    const raw = this.editForm.getRawValue();
    const isIncome = raw.direction === 'income';
    const isExpense = raw.direction === 'expense';
    const incomeDescription = (raw.income_description || '').trim();
    if (!raw.account_id) {
      this.toast.error('Select an account.');
      return;
    }
    if (isIncome && !incomeDescription) {
      this.toast.error('Enter what this income is (e.g. Salary).');
      return;
    }
    if (isExpense && (!raw.merchant || raw.merchant === UNASSIGNED)) {
      this.toast.error('Select a merchant (subcategory).');
      return;
    }
    if (isExpense && usesSameAsDescription(raw.merchant) && !raw.category_id) {
      this.toast.error('Select a parent category first.');
      return;
    }
    const isTransfer = raw.direction === 'transfer';
    if (isTransfer && raw.to_account_id && raw.to_account_id === raw.account_id) {
      this.toast.error('Choose two different accounts.');
      return;
    }

    this.saving.set(true);

    const finishEdit = () => {
      this.saving.set(false);
      this.toast.success('Transaction updated.');
      this.closeEdit();
      this.reload();
    };

    if (isExpense && usesSameAsDescription(raw.merchant)) {
      resolveSubcategoryId(
        this.api,
        this.categories(),
        raw.category_id,
        raw.merchant,
        current.description || '',
        (cat) => this.addCreatedCategory(cat)
      )
        .pipe(
          switchMap((subcategoryId) => {
            const fields = expenseFieldsForAssignment(
              this.categories(),
              subcategoryId,
              current.description || '',
              raw.note || '',
              true
            );
            return this.api.updateTransaction(current.id, {
              date: raw.date,
              time: raw.time || '',
              description: fields.description,
              amount: raw.amount,
              currency: raw.currency || 'USD',
              note: fields.note,
              direction: raw.direction,
              category_id: subcategoryId,
              account_id: raw.account_id,
              status: raw.status,
              classification: null,
              budget_id: raw.budget_id || undefined,
            });
          })
        )
        .subscribe({
          next: () => finishEdit(),
          error: (err) => {
            this.saving.set(false);
            this.toast.fromHttpError(err, 'Could not update transaction.');
          },
        });
      return;
    }

    const expenseFields =
      isExpense && raw.merchant && raw.merchant !== UNASSIGNED
        ? expenseDescriptionAndNote(
            this.categories(),
            raw.merchant,
            current.description || '',
            raw.note || ''
          )
        : null;
    this.api
      .updateTransaction(current.id, {
        date: raw.date,
        time: raw.time || '',
        description: isIncome
          ? incomeDescription
          : isExpense
            ? expenseFields!.description
            : current.description || 'Transfer',
        amount: raw.amount,
        currency: raw.currency || 'USD',
        note: isExpense && expenseFields ? expenseFields.note : (raw.note || '').trim(),
        direction: raw.direction,
        category_id: isExpense ? raw.merchant || null : null,
        account_id: raw.account_id,
        to_account_id: isTransfer ? raw.to_account_id : '',
        status: raw.status,
        classification: null,
        budget_id: isExpense ? raw.budget_id || undefined : undefined,
      })
      .subscribe({
        next: () => {
          this.saving.set(false);
          this.toast.success('Transaction updated.');
          this.closeEdit();
          this.reload();
        },
        error: (err) => {
          this.saving.set(false);
          this.toast.fromHttpError(err, 'Could not update transaction.');
        },
      });
  }

  remove(id: string): void {
    if (!confirm('Delete this transaction?')) return;
    this.api.deleteTransaction(id).subscribe({
      next: () => {
        this.toast.success('Transaction deleted.');
        this.reload();
      },
      error: (err) => this.toast.fromHttpError(err, 'Delete failed.'),
    });
  }

  // ---- Selection and bulk actions ----

  isSelected(id: string): boolean {
    return this.selectedIds().has(id);
  }

  selectedCount(): number {
    return this.selectedIds().size;
  }

  allSelected(): boolean {
    const rows = this.items();
    return rows.length > 0 && rows.every((t) => this.selectedIds().has(t.id));
  }

  someSelected(): boolean {
    return this.selectedCount() > 0 && !this.allSelected();
  }

  toggleSelected(id: string): void {
    this.selectedIds.update((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  /** Header tick box: the whole month, or nothing. */
  toggleSelectAll(): void {
    this.selectedIds.set(this.allSelected() ? new Set() : new Set(this.items().map((t) => t.id)));
  }

  clearSelection(): void {
    this.selectedIds.set(new Set());
    this.bulkStatus = '';
    this.bulkAccountId = '';
    this.bulkGroupId = '';
    this.bulkMerchantId = '';
  }

  /** Picking a category defaults to keeping each row's own merchant name under it. */
  onBulkGroupChange(): void {
    this.bulkMerchantId = this.bulkGroupId ? SAME_AS_DESCRIPTION : '';
  }

  /** Category chosen with "keep each merchant's name": every row goes to its own subcategory. */
  get bulkKeepsMerchantNames(): boolean {
    return !!this.bulkGroupId && usesSameAsDescription(this.bulkMerchantId);
  }

  bulkChanges(): TransactionBulkChanges {
    const changes: TransactionBulkChanges = {};
    if (this.bulkStatus) changes.status = this.bulkStatus;
    if (this.bulkAccountId) changes.account_id = this.bulkAccountId;
    if (this.bulkMerchantId && !usesSameAsDescription(this.bulkMerchantId)) changes.category_id = this.bulkMerchantId;
    return changes;
  }

  hasBulkChanges(): boolean {
    return this.bulkKeepsMerchantNames || Object.keys(this.bulkChanges()).length > 0;
  }

  applyBulkChanges(): void {
    const ids = [...this.selectedIds()];
    const changes = this.bulkChanges();
    if (!ids.length || !this.hasBulkChanges()) return;
    if (this.bulkKeepsMerchantNames) {
      this.applyBulkCategoryKeepingNames(ids, changes);
      return;
    }
    this.bulkBusy.set(true);
    this.api.bulkUpdateTransactions(ids, changes).subscribe({
      next: (r) => {
        this.bulkBusy.set(false);
        this.toast.success(this.bulkMessage(r, 'Updated'));
        this.clearSelection();
        this.reload();
      },
      error: (err) => {
        this.bulkBusy.set(false);
        this.toast.fromHttpError(err, 'Could not update the selected transactions.');
      },
    });
  }

  /**
   * Move the selected expenses under one category while each keeps its own merchant name.
   * One API call: the server finds or creates each merchant under the category and updates
   * every row, applying the status/account changes too.
   */
  private applyBulkCategoryKeepingNames(ids: string[], changes: TransactionBulkChanges): void {
    const { status, account_id } = changes;
    const extra: Pick<TransactionBulkChanges, 'status' | 'account_id'> = {};
    if (status) extra.status = status;
    if (account_id) extra.account_id = account_id;

    this.bulkBusy.set(true);
    this.api.bulkCategorizeTransactions(ids, this.bulkGroupId, extra).subscribe({
      next: (r) => {
        this.bulkBusy.set(false);
        r.created_categories.forEach((cat) => this.addCreatedCategory(cat));
        let msg = this.bulkMessage(r, 'Updated');
        if (r.created_categories.length) msg += ` Added ${r.created_categories.length} new merchant(s).`;
        if (r.no_description) msg += ` ${r.no_description} had no description, so their merchant was not changed.`;
        this.toast.success(msg);
        this.clearSelection();
        this.reload();
      },
      error: (err) => {
        this.bulkBusy.set(false);
        this.toast.fromHttpError(err, 'Could not update the selected transactions.');
      },
    });
  }

  deleteSelected(): void {
    const ids = [...this.selectedIds()];
    if (!ids.length) return;
    const what = this.allSelected() ? `all ${ids.length} transaction(s) of ${this.monthLabel(this.month)}` : `${ids.length} transaction(s)`;
    if (!confirm(`Delete ${what}? This cannot be undone.`)) return;
    this.bulkBusy.set(true);
    this.api.bulkDeleteTransactions(ids).subscribe({
      next: (r) => {
        this.bulkBusy.set(false);
        this.toast.success(this.bulkMessage(r, 'Deleted'));
        this.clearSelection();
        this.loadCommitments(); // deleted installment payments are outstanding again
        this.reload();
      },
      error: (err) => {
        this.bulkBusy.set(false);
        this.toast.fromHttpError(err, 'Could not delete the selected transactions.');
      },
    });
  }

  private bulkMessage(r: TransactionBulkResult, verb: 'Updated' | 'Deleted'): string {
    const n = verb === 'Deleted' ? r.deleted ?? 0 : r.updated ?? 0;
    let msg = `${verb} ${n} transaction(s).`;
    if (r.skipped) msg += ` ${r.skipped} already matched or did not apply (a merchant applies to expenses only).`;
    if (r.missing) msg += ` ${r.missing} no longer exist.`;
    return msg;
  }

  // ---- Months list ----

  monthLabel(month: string): string {
    const [y, m] = (month || '').split('-').map(Number);
    if (!y || !m) return month;
    return new Date(y, m - 1, 1).toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
  }

  openMonths(): void {
    this.selectedMonths.set(new Set());
    this.showMonths.set(true);
    this.loadMonths();
  }

  closeMonths(): void {
    if (this.bulkBusy()) return;
    this.showMonths.set(false);
  }

  loadMonths(): void {
    this.monthsLoading.set(true);
    this.api.transactionMonths().subscribe({
      next: (rows) => {
        this.months.set(rows);
        this.monthsLoading.set(false);
        const listed = new Set(rows.map((r) => r.month));
        this.selectedMonths.update((s) => new Set([...s].filter((m) => listed.has(m))));
      },
      error: (err) => {
        this.months.set([]);
        this.monthsLoading.set(false);
        this.toast.fromHttpError(err, 'Could not load the months.');
      },
    });
  }

  /** Show one month in the list and close the dialog. */
  openMonth(month: string): void {
    this.month = month;
    this.showMonths.set(false);
    this.clearSelection();
    this.reload();
  }

  isMonthSelected(month: string): boolean {
    return this.selectedMonths().has(month);
  }

  toggleMonth(month: string): void {
    this.selectedMonths.update((s) => {
      const next = new Set(s);
      if (next.has(month)) next.delete(month);
      else next.add(month);
      return next;
    });
  }

  allMonthsSelected(): boolean {
    const rows = this.months();
    return rows.length > 0 && rows.every((r) => this.selectedMonths().has(r.month));
  }

  toggleAllMonths(): void {
    this.selectedMonths.set(this.allMonthsSelected() ? new Set() : new Set(this.months().map((r) => r.month)));
  }

  selectedMonthsTxnCount(): number {
    const picked = this.selectedMonths();
    return this.months().reduce((n, r) => n + (picked.has(r.month) ? r.count : 0), 0);
  }

  deleteSelectedMonths(): void {
    const months = [...this.selectedMonths()].sort();
    if (!months.length) return;
    const names = months.map((m) => this.monthLabel(m)).join(', ');
    const count = this.selectedMonthsTxnCount();
    if (!confirm(`Delete all ${count} transaction(s) in ${months.length} month(s): ${names}? This cannot be undone.`)) {
      return;
    }
    this.bulkBusy.set(true);
    this.api.deleteTransactionMonths(months).subscribe({
      next: (r) => {
        this.bulkBusy.set(false);
        this.toast.success(`Deleted ${r.deleted} transaction(s) in ${r.months.length} month(s).`);
        this.selectedMonths.set(new Set());
        this.clearSelection();
        this.loadMonths();
        this.loadCommitments();
        this.reload();
      },
      error: (err) => {
        this.bulkBusy.set(false);
        this.toast.fromHttpError(err, 'Could not delete those months.');
      },
    });
  }

  // ---- Statement import ----

  openImport(): void {
    const saved = this.loadImportPrefs();
    this.importDateFormat = saved.dateFormat || 'auto';
    this.importCurrency = saved.currency || this.locale.defaultCurrency();
    const accountIds = new Set(this.accounts().map((a) => a.id));
    this.importAccountId =
      saved.accountId && accountIds.has(saved.accountId) ? saved.accountId : this.defaultExpenseAccountId();
    this.importFile = null;
    this.resetImportPassword();
    this.showImport.set(true);
  }

  closeImport(): void {
    if (this.uploading()) return;
    this.showImport.set(false);
    this.resetImportPassword();
  }

  onImportFile(event: Event): void {
    this.importFile = (event.target as HTMLInputElement).files?.[0] ?? null;
    this.resetImportPassword();
  }

  private resetImportPassword(): void {
    this.importPassword = '';
    this.importPasswordPrompt.set('');
  }

  private loadImportPrefs(): TransactionImportOptions {
    try {
      return JSON.parse(localStorage.getItem(IMPORT_PREFS_KEY) || '{}') as TransactionImportOptions;
    } catch {
      return {};
    }
  }

  private saveImportPrefs(opts: TransactionImportOptions): void {
    try {
      localStorage.setItem(IMPORT_PREFS_KEY, JSON.stringify(opts));
    } catch {
      /* storage unavailable: the choice just is not remembered */
    }
  }

  runImport(): void {
    const file = this.importFile;
    if (!file) {
      this.toast.error('Choose a .csv, .xlsx, .json or .pdf file.');
      return;
    }
    const opts: TransactionImportOptions = {
      dateFormat: this.importDateFormat,
      currency: this.importCurrency,
      accountId: this.importAccountId || undefined,
    };
    this.saveImportPrefs(opts);
    this.uploading.set(true);
    this.api.uploadTransactions(file, opts, this.importPassword).subscribe({
      next: (r) => {
        this.uploading.set(false);
        this.showImport.set(false);
        this.resetImportPassword();
        const fmt = r.date_format ? ' Dates read as ' + DATE_FORMAT_LABELS[r.date_format] + '.' : '';
        this.toast.success(
          'Imported ' + r.created + ' (matched ' + r.matched + ' merchants), skipped ' + r.skipped + '.' + fmt
        );
        if (r.uncertain_direction) {
          this.toast.info(
            r.uncertain_direction +
              ' transaction(s) did not say whether money came in or went out and were saved as expenses. Check them in the list.',
            8000
          );
        }
        if (r.errors?.length) {
          const first = r.errors[0];
          this.toast.error(r.errors.length + ' row(s) could not be read. First: row ' + first.row + ' (' + first.error + ')');
        }
        this.loadMerchants();
        this.reload();
        if (r.unmatched?.length) {
          this.importSummary.set({
            created: r.created,
            skipped: r.skipped,
            matched: r.matched,
          });
          this.pendingLinks.set(
            r.unmatched.map((u) => ({
              ...u,
              keyword: u.keyword_suggestion || u.merchant,
              category_id: '',
              saved: false,
            }))
          );
          this.showUnmatchedModal.set(true);
        }
      },
      error: (err) => {
        this.uploading.set(false);
        const body = (err as { error?: { code?: string; detail?: string } })?.error;
        if (body?.code === 'password_required' || body?.code === 'password_incorrect') {
          // Keep the dialog open and ask for the PDF's password.
          this.importPassword = '';
          this.importPasswordPrompt.set(body.detail || 'Enter the PDF password.');
          return;
        }
        this.toast.fromHttpError(err, 'Import failed.');
      },
    });
  }

  closeUnmatchedModal(): void {
    this.showUnmatchedModal.set(false);
  }

  remainingUnmatched(): PendingLink[] {
    return this.pendingLinks().filter((p) => !p.saved);
  }

  updatePending(index: number, patch: Partial<PendingLink>): void {
    this.pendingLinks.update((list) =>
      list.map((row, i) => (i === index ? { ...row, ...patch } : row))
    );
  }

  saveLink(index: number): void {
    const row = this.pendingLinks()[index];
    if (!row || row.saved) return;
    const keyword = (row.keyword || '').trim();
    if (!keyword || !row.category_id) {
      this.toast.error('Enter a keyword and pick a subcategory.');
      return;
    }
    this.api
      .createMerchantLink(keyword, row.category_id, {
        transaction_ids: row.transaction_ids,
        apply_unmatched: true,
      })
      .subscribe({
        next: (res) => {
          this.toast.success(
            `Linked “${keyword}”` +
              (res.transactions_updated ? ` · updated ${res.transactions_updated} txn(s)` : '')
          );
          this.updatePending(index, { saved: true, keyword });
          this.loadMerchants();
          this.reload();
          if (!this.remainingUnmatched().length) {
            this.showUnmatchedModal.set(false);
            this.toast.success('All unmatched merchants are linked.');
          }
        },
        error: (err) => this.toast.fromHttpError(err, 'Could not save merchant link.'),
      });
  }

  saveAllReady(): void {
    const ready = this.pendingLinks()
      .map((row, index) => ({ row, index }))
      .filter(({ row }) => !row.saved && row.keyword.trim() && row.category_id);
    if (!ready.length) {
      this.toast.error('Fill keyword and subcategory for at least one merchant.');
      return;
    }
    let done = 0;
    for (const { row, index } of ready) {
      this.api
        .createMerchantLink(row.keyword.trim(), row.category_id, {
          transaction_ids: row.transaction_ids,
          apply_unmatched: true,
        })
        .subscribe({
          next: () => {
            this.updatePending(index, { saved: true });
            done += 1;
            if (done === ready.length) {
              this.loadMerchants();
              this.reload();
              this.toast.success(`Saved ${done} merchant link(s).`);
              if (!this.remainingUnmatched().length) {
                this.showUnmatchedModal.set(false);
              }
            }
          },
          error: (err) => this.toast.fromHttpError(err, 'Could not save merchant link.'),
        });
    }
  }
}
