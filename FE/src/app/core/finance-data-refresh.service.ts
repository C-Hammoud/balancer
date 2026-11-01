import { Injectable } from '@angular/core';
import { Subject, debounceTime } from 'rxjs';

/** Broadcast when transactions/expenses/alerts change so open pages can reload. */
@Injectable({ providedIn: 'root' })
export class FinanceDataRefreshService {
  private readonly changed = new Subject<void>();

  /** Debounced: a burst of saves (e.g. a bulk action) reloads open pages once. */
  readonly changed$ = this.changed.asObservable().pipe(debounceTime(300));

  notify(): void {
    this.changed.next();
  }
}
