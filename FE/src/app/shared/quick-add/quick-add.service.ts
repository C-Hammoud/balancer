import { Injectable, inject, signal } from '@angular/core';
import { Observable, catchError, forkJoin, map, of } from 'rxjs';
import { BudgetingService } from '../../core/budgeting.service';
import { Account, BudgetCategory, BudgetGroup } from '../../core/models';
import { QuickRow } from './quick-add.helpers';

/** Lists the quick-add forms choose from. */
export interface QuickAddOptions {
  groups: BudgetGroup[];
  /** Merchants (subcategories). */
  categories: BudgetCategory[];
  /** Active accounts. */
  accounts: Account[];
}

/** Opens the quick-add screen from anywhere (the + button, the dashboard widget). */
@Injectable({ providedIn: 'root' })
export class QuickAddService {
  private api = inject(BudgetingService);

  readonly isOpen = signal(false);
  /** Values for the first row when the screen opens (e.g. the dashboard widget's draft). */
  readonly initial = signal<Partial<QuickRow> | null>(null);

  open(initial?: Partial<QuickRow>): void {
    this.initial.set(initial ?? null);
    this.isOpen.set(true);
  }

  close(): void {
    this.isOpen.set(false);
    this.initial.set(null);
  }

  /** Categories, merchants and active accounts; empty lists when a request fails. */
  options(): Observable<QuickAddOptions> {
    return forkJoin({
      cats: this.api.categories().pipe(catchError(() => of({ groups: [], categories: [] }))),
      accounts: this.api.accounts(true).pipe(catchError(() => of([] as Account[]))),
    }).pipe(
      map(({ cats, accounts }) => ({
        groups: [...cats.groups].sort((a, b) => a.order - b.order || a.name.localeCompare(b.name)),
        categories: cats.categories.filter((c) => c.include_in_reports),
        accounts: accounts.filter((a) => a.is_active),
      }))
    );
  }
}

/** The default expense account, else the first active one ('' when there is none). */
export function defaultAccountId(accounts: Account[]): string {
  return (accounts.find((a) => a.is_default_for_expenses) ?? accounts[0])?.id || '';
}

/** Merchants of a category, sorted like everywhere else. */
export function merchantsOf(categories: BudgetCategory[], groupId: string): BudgetCategory[] {
  if (!groupId) return [];
  return categories
    .filter((c) => c.group_id === groupId)
    .sort((a, b) => a.order - b.order || a.name.localeCompare(b.name));
}
