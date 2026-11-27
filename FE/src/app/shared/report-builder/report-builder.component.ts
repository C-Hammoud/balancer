import { Component, EventEmitter, Input, OnChanges, OnInit, Output, booleanAttribute, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { BudgetingService } from '../../core/budgeting.service';
import { ToastService } from '../../core/toast.service';
import {
  REPORT_FORMATS,
  ReportFileType,
  ReportOptions,
  ReportScope,
  filenameFromDisposition,
  formatInfo,
  loadReportOptions,
  periodLabel,
  reportContents,
  reportFileName,
  reportQuery,
  saveReportOptions,
} from './report-options';

export interface ReportPeriod {
  scope: ReportScope;
  year: number;
  month: number;
}

/**
 * Pick a period, a file type (Excel, PDF, CSV, JSON) and whether to add the transactions,
 * then download. `compact` (dashboard card) follows the dashboard's year and month; the full
 * version (Reports page) has its own year / month pickers.
 */
@Component({
  selector: 'app-report-builder',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './report-builder.component.html',
  styleUrl: './report-builder.component.scss',
})
export class ReportBuilderComponent implements OnInit, OnChanges {
  private api = inject(BudgetingService);
  private toast = inject(ToastService);

  @Input() year = new Date().getFullYear();
  @Input() month = new Date().getMonth() + 1;
  @Input({ transform: booleanAttribute }) compact = false;
  /** The chosen period, so a page can preview it. */
  @Output() periodChange = new EventEmitter<ReportPeriod>();

  readonly formats = REPORT_FORMATS;
  readonly years = Array.from({ length: 6 }, (_, i) => new Date().getFullYear() - 4 + i);
  readonly monthNames = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
  ];

  options = signal<ReportOptions>(loadReportOptions());
  pickedYear = signal(this.year);
  pickedMonth = signal(this.month);
  downloading = signal(false);

  readonly format = computed(() => formatInfo(this.options().type));
  readonly contents = computed(() => reportContents(this.options()));
  readonly period = computed(() => periodLabel(this.options().scope, this.pickedYear(), this.pickedMonth()));

  ngOnInit(): void {
    this.emitPeriod();
  }

  ngOnChanges(): void {
    // The dashboard's year / month (and the page's starting point) come in through the inputs.
    this.pickedYear.set(this.year);
    this.pickedMonth.set(this.month);
    this.emitPeriod();
  }

  setType(type: ReportFileType): void {
    this.update({ type });
  }

  setScope(scope: ReportScope): void {
    this.update({ scope });
    this.emitPeriod();
  }

  setTransactions(transactions: boolean): void {
    this.update({ transactions });
  }

  pickYear(y: number): void {
    this.pickedYear.set(+y);
    this.emitPeriod();
  }

  pickMonth(m: number): void {
    this.pickedMonth.set(+m);
    this.emitPeriod();
  }

  download(): void {
    if (this.downloading()) return;
    const o = this.options();
    const year = this.pickedYear();
    const month = this.pickedMonth();
    this.downloading.set(true);
    this.api.exportReport(reportQuery(o, year, month)).subscribe({
      next: (res) => {
        this.downloading.set(false);
        if (!res.body) return;
        const name = filenameFromDisposition(res.headers.get('Content-Disposition')) || reportFileName(o, year, month);
        saveBlob(res.body, name);
        this.toast.success(`${this.format().name} report downloaded.`);
      },
      error: (err) => {
        this.downloading.set(false);
        this.toast.fromHttpError(err, 'Could not build the report.');
      },
    });
  }

  private update(patch: Partial<ReportOptions>): void {
    const next = { ...this.options(), ...patch };
    this.options.set(next);
    saveReportOptions(next);
  }

  private emitPeriod(): void {
    this.periodChange.emit({ scope: this.options().scope, year: this.pickedYear(), month: this.pickedMonth() });
  }
}

/** Save a downloaded file through a temporary link. */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
