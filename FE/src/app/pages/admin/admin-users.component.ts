import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { AdminService } from '../../core/admin.service';
import { AdminUserRow, Paged } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { FLAG_LABEL, shortDate } from './labels';

@Component({
  selector: 'app-admin-users',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <section class="hero">
      <div>
        <h1>Users</h1>
        <p>Search by username, email or name. Open a user for their support view and actions.</p>
      </div>
    </section>
    <form class="filters" (ngSubmit)="search(1)">
      <label>Search <input name="q" [(ngModel)]="q" placeholder="name, username or email" /></label>
      <label>
        Status
        <select name="status" [(ngModel)]="status" (ngModelChange)="search(1)">
          <option value="">All</option>
          <option value="active">Active</option>
          <option value="inactive">Deactivated</option>
          <option value="staff">Admins</option>
        </select>
      </label>
      <label>
        Problem
        <select name="flag" [(ngModel)]="flag" (ngModelChange)="search(1)">
          <option value="">Any</option>
          @for (f of flagOptions; track f.code) {
            <option [value]="f.code">{{ f.label }}</option>
          }
        </select>
      </label>
      <button class="btn primary" type="submit">Search</button>
    </form>

    <div class="panel table-wrap">
      <table>
        <thead>
          <tr><th>User</th><th>Signed up</th><th>Last sign-in</th><th>Status</th><th>Problems</th></tr>
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
              <td>{{ date(u.last_login) }}</td>
              <td>
                <span class="pill" [class.ok]="u.is_active" [class.high]="!u.is_active">
                  {{ u.is_active ? 'active' : 'deactivated' }}
                </span>
                <span class="pill" [class.ok]="u.email_verified" [class.warn]="!u.email_verified">
                  {{ u.email_verified ? 'verified' : 'unverified' }}
                </span>
              </td>
              <td>
                @for (f of u.flags; track f.code) {
                  <span [class]="'pill ' + f.severity" [title]="f.text">{{ flagLabel(f.code) }}</span>
                } @empty {
                  <span class="muted">—</span>
                }
              </td>
            </tr>
          } @empty {
            <tr><td colspan="5" class="empty">{{ loading() ? 'Loading…' : 'No users match.' }}</td></tr>
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

  readonly flagOptions = Object.entries(FLAG_LABEL).map(([code, label]) => ({ code, label }));
  q = '';
  status = '';
  flag = '';
  page = signal<Paged<AdminUserRow> | null>(null);
  loading = signal(false);

  ngOnInit(): void {
    const qp = this.route.snapshot.queryParamMap;
    this.q = qp.get('q') ?? '';
    this.status = qp.get('status') ?? '';
    this.flag = qp.get('flag') ?? '';
    this.search(1);
  }

  search(page: number): void {
    this.loading.set(true);
    // Keep the filters in the URL so "back" from a user returns to the same list.
    this.router.navigate([], {
      queryParams: { q: this.q || null, status: this.status || null, flag: this.flag || null },
      replaceUrl: true,
    });
    this.admin.users({ q: this.q, status: this.status, flag: this.flag, page }).subscribe({
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

  open(u: AdminUserRow): void {
    this.router.navigate(['/admin/users', u.id]);
  }

  flagLabel(code: string): string {
    return FLAG_LABEL[code] ?? code;
  }

  date(iso: string | null): string {
    return shortDate(iso);
  }
}
