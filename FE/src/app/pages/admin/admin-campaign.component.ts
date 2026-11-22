import { Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpErrorResponse } from '@angular/common/http';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { Observable, map, of } from 'rxjs';
import { AdminService } from '../../core/admin.service';
import { AuthService } from '../../core/auth.service';
import { LocaleService } from '../../core/locale.service';
import {
  Campaign,
  CampaignAudience,
  CampaignInput,
  ChannelStats,
  MessageChannel,
  MessageDelivery,
  MessagingMeta,
  Paged,
  UserRef,
} from '../../core/models';
import { ToastService } from '../../core/toast.service';
import {
  CAMPAIGN_STATUS_CLASS,
  CAMPAIGN_STATUS_LABEL,
  CATEGORY_LABEL,
  CHANNEL_LABEL,
  DELIVERY_STATUS_CLASS,
  shortDate,
} from './labels';
import { audienceSummary, localInputToIso, parseCodes } from './messaging.helpers';

const POLL_MS = 8000;

/** Admin → Notifications → one campaign: edit the draft, pick the audience, test, send / schedule, stats. */
@Component({
  selector: 'app-admin-campaign',
  standalone: true,
  imports: [FormsModule, RouterLink],
  templateUrl: './admin-campaign.component.html',
  styleUrls: ['./admin-shared.scss', './admin-messaging.scss'],
})
export class AdminCampaignComponent implements OnInit, OnDestroy {
  private admin = inject(AdminService);
  private auth = inject(AuthService);
  private locale = inject(LocaleService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private toast = inject(ToastService);

  readonly statusLabel = CAMPAIGN_STATUS_LABEL;
  readonly statusClass = CAMPAIGN_STATUS_CLASS;
  readonly categoryLabel = CATEGORY_LABEL;
  readonly channelLabel = CHANNEL_LABEL;
  readonly deliveryClass = DELIVERY_STATUS_CLASS;
  readonly currencies = this.locale.currencies;

  meta = signal<MessagingMeta | null>(null);
  campaign = signal<Campaign | null>(null);
  busy = signal(false);
  isSuperuser = computed(() => !!this.auth.user()?.is_superuser);
  editable = computed(() => {
    const c = this.campaign();
    return !c || c.status === 'draft' || c.status === 'scheduled';
  });
  marketingTemplates = computed(() => (this.meta()?.templates ?? []).filter((t) => t.category !== 'account'));

  // Message
  name = '';
  category: 'marketing' | 'reminder' = 'marketing';
  subject = '';
  body = '';
  link = '';
  linkLabel = '';
  channels = new Set<MessageChannel>(['in_app', 'email']);

  // Audience
  audienceType: CampaignAudience['type'] = 'filter';
  flags = new Set<string>();
  countriesText = '';
  currencyCodes = new Set<string>();
  verified: '' | 'yes' | 'no' = '';
  joinedFrom = '';
  joinedTo = '';
  lastLogin: CampaignAudience['last_login'] = '';
  pickedUsers: UserRef[] = [];
  userQuery = '';
  userResults = signal<UserRef[]>([]);

  count = signal<{ count: number; sample: UserRef[] } | null>(null);
  counting = signal(false);
  private countTimer: ReturnType<typeof setTimeout> | null = null;

  // Sending
  when: 'now' | 'later' = 'now';
  scheduleAt = '';

  // Results
  deliveries = signal<Paged<MessageDelivery> | null>(null);
  deliveryStatus = '';
  deliveryChannel = '';
  private poll: ReturnType<typeof setInterval> | null = null;

  ngOnInit(): void {
    this.admin.messagingMeta().subscribe({
      next: (m) => this.meta.set(m),
      error: (err) => this.toast.fromHttpError(err, 'Could not load templates.'),
    });
    const id = this.route.snapshot.paramMap.get('id');
    if (id && id !== 'new') {
      this.load(id);
    } else {
      this.refreshCount();
    }
  }

  ngOnDestroy(): void {
    if (this.poll) clearInterval(this.poll);
    if (this.countTimer) clearTimeout(this.countTimer);
  }

  private load(id: number | string): void {
    this.admin.campaign(id).subscribe({
      next: (c) => {
        this.fill(c);
        this.refreshCount();
        this.loadDeliveries(1);
        this.syncPolling();
      },
      error: (err) => this.toast.fromHttpError(err, 'Could not load the campaign.'),
    });
  }

  private fill(c: Campaign): void {
    this.campaign.set(c);
    this.name = c.name;
    this.category = c.category;
    this.subject = c.subject;
    this.body = c.body;
    this.link = c.link;
    this.linkLabel = c.link_label;
    this.channels = new Set(c.channels);
    const a = c.audience || { type: 'filter' };
    this.audienceType = a.type || 'filter';
    this.flags = new Set(a.flags ?? []);
    this.countriesText = (a.countries ?? []).join(', ');
    this.currencyCodes = new Set(a.currencies ?? []);
    this.verified = a.verified ?? '';
    this.joinedFrom = a.joined_from ?? '';
    this.joinedTo = a.joined_to ?? '';
    this.lastLogin = a.last_login ?? '';
    const named = new Map((c.audience_users ?? []).map((u) => [u.id, u]));
    this.pickedUsers = (a.user_ids ?? []).map((id) => named.get(id) ?? { id, username: `#${id}`, email: '' });
    if (c.scheduled_at && c.status === 'scheduled') {
      this.when = 'later';
      this.scheduleAt = toLocalInput(c.scheduled_at);
    }
  }

  /** While a campaign is sending, refresh its stats now and then. */
  private syncPolling(): void {
    const sending = this.campaign()?.status === 'sending';
    if (sending && !this.poll) {
      this.poll = setInterval(() => {
        const c = this.campaign();
        if (!c) return;
        this.admin.campaign(c.id).subscribe((fresh) => {
          this.campaign.set(fresh);
          this.loadDeliveries(this.deliveries()?.page ?? 1);
          this.syncPolling();
        });
      }, POLL_MS);
    } else if (!sending && this.poll) {
      clearInterval(this.poll);
      this.poll = null;
    }
  }

  // ---- Message ----

  applyTemplate(key: string): void {
    const t = this.meta()?.templates.find((x) => x.key === key);
    if (!t) return;
    this.subject = t.subject;
    this.body = t.body;
    this.link = t.link;
    this.linkLabel = t.link_label;
    this.channels = new Set(t.channels.length ? t.channels : ['in_app', 'email']);
    this.category = t.category === 'marketing' ? 'marketing' : 'reminder';
    if (!this.name) this.name = t.name;
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

  // ---- Audience ----

  audience(): CampaignAudience {
    if (this.audienceType === 'all') return { type: 'all' };
    if (this.audienceType === 'users') return { type: 'users', user_ids: this.pickedUsers.map((u) => u.id) };
    return {
      type: 'filter',
      flags: [...this.flags],
      countries: parseCodes(this.countriesText),
      currencies: [...this.currencyCodes],
      verified: this.verified,
      joined_from: this.joinedFrom,
      joined_to: this.joinedTo,
      last_login: this.lastLogin,
    };
  }

  /** A few names from the audience ("ann, bob…"). */
  sampleText(): string {
    const c = this.count();
    if (!c?.sample.length) return '';
    return c.sample.map((u) => u.username).join(', ') + (c.count > c.sample.length ? '…' : '');
  }

  audienceText(): string {
    return audienceSummary(this.audience());
  }

  toggleIn(set: Set<string>, value: string, on: boolean): Set<string> {
    const next = new Set(set);
    if (on) next.add(value);
    else next.delete(value);
    return next;
  }

  setFlag(code: string, on: boolean): void {
    this.flags = this.toggleIn(this.flags, code, on);
    this.audienceChanged();
  }

  setCurrency(code: string, on: boolean): void {
    this.currencyCodes = this.toggleIn(this.currencyCodes, code, on);
    this.audienceChanged();
  }

  /** Recount shortly after the last change. */
  audienceChanged(): void {
    if (this.countTimer) clearTimeout(this.countTimer);
    this.countTimer = setTimeout(() => this.refreshCount(), 400);
  }

  refreshCount(): void {
    const a = this.audience();
    if (a.type === 'users' && !a.user_ids?.length) {
      this.count.set({ count: 0, sample: [] });
      return;
    }
    this.counting.set(true);
    this.admin.audienceCount(a).subscribe({
      next: (r) => {
        this.count.set(r);
        this.counting.set(false);
      },
      error: () => {
        this.count.set(null);
        this.counting.set(false);
      },
    });
  }

  searchUsers(): void {
    const q = this.userQuery.trim();
    if (!q) {
      this.userResults.set([]);
      return;
    }
    this.admin.users({ q, pool: '', page: 1 }).subscribe({
      next: (p) => this.userResults.set(p.results.filter((u) => u.is_active).map((u) => ({ id: u.id, username: u.username, email: u.email }))),
      error: () => this.userResults.set([]),
    });
  }

  pickUser(u: UserRef): void {
    if (!this.pickedUsers.some((x) => x.id === u.id)) this.pickedUsers = [...this.pickedUsers, u];
    this.audienceChanged();
  }

  unpickUser(u: UserRef): void {
    this.pickedUsers = this.pickedUsers.filter((x) => x.id !== u.id);
    this.audienceChanged();
  }

  // ---- Save / test / send ----

  private input(): CampaignInput {
    return {
      name: this.name.trim(),
      category: this.category,
      subject: this.subject,
      body: this.body,
      link: this.link.trim(),
      link_label: this.linkLabel.trim(),
      channels: [...this.channels],
      audience: this.audience(),
    };
  }

  /** Create or update the draft; emits the saved campaign. */
  private persist(): Observable<Campaign> {
    const c = this.campaign();
    if (c && !this.editable()) return of(c);
    const req = c ? this.admin.updateCampaign(c.id, this.input()) : this.admin.createCampaign(this.input());
    return req.pipe(
      map((saved) => {
        const isNew = !c;
        this.campaign.set(saved);
        if (isNew) this.router.navigate(['/admin/notifications', saved.id], { replaceUrl: true });
        return saved;
      })
    );
  }

  save(): void {
    this.busy.set(true);
    this.persist().subscribe({
      next: () => {
        this.busy.set(false);
        this.toast.success('Campaign saved.');
      },
      error: (err) => this.fail(err, 'Could not save the campaign.'),
    });
  }

  sendTest(): void {
    this.busy.set(true);
    this.persist().subscribe({
      next: (c) =>
        this.admin.testCampaign(c.id).subscribe({
          next: (r) => {
            this.busy.set(false);
            const ok = r.deliveries.some((d) => d.status === 'sent');
            (ok ? this.toast.success.bind(this.toast) : this.toast.error.bind(this.toast))(
              `Test sent to you. ${r.summary ?? ''}`.trim()
            );
          },
          error: (err) => this.fail(err, 'Could not send the test.'),
        }),
      error: (err) => this.fail(err, 'Could not save the campaign.'),
    });
  }

  send(): void {
    const scheduledAt = this.when === 'later' ? localInputToIso(this.scheduleAt) : null;
    if (this.when === 'later' && !scheduledAt) {
      this.toast.error('Choose the date and time to send.');
      return;
    }
    this.busy.set(true);
    this.persist().subscribe({
      next: (c) =>
        this.admin.audienceCount(c.audience).subscribe({
          next: ({ count }) => {
            this.count.set({ count, sample: this.count()?.sample ?? [] });
            if (!count) {
              this.busy.set(false);
              this.toast.error('Nobody matches this audience.');
              return;
            }
            const whenText = scheduledAt ? `on ${shortDate(scheduledAt)}` : 'now';
            const channels = [...this.channels].map((ch) => CHANNEL_LABEL[ch]).join(' and ');
            if (!confirm(`Send “${c.name}” ${whenText} by ${channels} to ${count} user(s)?`)) {
              this.busy.set(false);
              return;
            }
            this.admin.sendCampaign(c.id, count, scheduledAt).subscribe({
              next: (sent) => {
                this.busy.set(false);
                this.campaign.set(sent);
                this.toast.success(
                  sent.status === 'scheduled' ? `Scheduled for ${shortDate(sent.scheduled_at)}.` : 'Sending started.'
                );
                this.loadDeliveries(1);
                this.syncPolling();
              },
              error: (err: HttpErrorResponse) => {
                if (err.status === 409 && typeof err.error?.count === 'number') {
                  this.count.set({ count: err.error.count, sample: this.count()?.sample ?? [] });
                }
                this.fail(err, 'Could not send the campaign.');
              },
            });
          },
          error: (err) => this.fail(err, 'Could not count the audience.'),
        }),
      error: (err) => this.fail(err, 'Could not save the campaign.'),
    });
  }

  cancelSending(): void {
    const c = this.campaign();
    if (!c || !confirm('Stop this campaign? Messages already sent stay sent.')) return;
    this.admin.cancelCampaign(c.id).subscribe({
      next: (fresh) => {
        this.campaign.set(fresh);
        this.syncPolling();
        this.toast.success('Campaign cancelled.');
      },
      error: (err) => this.fail(err, 'Could not cancel the campaign.'),
    });
  }

  remove(): void {
    const c = this.campaign();
    if (!c || !confirm(`Delete the campaign “${c.name}”?`)) return;
    this.admin.deleteCampaign(c.id).subscribe({
      next: () => {
        this.toast.success('Campaign deleted.');
        this.router.navigate(['/admin/notifications']);
      },
      error: (err) => this.fail(err, 'Could not delete the campaign.'),
    });
  }

  private fail(err: unknown, fallback: string): void {
    this.busy.set(false);
    this.toast.fromHttpError(err, fallback);
  }

  // ---- Results ----

  loadDeliveries(page: number): void {
    const c = this.campaign();
    if (!c || c.status === 'draft' || c.status === 'scheduled') return;
    this.admin
      .campaignDeliveries(c.id, { status: this.deliveryStatus, channel: this.deliveryChannel, page })
      .subscribe({ next: (p) => this.deliveries.set(p), error: () => this.deliveries.set(null) });
  }

  channelStats(): { code: MessageChannel; stats: ChannelStats }[] {
    const by = this.campaign()?.stats?.by_channel ?? {};
    return (Object.keys(by) as MessageChannel[]).map((code) => ({ code, stats: by[code]! }));
  }

  date(iso: string | null | undefined): string {
    return shortDate(iso);
  }
}

/** ISO date-time → value for <input type="datetime-local"> in the browser's timezone. */
function toLocalInput(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
