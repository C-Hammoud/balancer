import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AdminService } from '../../core/admin.service';
import {
  MessageChannel,
  MessageDelivery,
  MessagePreview,
  MessageTemplate,
  MessagingMeta,
  MissingItem,
} from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { CATEGORY_LABEL, CHANNEL_LABEL, DELIVERY_STATUS_CLASS, shortDate } from './labels';

/**
 * Admin → user: send this user a notice or reminder (in-app / email; SMS later), see what they
 * have not filled in yet, and every message sent to them.
 */
@Component({
  selector: 'app-admin-user-notify',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './admin-user-notify.component.html',
  styleUrls: ['./admin-shared.scss', './admin-messaging.scss'],
})
export class AdminUserNotifyComponent implements OnInit {
  private admin = inject(AdminService);
  private toast = inject(ToastService);

  userId = input.required<number>();

  meta = signal<MessagingMeta | null>(null);
  missing = signal<MissingItem[]>([]);
  deliveries = signal<MessageDelivery[]>([]);
  loading = signal(true);

  composing = signal(false);
  preview = signal<MessagePreview | null>(null);
  busy = signal(false);

  templateKey = 'custom';
  subject = '';
  body = '';
  link = '';
  linkLabel = '';
  channels = new Set<MessageChannel>();

  readonly channelLabel = CHANNEL_LABEL;
  readonly categoryLabel = CATEGORY_LABEL;
  readonly statusClass = DELIVERY_STATUS_CLASS;

  /** Notices and reminders for one user (marketing goes through campaigns). */
  templates = computed(() => (this.meta()?.templates ?? []).filter((t) => t.category !== 'marketing'));

  ngOnInit(): void {
    this.admin.messagingMeta().subscribe({
      next: (m) => this.meta.set(m),
      error: (err) => this.toast.fromHttpError(err, 'Could not load the message templates.'),
    });
    this.load();
  }

  load(): void {
    this.admin.userMessages(this.userId()).subscribe({
      next: (r) => {
        this.missing.set(r.missing);
        this.deliveries.set(r.deliveries);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  /** Open the editor with a template (default: the missing-data reminder when something is missing). */
  compose(key?: string): void {
    const fallback = this.missing().length ? 'missing_data' : 'custom';
    this.applyTemplate(key || fallback);
    this.composing.set(true);
    this.refreshPreview();
  }

  cancel(): void {
    this.composing.set(false);
    this.preview.set(null);
  }

  applyTemplate(key: string): void {
    const t: MessageTemplate | undefined = this.meta()?.templates.find((x) => x.key === key);
    this.templateKey = key;
    this.subject = t?.subject ?? '';
    this.body = t?.body ?? '';
    this.link = t?.link ?? '';
    this.linkLabel = t?.link_label ?? '';
    this.channels = new Set(t?.channels ?? ['in_app']);
  }

  onTemplateChange(key: string): void {
    this.applyTemplate(key);
    this.refreshPreview();
  }

  toggleChannel(code: MessageChannel, on: boolean): void {
    const next = new Set(this.channels);
    if (on) next.add(code);
    else next.delete(code);
    this.channels = next;
  }

  insertPlaceholder(key: string): void {
    this.body = `${this.body}{${key}}`;
  }

  private payload() {
    return {
      template_key: this.templateKey,
      subject: this.subject,
      body: this.body,
      link: this.link,
      link_label: this.linkLabel,
      channels: [...this.channels],
    };
  }

  refreshPreview(): void {
    this.admin.previewUserMessage(this.userId(), this.payload()).subscribe({
      next: (p) => this.preview.set(p),
      error: (err) => {
        this.preview.set(null);
        this.toast.fromHttpError(err, 'Could not preview the message.');
      },
    });
  }

  /** Channels chosen that cannot reach the user (shown before sending). */
  blockedChannels(): string[] {
    return (this.preview()?.channels ?? [])
      .filter((c) => this.channels.has(c.code) && c.reason)
      .map((c) => `${c.label}: ${c.reason}`);
  }

  send(): void {
    if (!this.channels.size) {
      this.toast.error('Choose at least one channel.');
      return;
    }
    this.busy.set(true);
    this.admin.sendUserMessage(this.userId(), this.payload()).subscribe({
      next: (r) => {
        this.busy.set(false);
        const sent = r.deliveries.some((d) => d.status === 'sent');
        if (sent) this.toast.success(`Message sent. ${r.summary ?? ''}`.trim());
        else this.toast.error(`Nothing was sent. ${r.summary ?? ''}`.trim(), 7000);
        this.cancel();
        this.load();
      },
      error: (err) => {
        this.busy.set(false);
        this.toast.fromHttpError(err, 'Could not send the message.');
      },
    });
  }

  date(iso: string | null | undefined): string {
    return shortDate(iso);
  }
}
