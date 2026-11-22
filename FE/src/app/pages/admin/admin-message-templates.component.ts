import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { AdminService } from '../../core/admin.service';
import { AuthService } from '../../core/auth.service';
import { MessageCategory, MessageChannel, MessageTemplate, MessagingMeta } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { CATEGORY_LABEL, CHANNEL_LABEL } from './labels';

interface Draft {
  key: string | null;
  name: string;
  category: MessageCategory;
  subject: string;
  body: string;
  link: string;
  link_label: string;
  channels: Set<MessageChannel>;
}

/** Admin → Notifications → Templates: the messages admins start from (superusers edit them). */
@Component({
  selector: 'app-admin-message-templates',
  standalone: true,
  imports: [FormsModule, RouterLink],
  styleUrls: ['./admin-shared.scss', './admin-messaging.scss'],
  template: `
    <p><a routerLink="/admin/notifications">← Notifications</a></p>
    <section class="hero">
      <div>
        <h1>Message templates</h1>
        <p>
          Account notices, reminders and marketing messages admins start from. Use placeholders such as
          <code>{{ '{first_name}' }}</code>; they are filled in for each user.
          @if (!isSuperuser()) { Only a superuser can change them. }
        </p>
      </div>
      @if (isSuperuser() && !draft()) {
        <button type="button" class="btn primary" (click)="startNew()">New template</button>
      }
    </section>

    @if (draft(); as d) {
      <section class="panel">
        <h2>{{ d.key ? 'Edit template' : 'New template' }}</h2>
        <div class="compose-form form-grid">
          <div class="two">
            <label>Name <input [(ngModel)]="d.name" maxlength="80" /></label>
            <label>
              Type
              <select [(ngModel)]="d.category">
                @for (c of meta()?.categories ?? []; track c.code) {
                  <option [value]="c.code">{{ c.label }}</option>
                }
              </select>
            </label>
          </div>
          <fieldset class="channels">
            <legend>Default channels</legend>
            @for (ch of meta()?.channels ?? []; track ch.code) {
              <label class="check" [class.disabled]="!ch.enabled">
                <input
                  type="checkbox"
                  [disabled]="!ch.enabled"
                  [checked]="d.channels.has(ch.code)"
                  (change)="toggle(d, ch.code, $any($event.target).checked)"
                />
                {{ ch.label }}
              </label>
            }
          </fieldset>
          <label>Subject <input [(ngModel)]="d.subject" maxlength="200" /></label>
          <label>Message <textarea [(ngModel)]="d.body" rows="8" maxlength="5000"></textarea></label>
          <div class="placeholders">
            <span class="muted">Insert:</span>
            @for (p of meta()?.placeholders ?? []; track p.key) {
              <button type="button" class="chip" [title]="p.description" (click)="d.body = d.body + '{' + p.key + '}'">
                {{ '{' + p.key + '}' }}
              </button>
            }
          </div>
          <div class="two">
            <label>Button opens (app page) <input [(ngModel)]="d.link" placeholder="/dashboard" maxlength="300" /></label>
            <label>Button text <input [(ngModel)]="d.link_label" maxlength="60" /></label>
          </div>
        </div>
        <div class="toolbar send-actions">
          <button type="button" class="btn primary" [disabled]="busy()" (click)="save(d)">Save template</button>
          <button type="button" class="btn ghost" [disabled]="busy()" (click)="draft.set(null)">Cancel</button>
        </div>
      </section>
    }

    <div class="panel table-wrap">
      <table>
        <thead><tr><th>Template</th><th>Type</th><th>Channels</th><th></th></tr></thead>
        <tbody>
          @for (t of meta()?.templates ?? []; track t.key) {
            <tr>
              <td><strong>{{ t.name }}</strong><small>{{ t.subject || '(no subject)' }}</small></td>
              <td>{{ categoryLabel[t.category] }}</td>
              <td>{{ channelNames(t) }}</td>
              <td class="row-action">
                @if (isSuperuser()) {
                  <button type="button" class="btn ghost small" (click)="edit(t)">Edit</button>
                  @if (!t.is_builtin) {
                    <button type="button" class="btn ghost small" (click)="remove(t)">Delete</button>
                  }
                }
              </td>
            </tr>
          } @empty {
            <tr><td colspan="4" class="empty">Loading…</td></tr>
          }
        </tbody>
      </table>
    </div>
  `,
})
export class AdminMessageTemplatesComponent implements OnInit {
  private admin = inject(AdminService);
  private auth = inject(AuthService);
  private toast = inject(ToastService);

  meta = signal<MessagingMeta | null>(null);
  draft = signal<Draft | null>(null);
  busy = signal(false);
  isSuperuser = computed(() => !!this.auth.user()?.is_superuser);
  readonly categoryLabel = CATEGORY_LABEL;

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.admin.messagingMeta().subscribe({
      next: (m) => this.meta.set(m),
      error: (err) => this.toast.fromHttpError(err, 'Could not load templates.'),
    });
  }

  channelNames(t: MessageTemplate): string {
    return t.channels.map((c) => CHANNEL_LABEL[c] ?? c).join(', ') || '—';
  }

  startNew(): void {
    this.draft.set({
      key: null, name: '', category: 'marketing', subject: '', body: 'Hi {first_name},\n\n',
      link: '', link_label: '', channels: new Set(['in_app', 'email']),
    });
  }

  edit(t: MessageTemplate): void {
    this.draft.set({ ...t, key: t.key, channels: new Set(t.channels) });
  }

  toggle(d: Draft, code: MessageChannel, on: boolean): void {
    if (on) d.channels.add(code);
    else d.channels.delete(code);
  }

  save(d: Draft): void {
    const payload = {
      name: d.name, category: d.category, subject: d.subject, body: d.body,
      link: d.link, link_label: d.link_label, channels: [...d.channels],
    };
    this.busy.set(true);
    const req = d.key ? this.admin.updateTemplate(d.key, payload) : this.admin.createTemplate(payload);
    req.subscribe({
      next: () => {
        this.busy.set(false);
        this.draft.set(null);
        this.toast.success('Template saved.');
        this.load();
      },
      error: (err) => {
        this.busy.set(false);
        this.toast.fromHttpError(err, 'Could not save the template.');
      },
    });
  }

  remove(t: MessageTemplate): void {
    if (!confirm(`Delete the template “${t.name}”?`)) return;
    this.admin.deleteTemplate(t.key).subscribe({
      next: () => {
        this.toast.success('Template deleted.');
        this.load();
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not delete the template.'),
    });
  }
}
