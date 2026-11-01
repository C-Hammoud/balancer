import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { AdminService } from '../../core/admin.service';
import { AuthService } from '../../core/auth.service';
import { AdminUserAction, AdminUserDetail } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { FLAG_LABEL, TICKET_STATUS_LABEL, shortDate, statusClass } from './labels';

interface ActionDef {
  action: AdminUserAction;
  label: string;
  confirm?: string;
  done: string;
}

@Component({
  selector: 'app-admin-user-detail',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './admin-user-detail.component.html',
  styleUrl: './admin-shared.scss',
})
export class AdminUserDetailComponent implements OnInit {
  private admin = inject(AdminService);
  private auth = inject(AuthService);
  private toast = inject(ToastService);
  private route = inject(ActivatedRoute);

  data = signal<AdminUserDetail | null>(null);
  busy = signal(false);
  id = '';

  me = this.auth.user;
  canChangeRole = computed(() => {
    const d = this.data();
    return !!this.me()?.is_superuser && !!d && d.user.id !== this.me()?.id && !d.user.is_superuser;
  });
  isSelf = computed(() => this.data()?.user.id === this.me()?.id);

  readonly statusClass = statusClass;
  readonly ticketStatus = TICKET_STATUS_LABEL;

  ngOnInit(): void {
    this.id = this.route.snapshot.paramMap.get('id') ?? '';
    this.load();
  }

  load(): void {
    this.admin.user(this.id).subscribe({
      next: (d) => this.data.set(d),
      error: (err) => this.toast.fromHttpError(err, 'Could not load this user.'),
    });
  }

  actions(): ActionDef[] {
    const u = this.data()?.user;
    if (!u) return [];
    const list: ActionDef[] = [];
    if (!u.email_verified) {
      list.push({ action: 'resend-verification', label: 'Resend verification email', done: 'Verification email sent.' });
      list.push({
        action: 'mark-verified',
        label: 'Mark email verified',
        confirm: `Mark ${u.email || u.username} as verified without the user clicking the link?`,
        done: 'Email marked as verified.',
      });
    }
    if (u.has_password && u.email) {
      list.push({
        action: 'send-password-reset',
        label: 'Send password-reset link',
        confirm: `Email a password-reset link to ${u.email}?`,
        done: 'Password-reset link sent.',
      });
    }
    if (!this.isSelf()) {
      list.push(
        u.is_active
          ? {
              action: 'deactivate',
              label: 'Deactivate account',
              confirm: `Deactivate ${u.username}? They are signed out everywhere and cannot sign in until reactivated.`,
              done: 'Account deactivated.',
            }
          : { action: 'reactivate', label: 'Reactivate account', done: 'Account reactivated.' }
      );
    }
    return list;
  }

  run(a: ActionDef): void {
    if (a.confirm && !confirm(a.confirm)) return;
    this.busy.set(true);
    this.admin.userAction(this.id, a.action).subscribe({
      next: (r) => {
        this.busy.set(false);
        if (r.email_sent === false) this.toast.error('Done, but the email could not be sent. Check the email log below.');
        else this.toast.success(a.done);
        this.load();
      },
      error: (err) => {
        this.busy.set(false);
        this.toast.fromHttpError(err, 'The action failed.');
      },
    });
  }

  toggleAdmin(): void {
    const u = this.data()?.user;
    if (!u) return;
    const grant = !u.is_staff;
    const question = grant
      ? `Make ${u.username} a support admin? They will see all users and tickets.`
      : `Remove the admin role from ${u.username}?`;
    if (!confirm(question)) return;
    this.busy.set(true);
    this.admin.setRole(this.id, grant).subscribe({
      next: () => {
        this.busy.set(false);
        this.toast.success(grant ? 'Admin role granted.' : 'Admin role removed.');
        this.load();
      },
      error: (err) => {
        this.busy.set(false);
        this.toast.fromHttpError(err, 'Could not change the role.');
      },
    });
  }

  flagLabel(code: string): string {
    return FLAG_LABEL[code] ?? code;
  }

  date(iso: string | null | undefined): string {
    return shortDate(iso);
  }
}
