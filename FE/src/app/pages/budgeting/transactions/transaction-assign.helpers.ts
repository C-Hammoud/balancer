import { Observable, of } from 'rxjs';
import { catchError, map, switchMap } from 'rxjs/operators';
import { BudgetingService } from '../../../core/budgeting.service';
import { BudgetCategory, Transaction } from '../../../core/models';

const UNASSIGNED = 'Unassigned';

/** Pick subcategory using the transaction bank description as the merchant name. */
export const SAME_AS_DESCRIPTION = '__same_as_description__';

export function subcategoryName(categories: BudgetCategory[], id: string | null | undefined): string {
  if (!id) return '';
  return categories.find((c) => c.id === id)?.name || '';
}

export function subcategoriesForGroup(
  categories: BudgetCategory[],
  groupId: string
): BudgetCategory[] {
  if (!groupId) return [];
  return categories
    .filter((c) => c.group_id === groupId)
    .sort((a, b) => a.order - b.order || a.name.localeCompare(b.name));
}

export function isUnassignedExpense(t: Transaction, categories: BudgetCategory[]): boolean {
  if (t.commitment_id || t.direction !== 'expense') return false;
  return !t.category_id || !subcategoryName(categories, t.category_id);
}

export function transactionAccountId(t: Transaction): string {
  return t.account_id || t.income_source_id || '';
}

export function usesSameAsDescription(categoryId: string): boolean {
  return categoryId === SAME_AS_DESCRIPTION;
}

export function merchantNameFromDescription(description: string): string {
  const text = (description || '').trim().replace(/\s+/g, ' ');
  return text.slice(0, 80) || 'Merchant';
}

export function findSubcategoryByName(
  categories: BudgetCategory[],
  groupId: string,
  name: string
): BudgetCategory | undefined {
  const normalized = name.trim().toLowerCase();
  if (!normalized) return undefined;
  return categories.find(
    (c) => c.group_id === groupId && c.name.trim().toLowerCase() === normalized
  );
}

export function preserveDescriptionInNote(
  originalDescription: string,
  merchantName: string,
  existingNote: string
): string {
  const desc = (originalDescription || '').trim();
  const note = (existingNote || '').trim();
  const merchant = (merchantName || '').trim();
  if (!desc || desc === UNASSIGNED) return note;
  if (merchant && desc.toLowerCase() === merchant.toLowerCase()) return note;
  if (!note) return desc;
  if (note.includes(desc)) return note;
  return `${desc} · ${note}`;
}

export function expenseDescriptionAndNote(
  categories: BudgetCategory[],
  subcategoryId: string,
  originalDescription: string,
  existingNote: string
): { description: string; note: string } {
  const merchantName = subcategoryName(categories, subcategoryId) || UNASSIGNED;
  const note = preserveDescriptionInNote(originalDescription, merchantName, existingNote);
  return {
    description: merchantName === UNASSIGNED ? originalDescription || UNASSIGNED : merchantName,
    note,
  };
}

export function expenseFieldsForAssignment(
  categories: BudgetCategory[],
  subcategoryId: string,
  originalDescription: string,
  existingNote: string,
  usedSameAsDescription: boolean
): { description: string; note: string } {
  if (usedSameAsDescription) {
    return {
      description: (originalDescription || '').trim() || UNASSIGNED,
      note: (existingNote || '').trim(),
    };
  }
  return expenseDescriptionAndNote(categories, subcategoryId, originalDescription, existingNote);
}

export function isAssignmentDraftReady(draft: { group_id: string; category_id: string }): boolean {
  return !!(draft.group_id && draft.category_id);
}

export function resolveSubcategoryId(
  api: BudgetingService,
  categories: BudgetCategory[],
  groupId: string,
  categoryId: string,
  description: string,
  onCategoryCreated: (cat: BudgetCategory) => void
): Observable<string> {
  if (!usesSameAsDescription(categoryId)) {
    return of(categoryId);
  }
  const name = merchantNameFromDescription(description);
  const existing = findSubcategoryByName(categories, groupId, name);
  if (existing) {
    return of(existing.id);
  }
  return api
    .createCategory({
      name,
      group_id: groupId,
      include_in_reports: true,
      order: subcategoriesForGroup(categories, groupId).length,
    })
    .pipe(
      map((cat) => {
        onCategoryCreated(cat);
        return cat.id;
      }),
      catchError(() => {
        const afterClash = findSubcategoryByName(categories, groupId, name);
        if (afterClash) return of(afterClash.id);
        throw new Error('Could not create subcategory.');
      })
    );
}

export function applyAssignmentToTransaction(
  api: BudgetingService,
  categories: BudgetCategory[],
  t: Transaction,
  groupId: string,
  categoryId: string,
  onCategoryCreated: (cat: BudgetCategory) => void
): Observable<Transaction> {
  const usedSame = usesSameAsDescription(categoryId);
  return resolveSubcategoryId(
    api,
    categories,
    groupId,
    categoryId,
    t.description || '',
    onCategoryCreated
  ).pipe(
    switchMap((subcategoryId) => {
      const fields = expenseFieldsForAssignment(
        categories,
        subcategoryId,
        t.description || '',
        t.note || '',
        usedSame
      );
      return api.updateTransaction(t.id, {
        description: fields.description,
        note: fields.note,
        category_id: subcategoryId,
      });
    })
  );
}
