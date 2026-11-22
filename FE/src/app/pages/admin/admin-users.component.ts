import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { AdminService } from '../../core/admin.service';
import { AdminUserFilters, AdminUserPage, AdminUserPool, AdminUserRow } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { FLAG_LABEL, shortDate } from './labels';

const POOLS: { code: AdminUserPool; label: string; hint: string }[] = [
  { code: 'active', label: 'Active', hint: 'Users who can sign in' },
  { code: 'deactivated', label: 'Deactivated', hint: 'Signed out and blocked; can be reactivated' },
  { code: 'staff', label: 'Admins', hint: 'Support admins and superusers' },
  { code: 'attention', label: 'Needs attention', hint: 'Active users with a problem support can fix' },
];

/** Old ?status= links (before pools). */
const STATUS_TO_POOL: Record<string, AdminUserPool> = { active: 'active', inactive: 'deactivated', staff: 'staff' };

type Filters = Required<Omit<AdminUserFilters, 'page' | 'pool'>>;

const EMPTY: Filters = { q: '', flag: '', verified: '', joined_from: '', joined_to: '', last_login: '', sort: '' };

@Component({
  selector: 'app-admin-users',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <section class="hero">
      <div>
        <h1>Users</h1>
        <p>{{ poolHint() }}</p>
      </div>
    </section>

    <nav class="pools" aria-label="User pools">
      @for (p of pools; track p.code) {
        <button type="button" class="pool" [class.active]="pool() === p.code" [ngClass]="'pool-' + p.code"
                [attr.aria-pressed]="pool() === p.code" (click)="setPool(p.code)">
          {{ p.label }}
          <span class="count">{{ page()?.pools?.[p.code] ?? '…' }}</span>
        </button>
      }
    </nav>

    <form class="filters panel" (ngSubmit)="search(1)">
      <label class="grow">Search <input name="q" [(ngModel)]="f.q" placeholder="name, username or email" /></label>
      <label>
        Email
        <select name="verified" [(ngModel)]="f.verified" (ngModelChange)="search(1)">
          <option value="">Any</option>
          <option value="yes">Verified</option>
          <option value="no">Unverified</option>
        </select>
      </label>
      <label>
        Problem
        <select name="flag" [(ngModel)]="f.flag" (ngModelChange)="search(1)">
          <option value="">Any</option>
          @for (o of flagOptions; track o.code) {
            <option [value]="o.code">{{ o.label }}</option>
          }
        </select>
      </label>
      <label>Joined from <input type="date" name="joined_from" [(ngModel)]="f.joined_from" (ngModelChange)="search(1)" /></label>
      <label>to <input type="date" name="joined_to" [(ngModel)]="f.joined_to" (ngModelChange)="search(1)" /></label>
      <label>
        Last sign-in
        <select name="last_login" [(ngModel)]="f.last_login" (ngModelChange)="search(1)">
          <option value="">Any time</option>
          <option value="never">Never</option>
          <option value="30">30+ days ago</option>
          <option value="90">90+ days ago</option>
          <option value="180">180+ days ago</option>
        </select>
      </label>
      <label>
        Sort
        <select name="sort" [(ngModel)]="f.sort" (ngModelChange)="search(1)">
          <option value="">Newest first</option>
          <option value="oldest">Oldest first</option>
          <option value="last_login">Last sign-in</option>
          <option value="username">Username A–Z</option>
        </select>
      </label>
      <div class="filter-actions">
        <button class="btn primary" type="submit">Search</button>
        @if (hasFilters()) {
          <button class="btn ghost" type="button" (click)="clear()">Clear filters</button>
        }
      </div>
    </form>

    <div class="panel table-wrap">
      <table>
        <thead>
          <tr>
            <th>User</th>
            <th>Signed up</th>
            <th>{{ pool() === 'deactivated' ? 'Deactivated' : 'Last sign-in' }}</th>
            <th>Status</th>
            <th>Problems</th>
            @if (pool() === 'deactivated') { <th></th> }
          </tr>
        </thead>
        <tbody>
          @for (u of page()?.results ?? []; track u.id) {
            <tr class="clickable" (click)="open(u)">
              <td>
                <strong>{{ u.username }}</strong>
                @if (u.is_superuser) {
                  <span class="pill">superuser</span>
                } @else if (u.is_staff) {
                  <span class="pill">admin</span>
                }
                <small>{{ u.name || '—' }} · {{ u.email || 'no email' }}</small>
              </td>
              <td>{{ date(u.date_joined) }}</td>
              <td>
                @if (pool() === 'deactivated') {
                  {{ u.deactivated_at ? date(u.deactivated_at) : '—' }}
                  @if (u.deactivated_by) { <small>by {{ u.deactivated_by }}</small> }
                } @else {
                  {{ u.last_login ? date(u.last_login) : 'Never' }}
                }
              </td>
              <td>
                <span class="pill" [class.ok]="u.is_active" [class.high]="!u.is_active">
                  {{ u.is_active ? 'active' : 'deactivated' }}
                </span>
                <span class="pill" [class.ok]="u.email_verified" [class.warn]="!u.email_verified">
                  {{ u.email_verified ? 'verified' : 'unverified' }}
                </span>
              </td>
              <td>
                @for (fl of visibleFlags(u); track fl.code) {
                  <span [class]="'pill ' + fl.severity" [title]="fl.text">{{ flagLabel(fl.code) }}</span>
                } @empty {
                  <span class="muted">—</span>
                }
              </td>
              @if (pool() === 'deactivated') {
                <td class="row-action">
                  <button class="btn ghost" type="button" [disabled]="busyId() === u.id"
                          (click)="reactivate(u, $event)">
                    {{ busyId() === u.id ? 'Reactivating…' : 'Reactivate' }}
                  </button>
                </td>
              }
            </tr>
          } @empty {
            <tr>
              <td [attr.colspan]="pool() === 'deactivated' ? 6 : 5" class="empty">
                {{ loading() ? 'Loading…' : emptyText() }}
              </td>
            </tr>
          }
        </tbody>
      </table>
      @if (page(); as p) {
        <div class="pager">
          <span>{{ p.count }} user(s)</span>
          <button class="btn ghost" type="button" [disabled]="p.page <= 1" (click)="search(p.page - 1)">Previous</button>
          <span>Page {{ p.page }}</span>
          <button class="btn ghost" type="button" [disabled]="p.page * p.page_size >= p.count" (click)="search(p.page + 1)">
            Next
          </button>
        </div>
      }
    </div>
  `,
  styleUrl: './admin-shared.scss',
})
export class AdminUsersComponent implements OnInit {
  private admin = inject(AdminService);
  private toast = inject(ToastService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);

  readonly pools = POOLS;
  readonly flagOptions = Object.entries(FLAG_LABEL)
    .filter(([code]) => code !== 'deactivated') // that is a pool now
    .map(([code, label]) => ({ code, label }));

  pool = signal<AdminUserPool>('active');
  f: Filters = { ...EMPTY };
  page = signal<AdminUserPage | null>(null);
  loading = signal(false);
  busyId = signal<number | null>(null);

  poolHint = computed(() => POOLS.find((p) => p.code === this.pool())?.hint ?? '');

  ngOnInit(): void {
    const qp = this.route.snapshot.queryParamMap;
    const pool = (qp.get('pool') as AdminUserPool | null) ?? STATUS_TO_POOL[qp.get('status') ?? ''] ?? 'active';
    this.pool.set(POOLS.some((p) => p.code === pool) ? pool : 'active');
    for (const key of Object.keys(EMPTY) as (keyof Filters)[]) {
      (this.f as Record<string, string>)[key] = qp.get(key) ?? '';
    }
    this.search(1);
  }

  setPool(pool: AdminUserPool): void {
    if (pool === this.pool()) return;
    this.pool.set(pool);
    this.search(1);
  }

  hasFilters(): boolean {
    return (Object.keys(EMPTY) as (keyof Filters)[]).some((k) => !!this.f[k]);
  }

  clear(): void {
    this.f = { ...EMPTY };
    this.search(1);
  }

  search(page: number): void {
    this.loading.set(true);
    const filters: AdminUserFilters = { ...this.f, pool: this.pool() };
    // Keep the pool and filters in the URL so "back" from a user returns to the same view.
    const queryParams: Record<string, string | null> = {};
    for (const [k, v] of Object.entries(filters)) queryParams[k] = v ? String(v) : null;
    this.router.navigate([], { queryParams, replaceUrl: true });
    this.admin.users({ ...filters, page }).subscribe({
      next: (p) => {
        this.page.set(p);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not load users.');
      },
    });
  }

  reactivate(u: AdminUserRow, event: Event): void {
    event.stopPropagation();
    if (!confirm(`Reactivate ${u.username}? They will be able to sign in again.`)) return;
    this.busyId.set(u.id);
    this.admin.userAction(u.id, 'reactivate').subscribe({
      next: () => {
        this.busyId.set(null);
        this.toast.success(`${u.username} is active again.`);
        this.search(this.page()?.page ?? 1);
      },
      error: (err) => {
        this.busyId.set(null);
        this.toast.fromHttpError(err, 'Could not reactivate this user.');
      },
    });
  }

  open(u: AdminUserRow): void {
    this.router.navigate(['/admin/users', u.id]);
  }

  /** The "deactivated" flag repeats the pool, so it is not shown as a problem. */
  visibleFlags(u: AdminUserRow) {
    return u.flags.filter((fl) => fl.code !== 'deactivated');
  }

  emptyText(): string {
    if (this.hasFilters()) return 'No users match these filters.';
    return this.pool() === 'deactivated'
      ? 'No deactivated users.'
      : this.pool() === 'attention'
        ? 'Nobody needs attention right now.'
        : 'No users here yet.';
  }

  flagLabel(code: string): string {
    return FLAG_LABEL[code] ?? code;
  }

  date(iso: string | null): string {
    return shortDate(iso);
  }
}
