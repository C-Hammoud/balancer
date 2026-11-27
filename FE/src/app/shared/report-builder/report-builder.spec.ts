import { HttpHeaders, HttpResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { BudgetingService } from '../../core/budgeting.service';
import { ToastService } from '../../core/toast.service';
import { ReportBuilderComponent } from './report-builder.component';
import {
  filenameFromDisposition,
  loadReportOptions,
  periodLabel,
  reportContents,
  reportFileName,
  reportQuery,
  saveReportOptions,
} from './report-options';

describe('report options', () => {
  afterEach(() => localStorage.removeItem('report_options'));

  it('builds the export query', () => {
    expect(reportQuery({ type: 'xlsx', scope: 'year', transactions: true }, 2026, 11)).toEqual({
      type: 'xlsx', scope: 'year', year: '2026', transactions: '1',
    });
    expect(reportQuery({ type: 'pdf', scope: 'month', transactions: false }, 2026, 3)).toEqual({
      type: 'pdf', scope: 'month', year: '2026', month: '3',
    });
  });

  it('lists what the file contains', () => {
    expect(reportContents({ type: 'xlsx', scope: 'year', transactions: true })).toEqual([
      'Summary', 'Months', 'Spending by category', 'Transactions',
    ]);
    expect(reportContents({ type: 'csv', scope: 'month', transactions: false })).toEqual([
      'Summary', 'Budget by category', 'Spending by category',
    ]);
  });

  it('names files and periods', () => {
    expect(reportFileName({ type: 'json', scope: 'month', transactions: false }, 2026, 4)).toBe('finance-report-2026-04.json');
    expect(periodLabel('month', 2026, 11)).toBe('November 2026');
    expect(filenameFromDisposition('attachment; filename="finance-report-2026.xlsx"')).toBe('finance-report-2026.xlsx');
    expect(filenameFromDisposition(null)).toBeNull();
  });

  it('remembers the choice and ignores junk', () => {
    saveReportOptions({ type: 'pdf', scope: 'month', transactions: false });
    expect(loadReportOptions()).toEqual({ type: 'pdf', scope: 'month', transactions: false });
    localStorage.setItem('report_options', '{"type":"docx"}');
    expect(loadReportOptions().type).toBe('xlsx');
    localStorage.setItem('report_options', 'not json');
    expect(loadReportOptions()).toEqual({ type: 'xlsx', scope: 'year', transactions: true });
  });
});

describe('ReportBuilderComponent', () => {
  let exportReport: jasmine.Spy;

  beforeEach(() => {
    localStorage.removeItem('report_options');
    exportReport = jasmine.createSpy('exportReport').and.returnValue(
      of(new HttpResponse({ body: new Blob(['x']), headers: new HttpHeaders() })),
    );
    TestBed.configureTestingModule({
      providers: [
        { provide: BudgetingService, useValue: { exportReport } },
        { provide: ToastService, useValue: { success: () => undefined, fromHttpError: () => undefined } },
      ],
    });
  });

  afterEach(() => localStorage.removeItem('report_options'));

  it('follows the chosen format and downloads with the right query', () => {
    const fixture = TestBed.createComponent(ReportBuilderComponent);
    fixture.componentRef.setInput('year', 2026);
    fixture.componentRef.setInput('month', 11);
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    const button = () => el.querySelector('.rb-download') as HTMLButtonElement;
    expect(button().textContent).toContain('Download Excel');

    (el.querySelector('.card[data-type="pdf"] input') as HTMLInputElement).click();
    (el.querySelectorAll('.seg button')[1] as HTMLButtonElement).click();
    fixture.detectChanges();
    expect(button().textContent).toContain('Download PDF');
    expect(el.querySelector('.rb-inside')!.textContent).toContain('Budget by category');

    spyOn(URL, 'createObjectURL').and.returnValue('blob:x');
    spyOn(HTMLAnchorElement.prototype, 'click');
    button().click();
    expect(exportReport).toHaveBeenCalledWith({ type: 'pdf', scope: 'month', year: '2026', month: '11', transactions: '1' });
    expect(JSON.parse(localStorage.getItem('report_options')!)).toEqual({ type: 'pdf', scope: 'month', transactions: true });
  });
});
