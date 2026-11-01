import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { CommonModule } from '@angular/common';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { BudgetingService } from '../../core/budgeting.service';
import { RiskService } from '../../core/risk.service';
import { ToastService } from '../../core/toast.service';
import { FinanceDataRefreshService } from '../../core/finance-data-refresh.service';
import {
  Account,
  RiskFactor,
  RiskHistoryPoint,
  RiskReport,
  RiskSettings,
  RiskSettingsPatch,
  RiskThresholdKey,
} from '../../core/models';

interface ThresholdField {
  key: RiskThresholdKey;
  label: string;
  suffix: string;
}

/** Where each factor's inputs can be fixed in the app. */
const FACTOR_LINKS: Record<string, { label: string; path: string }> = {
  debt_to_income: { label: 'Commitments', path: '/budgeting/commitments' },
  overdue_installments: { label: 'Commitments', path: '/budgeting/commitments' },
  balloon_exposure: { label: 'Commitments', path: '/budgeting/commitments' },
  debt_to_assets: { label: 'Net worth', path: '/budgeting/financial-standing' },
  emergency_fund: { label: 'Accounts', path: '/budgeting/config/accounts' },
  month_cash_flow: { label: 'Planned items', path: '/budgeting/config/planned-items' },
};

@Component({
  selector: 'app-risk',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink],
  templateUrl: './risk.component.html',
  styleUrl: './risk.component.scss',
})
export class RiskComponent implements OnInit {
  private risk = inject(RiskService);
  private budgeting = inject(BudgetingService);
  private fb = inject(FormBuilder);
  private toast = inject(ToastService);
  private refresh = inject(FinanceDataRefreshService);
  private destroyRef = inject(DestroyRef);

  report = signal<RiskReport | null>(null);
  history = signal<RiskHistoryPoint[]>([]);
  settings = signal<RiskSettings | null>(null);
  accounts = signal<Account[]>([]);
  loading = signal(true);
  refreshing = signal(false);
  saving = signal(false);
  showSettings = signal(false);
  selectedAccounts = signal<string[]>([]);

  readonly links = FACTOR_LINKS;

  readonly thresholdFields: ThresholdField[] = [
    { key: 'dti_warn', label: 'Debt payments vs income — warn at', suffix: '%' },
    { key: 'dti_high', label: 'Debt payments vs income — high at', suffix: '%' },
    { key: 'balloon_warn', label: 'Balloon vs cash — warn at', suffix: '%' },
    { key: 'balloon_high', label: 'Balloon vs cash — high at', suffix: '%' },
    { key: 'debt_assets_warn', label: 'Debt vs assets — warn at', suffix: '%' },
    { key: 'debt_assets_high', label: 'Debt vs assets — high at', suffix: '%' },
    { key: 'emergency_warn_months', label: 'Emergency fund — warn below', suffix: 'months' },
    { key: 'emergency_high_months', label: 'Emergency fund — high below', suffix: 'months' },
    { key: 'cash_flow_warn_pct', label: 'Month-end cushion — warn below', suffix: '% of income' },
    { key: 'horizon_months', label: 'Look ahead for balloon payments', suffix: 'months' },
  ];

  form = this.fb.nonNullable.group({
    dti_warn: [''],
    dti_high: [''],
    balloon_warn: [''],
    balloon_high: [''],
    debt_assets_warn: [''],
    debt_assets_high: [''],
    emergency_warn_months: [''],
    emergency_high_months: [''],
    cash_flow_warn_pct: [''],
    horizon_months: [''],
    alerts_enabled: [true],
    email_enabled: [true],
  });

  /** Score ring fill (CSS conic-gradient angle). */
  scoreDeg = computed(() => Math.round(((this.report()?.score ?? 0) / 100) * 360));
  debtFactors = computed(() => (this.report()?.factors ?? []).filter((f) => f.category === 'debt'));
  liquidityFactors = computed(() => (this.report()?.factors ?? []).filter((f) => f.category === 'liquidity'));
  liquidAccounts = computed(() => this.accounts().filter((a) => a.account_type !== 'credit_card'));

  ngOnInit(): void {
    this.load(false);
    this.loadHistory();
    // Any saved transaction, account, commitment or planned item changes the score.
    this.refresh.changed$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => {
      this.load(false);
      this.loadHistory();
    });
    this.budgeting.accounts().subscribe({ next: (a) => this.accounts.set(a), error: () => this.accounts.set([]) });
    this.risk.settings().subscribe({ next: (s) => this.applySettings(s), error: () => undefined });
  }

  private loadHistory(): void {
    this.risk.history(90).subscribe({ next: (h) => this.history.set(h.points), error: () => this.history.set([]) });
  }

  load(refresh: boolean): void {
    if (refresh) this.refreshing.set(true);
    this.risk.report(refresh).subscribe({
      next: (r) => {
        this.report.set(r);
        this.loading.set(false);
        this.refreshing.set(false);
        if (refresh) this.toast.success('Risk re-checked and alerts updated.');
      },
      error: (err) => {
        this.loading.set(false);
        this.refreshing.set(false);
        this.toast.fromHttpError(err, 'Could not load your risk report.');
      },
    });
  }

  private applySettings(s: RiskSettings): void {
    this.settings.set(s);
    const values: Record<string, string | boolean> = {
      alerts_enabled: s.alerts_enabled,
      email_enabled: s.email_enabled,
    };
    for (const f of this.thresholdFields) values[f.key] = s.overrides[f.key] ?? '';
    this.form.patchValue(values);
    this.selectedAccounts.set([...s.included_account_ids]);
  }

  toggleAccount(id: string, checked: boolean): void {
    this.selectedAccounts.update((ids) => (checked ? [...ids, id] : ids.filter((x) => x !== id)));
  }

  saveSettings(): void {
    const raw = this.form.getRawValue();
    const payload: RiskSettingsPatch = {
      alerts_enabled: raw.alerts_enabled,
      email_enabled: raw.email_enabled,
      included_account_ids: this.selectedAccounts(),
    };
    for (const f of this.thresholdFields) {
      const v = String(raw[f.key] ?? '').trim();
      payload[f.key] = v === '' ? null : v;
    }
    this.saving.set(true);
    this.risk.updateSettings(payload).subscribe({
      next: (s) => {
        this.saving.set(false);
        this.applySettings(s);
        this.toast.success('Risk settings saved.');
        this.load(false);
      },
      error: (err) => {
        this.saving.set(false);
        this.toast.fromHttpError(err, 'Could not save risk settings.');
      },
    });
  }

  resetDefaults(): void {
    const values: Record<string, string> = {};
    for (const f of this.thresholdFields) values[f.key] = '';
    this.form.patchValue(values);
  }

  formatValue(f: RiskFactor): string {
    if (f.value === null) return '—';
    const n = Number(f.value);
    switch (f.unit) {
      case 'pct':
        return `${n.toFixed(1)}%`;
      case 'months':
        return `${n.toFixed(1)} mo`;
      case 'count':
        return String(Math.round(n));
      default:
        return `${n.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${this.report()?.currency ?? ''}`;
    }
  }

  thresholdText(f: RiskFactor): string {
    if (f.key === 'overdue_installments') return 'Any overdue installment is high risk';
    if (f.key === 'emergency_fund') return `Warn below ${f.warn_at} months · high below ${f.high_at}`;
    if (f.key === 'month_cash_flow') return `Warn below ${f.warn_at}% of income · high below 0`;
    if (f.warn_at === null) return '';
    return `Warn at ${f.warn_at}% · high at ${f.high_at}%`;
  }

  itemText(item: Record<string, unknown>): string {
    const parts = [item['name'], item['due_date'], item['amount']].filter((x) => x !== undefined && x !== null);
    const dates = item['dates'];
    if (Array.isArray(dates) && dates.length) parts.push(`on ${dates.join(', ')}`);
    return parts.join(' · ');
  }

  statusLabel(status: string): string {
    return { ok: 'OK', warn: 'Watch', high: 'High', unknown: 'Needs data' }[status] ?? status;
  }

  barHeight(p: RiskHistoryPoint): number {
    return p.score === null ? 4 : Math.max(4, p.score);
  }
}
