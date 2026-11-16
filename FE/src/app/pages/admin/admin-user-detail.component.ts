import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { AdminService } from '../../core/admin.service';
import { AuthService } from '../../core/auth.service';
import { LocaleService } from '../../core/locale.service';
import { AdminUserAction, AdminUserDetail, AdminUserEditable } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { FLAG_LABEL, TICKET_STATUS_LABEL, shortDate, statusClass } from './labels';

/** Fields any admin may edit; the rest are superuser-only (the API enforces the same rule). */
const BASIC_FIELDS: (keyof AdminUserEditable)[] = [
  'username',
  'email',
  'first_name',
  'last_name',
  'timezone',
  'country',
  'default_currency',
];

type NotifyKey = 'notify_weekly_summaries' | 'notify_low_balance' | 'notify_setup_nudges' | 'notify_plan_updates';

interface ActionDef {
  action: AdminUserAction;
  label: string;
  confirm?: string;
  done: string;
}

@Component({
  selector: 'app-admin-user-detail',
  standalone: true,
  imports: [CommonModule, RouterLink, ReactiveFormsModule],
  templateUrl: './admin-user-detail.component.html',
  styleUrl: './admin-shared.scss',
})
export class AdminUserDetailComponent implements OnInit {
  private admin = inject(AdminService);
  private auth = inject(AuthService);
  private fb = inject(FormBuilder);
  private locale = inject(LocaleService);
  private toast = inject(ToastService);
  private route = inject(ActivatedRoute);

  data = signal<AdminUserDetail | null>(null);
  busy = signal(false);
  id = '';

  editing = signal(false);
  saving = signal(false);
  countries = signal<{ code: string; label: string }[]>([]);
  readonly currencies = this.locale.currencies;
  readonly setupStatuses = [
    { code: 'pending', label: 'Not started' },
    { code: 'incomplete', label: 'Skipped' },
    { code: 'complete', label: 'Complete' },
  ];
  readonly notifyFields: { key: NotifyKey; label: string }[] = [
    { key: 'notify_weekly_summaries', label: 'Weekly summaries' },
    { key: 'notify_low_balance', label: 'Low-balance alerts' },
    { key: 'notify_setup_nudges', label: 'Setup reminders' },
    { key: 'notify_plan_updates', label: 'Plan updates' },
  ];

  form = this.fb.nonNullable.group({
    username: ['', Validators.required],
    email: ['', [Validators.required, Validators.email]],
    first_name: [''],
    last_name: [''],
    timezone: [''],
    country: [''],
    default_currency: ['USD'],
    phone: [''],
    email_verified: [false],
    setup_status: ['pending'],
    notify_weekly_summaries: [true],
    notify_low_balance: [true],
    notify_setup_nudges: [true],
    notify_plan_updates: [true],
    savings_target_pct: [20, [Validators.min(0), Validators.max(90)]],
  });

  me = this.auth.user;
  isSuperuser = computed(() => !!this.me()?.is_superuser);
  /** Any admin edits regular users (and themselves); only a superuser edits another admin. */
  canEdit = computed(() => {
    const u = this.data()?.user;
    if (!u) return false;
    const targetIsAdmin = u.is_staff || u.is_superuser;
    return this.isSuperuser() || !targetIsAdmin || u.id === this.me()?.id;
  });
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

  startEdit(): void {
    const u = this.data()?.user;
    if (!u) return;
    this.form.reset({
      username: u.username,
      email: u.email ?? '',
      first_name: u.first_name ?? '',
      last_name: u.last_name ?? '',
      timezone: u.timezone ?? '',
      country: u.country ?? '',
      default_currency: u.default_currency || 'USD',
      phone: u.phone ?? '',
      email_verified: u.email_verified,
      setup_status: u.setup_status || 'pending',
      notify_weekly_summaries: u.notify_weekly_summaries,
      notify_low_balance: u.notify_low_balance,
      notify_setup_nudges: u.notify_setup_nudges,
      notify_plan_updates: u.notify_plan_updates,
      savings_target_pct: u.savings_target_pct ?? 20,
    });
    if (!this.countries().length) {
      this.locale.loadMeta().subscribe((meta) => this.countries.set(meta.countries ?? []));
    }
    this.editing.set(true);
  }

  cancelEdit(): void {
    this.editing.set(false);
  }

  save(): void {
    const u = this.data()?.user;
    if (!u) return;
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.toast.error('Check the highlighted fields.');
      return;
    }
    // Send only what changed; superuser-only fields are left out for other admins.
    const value = this.form.getRawValue();
    const keys = (Object.keys(value) as (keyof AdminUserEditable)[]).filter(
      (k) => this.isSuperuser() || BASIC_FIELDS.includes(k)
    );
    const patch: Partial<AdminUserEditable> = {};
    for (const k of keys) {
      const next = typeof value[k] === 'string' ? (value[k] as string).trim() : value[k];
      if (next !== (u[k] ?? '')) (patch as Record<string, unknown>)[k] = next;
    }
    if (!Object.keys(patch).length) {
      this.editing.set(false);
      return;
    }
    if (patch.email && !confirm(`Change the email to ${patch.email}? Both the old and the new address get a notice.`)) {
      return;
    }
    this.saving.set(true);
    this.admin.updateUser(this.id, patch).subscribe({
      next: (d) => {
        this.saving.set(false);
        this.editing.set(false);
        this.data.set(d);
        this.toast.success('User details saved.');
      },
      error: (err) => {
        this.saving.set(false);
        this.toast.fromHttpError(err, 'Could not save the changes.');
      },
    });
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
