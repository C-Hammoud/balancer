/** Options of a downloadable report (dashboard card and Reports page). */
export type ReportFileType = 'xlsx' | 'pdf' | 'csv' | 'json';
export type ReportScope = 'year' | 'month';

export interface ReportOptions {
  type: ReportFileType;
  scope: ReportScope;
  transactions: boolean;
}

export interface ReportFormatInfo {
  type: ReportFileType;
  name: string;
  badge: string;
  hint: string;
  /** How the transactions are added in this format. */
  transactionsHint: string;
}

export const REPORT_FORMATS: readonly ReportFormatInfo[] = [
  {
    type: 'xlsx',
    name: 'Excel',
    badge: 'XLS',
    hint: 'Separate sheets, ready to sort and sum',
    transactionsHint: 'on their own sheet',
  },
  { type: 'pdf', name: 'PDF', badge: 'PDF', hint: 'Ready to print or share', transactionsHint: 'as a table at the end' },
  { type: 'csv', name: 'CSV', badge: 'CSV', hint: 'Plain table for any app', transactionsHint: 'as a section at the end' },
  { type: 'json', name: 'JSON', badge: '{ }', hint: 'Raw data for other tools', transactionsHint: 'as a list' },
];

const STORAGE_KEY = 'report_options';
export const DEFAULT_REPORT_OPTIONS: ReportOptions = { type: 'xlsx', scope: 'year', transactions: true };

export function formatInfo(type: ReportFileType): ReportFormatInfo {
  return REPORT_FORMATS.find((f) => f.type === type) ?? REPORT_FORMATS[0];
}

export function loadReportOptions(): ReportOptions {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null') as Partial<ReportOptions> | null;
    if (!raw) return { ...DEFAULT_REPORT_OPTIONS };
    return {
      type: REPORT_FORMATS.some((f) => f.type === raw.type) ? (raw.type as ReportFileType) : DEFAULT_REPORT_OPTIONS.type,
      scope: raw.scope === 'month' ? 'month' : 'year',
      transactions: raw.transactions !== false,
    };
  } catch {
    return { ...DEFAULT_REPORT_OPTIONS };
  }
}

export function saveReportOptions(o: ReportOptions): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(o));
  } catch {
    /* private browsing */
  }
}

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

export function periodLabel(scope: ReportScope, year: number, month: number): string {
  return scope === 'year' ? String(year) : `${MONTHS[month - 1]} ${year}`;
}

/** The parts of the file, in order: "Summary", "Months", "Spending", "Transactions". */
export function reportContents(o: ReportOptions): string[] {
  const parts = ['Summary', o.scope === 'year' ? 'Months' : 'Budget by category', 'Spending by category'];
  if (o.transactions) parts.push('Transactions');
  return parts;
}

export function reportFileName(o: ReportOptions, year: number, month: number): string {
  const stem = o.scope === 'year' ? `finance-report-${year}` : `finance-report-${year}-${String(month).padStart(2, '0')}`;
  return `${stem}.${o.type}`;
}

/** Query parameters for GET budgeting/reports/export/. */
export function reportQuery(o: ReportOptions, year: number, month: number): Record<string, string> {
  const q: Record<string, string> = { type: o.type, scope: o.scope, year: String(year) };
  if (o.scope === 'month') q['month'] = String(month);
  if (o.transactions) q['transactions'] = '1';
  return q;
}

/** filename="x.xlsx" from a Content-Disposition header. */
export function filenameFromDisposition(header: string | null): string | null {
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(header || '');
  return m ? decodeURIComponent(m[1]) : null;
}
