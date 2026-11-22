import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { AdminService } from '../../core/admin.service';
import { Campaign, CampaignStatus, Paged } from '../../core/models';
import { ToastService } from '../../core/toast.service';
import { CAMPAIGN_STATUS_CLASS, CAMPAIGN_STATUS_LABEL, CATEGORY_LABEL, CHANNEL_LABEL, shortDate } from './labels';
import { audienceSummary } from './messaging.helpers';

/** Admin → Notifications: campaigns (marketing and reminders to many users). */
@Component({
  selector: 'app-admin-notifications',
  standalone: true,
  imports: [FormsModule, RouterLink],
  styleUrls: ['./admin-shared.scss', './admin-messaging.scss'],
  template: `
    <section class="hero">
      <div>
        <h1>Notifications</h1>
        <p>
          Send announcements and reminders to many users by in-app notification and email (SMS later).
          To message one user, open them in <a routerLink="/admin/users">Users</a>.
        </p>
      </div>
      <div class="toolbar">
        <a class="btn ghost" routerLink="/admin/notifications/templates">Templates</a>
        <a class="btn primary" routerLink="/admin/notifications/new">New campaign</a>
      </div>
    </section>

    <form class="filters">
      <label>
        Status
        <select name="status" [(ngModel)]="status" (ngModelChange)="load(1)">
          <option value="">Any</option>
          @for (s of statuses; track s) {
            <option [value]="s">{{ statusLabel[s] }}</option>
          }
        </select>
      </label>
    </form>

    <div class="panel table-wrap">
      <table>
        <thead>
          <tr><th>Campaign</th><th>Status</th><th>Audience</th><th>Channels</th><th>Reached</th><th>Read / clicked</th><th>When</th></tr>
        </thead>
        <tbody>
          @for (c of page()?.results ?? []; track c.id) {
            <tr class="clickable" (click)="open(c)">
              <td><strong>{{ c.name }}</strong><small>{{ categoryLabel[c.category] }} · {{ c.subject }}</small></td>
              <td><span [class]="'pill ' + statusClass[c.status]">{{ statusLabel[c.status] }}</span></td>
              <td>{{ audience(c) }}</td>
              <td>{{ channels(c) }}</td>
              <td>{{ c.stats?.processed ?? 0 }} / {{ c.stats?.recipients || '—' }}</td>
              <td>{{ readCount(c) }} / {{ clickCount(c) }}</td>
              <td>{{ when(c) }}</td>
            </tr>
          } @empty {
            <tr><td colspan="7" class="empty">{{ loading() ? 'Loading…' : 'No campaigns yet.' }}</td></tr>
          }
        </tbody>
      </table>
      @if (page(); as p) {
        <div class="pager">
          <span>{{ p.count }} campaign(s)</span>
          <button class="btn ghost" type="button" [disabled]="p.page <= 1" (click)="load(p.page - 1)">Previous</button>
          <span>Page {{ p.page }}</span>
          <button class="btn ghost" type="button" [disabled]="p.page * p.page_size >= p.count" (click)="load(p.page + 1)">
            Next
          </button>
        </div>
      }
    </div>
  `,
})
export class AdminNotificationsComponent implements OnInit {
  private admin = inject(AdminService);
  private router = inject(Router);
  private route = inject(ActivatedRoute);
  private toast = inject(ToastService);

  page = signal<Paged<Campaign> | null>(null);
  loading = signal(true);
  status: CampaignStatus | '' = '';

  readonly statuses: CampaignStatus[] = ['draft', 'scheduled', 'sending', 'sent', 'cancelled'];
  readonly statusLabel = CAMPAIGN_STATUS_LABEL;
  readonly statusClass = CAMPAIGN_STATUS_CLASS;
  readonly categoryLabel = CATEGORY_LABEL;

  ngOnInit(): void {
    const status = this.route.snapshot.queryParamMap.get('status') as CampaignStatus | null;
    if (status && this.statuses.includes(status)) this.status = status;
    this.load(1);
  }

  load(page: number): void {
    this.loading.set(true);
    this.admin.campaigns({ status: this.status, page }).subscribe({
      next: (p) => {
        this.page.set(p);
        this.loading.set(false);
      },
      error: (err) => {
        this.loading.set(false);
        this.toast.fromHttpError(err, 'Could not load campaigns.');
      },
    });
  }

  open(c: Campaign): void {
    this.router.navigate(['/admin/notifications', c.id]);
  }

  audience(c: Campaign): string {
    return audienceSummary(c.audience);
  }

  channels(c: Campaign): string {
    return c.channels.map((ch) => CHANNEL_LABEL[ch] ?? ch).join(', ') || '—';
  }

  readCount(c: Campaign): number {
    return c.stats?.by_channel.in_app?.read ?? 0;
  }

  clickCount(c: Campaign): number {
    return c.stats?.by_channel.email?.clicked ?? 0;
  }

  when(c: Campaign): string {
    if (c.status === 'scheduled') return `Sends ${shortDate(c.scheduled_at)}`;
    if (c.finished_at) return shortDate(c.finished_at);
    if (c.started_at) return `Started ${shortDate(c.started_at)}`;
    return `Created ${shortDate(c.created_at)}`;
  }
}
