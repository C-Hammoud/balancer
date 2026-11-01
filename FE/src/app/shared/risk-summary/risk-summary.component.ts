import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { FinanceDataRefreshService } from '../../core/finance-data-refresh.service';
import { RiskService } from '../../core/risk.service';
import { RiskFactor, RiskReport } from '../../core/models';

const LEVEL_LABEL: Record<string, string> = {
  low: 'Low risk',
  medium: 'Medium risk',
  high: 'High risk',
  unknown: 'Not enough data yet',
};

/** Compact debt & liquidity risk card for the main dashboard; reloads whenever data changes. */
@Component({
  selector: 'app-risk-summary',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './risk-summary.component.html',
  styleUrl: './risk-summary.component.scss',
})
export class RiskSummaryComponent implements OnInit {
  private risk = inject(RiskService);
  private refresh = inject(FinanceDataRefreshService);
  private destroyRef = inject(DestroyRef);

  report = signal<RiskReport | null>(null);
  failed = signal(false);

  levelLabel = computed(() => LEVEL_LABEL[this.report()?.level ?? 'unknown']);
  scoreDeg = computed(() => Math.round(((this.report()?.score ?? 0) / 100) * 360));
  /** Checks needing attention first (high, then warn), at most three. */
  attention = computed(() => {
    const rank: Record<string, number> = { high: 0, warn: 1 };
    return (this.report()?.factors ?? [])
      .filter((f) => f.status === 'high' || f.status === 'warn')
      .sort((a, b) => rank[a.status] - rank[b.status])
      .slice(0, 3);
  });

  ngOnInit(): void {
    this.load();
    this.refresh.changed$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => this.load());
  }

  load(): void {
    this.risk.report().subscribe({
      next: (r) => {
        this.report.set(r);
        this.failed.set(false);
      },
      error: () => this.failed.set(true),
    });
  }

  money(value: string | string[] | null | undefined): string {
    if (typeof value !== 'string') return '—';
    return `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 })} ${this.report()?.currency ?? ''}`;
  }

  statusLabel(f: RiskFactor): string {
    return f.status === 'high' ? 'High' : 'Watch';
  }
}
