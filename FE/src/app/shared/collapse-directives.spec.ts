import { Component } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { AuthService } from '../core/auth.service';
import { CollapsibleCardDirective } from './collapsible-card.directive';
import { StackCollapseDirective } from './stack-collapse.directive';

@Component({
  standalone: true,
  imports: [StackCollapseDirective],
  template: `
    <table class="stack-table" appStackCollapse>
      <tbody>
        <tr id="row">
          <td data-label="Merchant" data-summary="title">Coffee</td>
          <td data-label="Amount" data-summary="end">4.50</td>
          <td data-label="Note">Morning</td>
          <td data-label=""><button type="button" id="edit">Edit</button></td>
        </tr>
        <tr id="short">
          <td data-label="Name" data-summary="title">Bank</td>
          <td data-label="Balance" data-summary="end">10</td>
        </tr>
        <tr id="empty"><td colspan="4">No transactions.</td></tr>
      </tbody>
    </table>
  `,
})
class TableHost {}

@Component({
  standalone: true,
  imports: [CollapsibleCardDirective],
  template: `
    <section class="panel" appCollapsibleCard="year">
      <header><h2>2026 overview</h2></header>
      <p id="body">Chart</p>
    </section>
  `,
})
class CardHost {}

function mockPhone(matches: boolean): void {
  spyOn(window, 'matchMedia').and.returnValue({
    matches,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
  } as unknown as MediaQueryList);
}

describe('StackCollapseDirective', () => {
  let fixture: ComponentFixture<TableHost>;
  const row = (id: string) => fixture.nativeElement.querySelector('#' + id) as HTMLElement;

  function create(phone: boolean): void {
    mockPhone(phone);
    fixture = TestBed.createComponent(TableHost);
    fixture.detectChanges();
  }

  it('marks rows: collapsible, compact only, untouched', () => {
    create(true);
    expect(row('row').classList).toContain('sc-more');
    expect(row('row').getAttribute('aria-expanded')).toBe('false');
    expect(row('row').tabIndex).toBe(0);
    // Every cell is on the compact line: nothing to open.
    expect(row('short').classList).toContain('sc-row');
    expect(row('short').classList).not.toContain('sc-more');
    expect(row('empty').classList).not.toContain('sc-row');
  });

  it('opens and closes on tap, but not when a button is tapped', () => {
    create(true);
    const tr = row('row');
    (tr.querySelector('td') as HTMLElement).click();
    expect(tr.classList).toContain('sc-open');
    expect(tr.getAttribute('aria-expanded')).toBe('true');
    (fixture.nativeElement.querySelector('#edit') as HTMLElement).click();
    expect(tr.classList).toContain('sc-open');
    (tr.querySelector('td') as HTMLElement).click();
    expect(tr.classList).not.toContain('sc-open');
  });

  it('opens with Enter from the keyboard', () => {
    create(true);
    const tr = row('row');
    tr.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    expect(tr.classList).toContain('sc-open');
  });

  it('does nothing on a wide screen', () => {
    create(false);
    const tr = row('row');
    expect(tr.hasAttribute('tabindex')).toBeFalse();
    (tr.querySelector('td') as HTMLElement).click();
    expect(tr.classList).not.toContain('sc-open');
  });
});

describe('CollapsibleCardDirective', () => {
  const KEY = 'collapsed_cards_7';

  beforeEach(() => {
    localStorage.removeItem(KEY);
    TestBed.configureTestingModule({
      providers: [{ provide: AuthService, useValue: { user: () => ({ id: 7 }) } }],
    });
  });

  afterEach(() => localStorage.removeItem(KEY));

  function create(): HTMLElement {
    const fixture = TestBed.createComponent(CardHost);
    fixture.detectChanges();
    return fixture.nativeElement.querySelector('section');
  }

  it('adds a fold button that hides the card body and is remembered', () => {
    const card = create();
    const button = card.querySelector('.cc-toggle') as HTMLButtonElement;
    expect(button).toBeTruthy();
    expect(button.getAttribute('aria-expanded')).toBe('true');
    expect(button.getAttribute('aria-label')).toBe('Collapse 2026 overview');

    button.click();
    expect(card.classList).toContain('cc-collapsed');
    expect(button.getAttribute('aria-expanded')).toBe('false');
    expect(JSON.parse(localStorage.getItem(KEY) || '[]')).toEqual(['year']);

    // A new visit starts folded.
    const again = create();
    expect(again.classList).toContain('cc-collapsed');
    (again.querySelector('.cc-toggle') as HTMLButtonElement).click();
    expect(JSON.parse(localStorage.getItem(KEY) || '[]')).toEqual([]);
  });
});
