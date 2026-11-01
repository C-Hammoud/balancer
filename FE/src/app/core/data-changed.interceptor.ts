import { HttpInterceptorFn, HttpResponse } from '@angular/common/http';
import { inject } from '@angular/core';
import { tap } from 'rxjs';
import { FinanceDataRefreshService } from './finance-data-refresh.service';

const MUTATING = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);
/** Saves that do not change financial data (sign-in, profile reads, notification read flags). */
const IGNORED = ['/auth/', '/notifications/', '/personal-budgets/users/lookup'];

/**
 * After any successful save (transaction, account, commitment, budget, planned item, settings…)
 * tell open pages to reload, so the dashboard, risk score, balances and alert badge stay in sync
 * without each page having to remember to announce its changes.
 */
export const dataChangedInterceptor: HttpInterceptorFn = (req, next) => {
  const refresh = inject(FinanceDataRefreshService);
  const watch = MUTATING.has(req.method) && req.url.includes('/api/') && !IGNORED.some((p) => req.url.includes(p));
  return next(req).pipe(
    tap((event) => {
      if (watch && event instanceof HttpResponse && event.ok) refresh.notify();
    })
  );
};
