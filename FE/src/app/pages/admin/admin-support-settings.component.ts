import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AdminService } from '../../core/admin.service';
import { AuthService } from '../../core/auth.service';
import { AssignmentMode, SupportSettings } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { shortDate } from './labels';

/** How support tickets are assigned and closed. Superusers can change it; other admins can read it. */
@Component({
  selector: 'app-admin-support-settings',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <section class="hero">
      <div>
        <h1>Support settings</h1>
        <p>How new tickets reach an admin, and what happens when a user does not confirm a fix.</p>
      </div>
    </section>

    @if (settings(); as s) {
      <form class="panel form-grid" (ngSubmit)="save()">
        <fieldset [disabled]="!canEdit()" class="plain">
          <h2>Assignment</h2>
          @for (m of s.assignment_modes; track m.value) {
            <label class="radio">
              <input type="radio" name="mode" [value]="m.value" [(ngModel)]="mode" />
              <span><strong>{{ modeTitle[m.value] }}</strong><small>{{ modeHelp[m.value] }}</small></span>
            </label>
          }

          <h2>When support marks a ticket resolved</h2>
          <label>
            Remind the user after (days, 0 = never)
            <input type="number" min="0" max="90" name="reminder" [(ngModel)]="reminderDays" />
          </label>
          <label>
            Close automatically after (days, 0 = never)
            <input type="number" min="0" max="90" name="autoclose" [(ngModel)]="autoCloseDays" />
          </label>
          <small class="muted">Closing (by the user or automatically) emails both the user and the assigned admin.</small>

          <h2>Admin emails</h2>
          <label class="radio">
            <input type="checkbox" name="emails" [(ngModel)]="emailAdmins" />
            <span>Email admins when a ticket is assigned to them or a user says it is not fixed
              <small>In-app notifications are always sent. Closing confirmations are always emailed.</small></span>
          </label>
        </fieldset>

        @if (canEdit()) {
          <div class="toolbar"><button class="btn primary" type="submit" [disabled]="saving()">Save settings</button></div>
        } @else {
          <p class="muted">Only a superuser can change these settings.</p>
        }
        <small class="muted">
          @if (s.saved) {
            Last changed by {{ s.updated_by?.username || '—' }} on {{ date(s.updated_at) }}.
          } @else {
            Using the defaults from the server configuration (SUPPORT_* in .env) until saved here.
          }
        </small>
      </form>
    } @else {
      <p class="muted">Loading…</p>
    }
  `,
  styleUrl: './admin-shared.scss',
  styles: [
    `fieldset.plain { border: 0; padding: 0; margin: 0; display: grid; gap: 0.6rem; }
     .radio { display: flex !important; gap: 0.6rem; align-items: flex-start; }
     .radio small { display: block; color: var(--muted); }
     h2 { margin-top: 0.5rem !important; }`,
  ],
})
export class AdminSupportSettingsComponent implements OnInit {
  private admin = inject(AdminService);
  private auth = inject(AuthService);
  private toast = inject(ToastService);

  readonly modeTitle: Record<AssignmentMode, string> = {
    least_busy: 'Automatic — least busy',
    round_robin: 'Automatic — round robin',
    pool: 'Pool — admins take tickets',
  };
  readonly modeHelp: Record<AssignmentMode, string> = {
    least_busy: 'Each new ticket goes to the admin with the fewest unfinished tickets.',
    round_robin: 'New tickets go to each admin in turn, whatever their workload.',
    pool: 'New tickets wait in the pool until an admin clicks "Take it".',
  };

  settings = signal<SupportSettings | null>(null);
  saving = signal(false);
  canEdit = computed(() => !!this.auth.user()?.is_superuser);
  mode: AssignmentMode = 'least_busy';
  reminderDays = 3;
  autoCloseDays = 7;
  emailAdmins = true;

  ngOnInit(): void {
    this.admin.supportSettings().subscribe({
      next: (s) => this.apply(s),
      error: (err) => this.toast.fromHttpError(err, 'Could not load support settings.'),
    });
  }

  private apply(s: SupportSettings): void {
    this.settings.set(s);
    this.mode = s.assignment_mode;
    this.reminderDays = s.reminder_days;
    this.autoCloseDays = s.auto_close_days;
    this.emailAdmins = s.email_admins;
  }

  save(): void {
    this.saving.set(true);
    this.admin
      .updateSupportSettings({
        assignment_mode: this.mode,
        reminder_days: Number(this.reminderDays) || 0,
        auto_close_days: Number(this.autoCloseDays) || 0,
        email_admins: this.emailAdmins,
      })
      .subscribe({
        next: (s) => {
          this.apply(s);
          this.saving.set(false);
          this.toast.success('Support settings saved.');
        },
        error: (err) => {
          this.saving.set(false);
          this.toast.fromHttpError(err, 'Could not save support settings.');
        },
      });
  }

  date(iso: string | null): string {
    return shortDate(iso);
  }
}
