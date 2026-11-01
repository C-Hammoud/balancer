import { Component, ElementRef, HostListener, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { Subscription, interval } from 'rxjs';
import { BudgetingService } from '../../core/budgeting.service';
import { FinanceDataRefreshService } from '../../core/finance-data-refresh.service';
import { AppNotification } from '../../core/models';

const POLL_MS = 120_000;

@Component({
  selector: 'app-notification-bell',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './notification-bell.component.html',
  styleUrl: './notification-bell.component.scss',
})
export class NotificationBellComponent implements OnInit, OnDestroy {
  private api = inject(BudgetingService);
  private router = inject(Router);
  private refresh = inject(FinanceDataRefreshService);
  private host = inject(ElementRef<HTMLElement>);
  private subs: Subscription[] = [];

  unread = signal(0);
  open = signal(false);
  items = signal<AppNotification[]>([]);
  loading = signal(false);

  ngOnInit(): void {
    this.loadCount();
    this.subs.push(interval(POLL_MS).subscribe(() => this.loadCount()));
    this.subs.push(this.refresh.changed$.subscribe(() => this.loadCount()));
  }

  ngOnDestroy(): void {
    this.subs.forEach((s) => s.unsubscribe());
  }

  @HostListener('document:click', ['$event'])
  onDocumentClick(event: Event): void {
    if (this.open() && !this.host.nativeElement.contains(event.target as Node)) this.open.set(false);
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    this.open.set(false);
  }

  loadCount(): void {
    this.api.notificationCount().subscribe({
      next: (r) => this.unread.set(r.unread),
      error: () => undefined,
    });
  }

  toggle(): void {
    const opening = !this.open();
    this.open.set(opening);
    if (!opening) return;
    this.loading.set(true);
    this.api.notifications().subscribe({
      next: (rows) => {
        this.items.set(rows.slice(0, 15));
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  openItem(n: AppNotification): void {
    this.open.set(false);
    if (!n.is_read) {
      this.api.markNotificationRead(n.id).subscribe({ next: () => this.loadCount(), error: () => undefined });
    }
    if (n.link) this.router.navigateByUrl(n.link);
  }

  markAll(): void {
    this.api.markAllNotificationsRead().subscribe({
      next: () => {
        this.items.update((rows) => rows.map((r) => ({ ...r, is_read: true })));
        this.unread.set(0);
      },
      error: () => undefined,
    });
  }
}
